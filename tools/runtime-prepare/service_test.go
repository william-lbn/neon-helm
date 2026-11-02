package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	vmfake "github.com/neondatabase/autoscaling/neonvm/client/clientset/versioned/fake"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/util/intstr"
	kubefake "k8s.io/client-go/kubernetes/fake"
	kt "k8s.io/client-go/testing"
)

// 模拟API分配UID/RV/ClusterIP，不从模板或同名GET推导原身份。
func installManagementServiceReactor(t *testing.T, c *kubefake.Clientset) {
	t.Helper()
	c.PrependReactor("create", "services", func(a kt.Action) (bool, runtime.Object, error) {
		s := a.(kt.CreateAction).GetObject().(*corev1.Service).DeepCopy()
		s.UID = "api-assigned-service-uid"
		s.ResourceVersion = "1"
		s.Spec.ClusterIP = "10.96.0.11"
		require.NoError(t, c.Tracker().Create(corev1.SchemeGroupVersion.WithResource("services"), s, s.Namespace))
		return true, s, nil
	})
}
func managementServiceFixture(t *testing.T) (*preparer, *kubefake.Clientset) {
	t.Helper()
	vm, _ := nativeUnit(t)
	vms := vmfake.NewSimpleClientset(vm)
	core := kubefake.NewSimpleClientset()
	wanted := vm.DeepCopy()
	wanted.UID = ""
	wanted.ResourceVersion = ""
	p := &preparer{core: core.CoreV1(), vms: vms.NeonvmV1().VirtualMachines(vm.Namespace), wanted: wanted, state: retained{ProtocolVersion: 1, Scope: stateScope, ManifestSHA256: digest([]byte("original-held-manifest")), VMUID: vm.UID, Namespace: vm.Namespace, Name: vm.Name}, statePath: filepath.Join(t.TempDir(), "state.json")}
	return p, core
}
func TestRuntimeManagementServicePersistsActualUIDBeforeRelease(t *testing.T) {
	p, c := managementServiceFixture(t)
	installManagementServiceReactor(t, c)
	c.PrependReactor("create", "services", func(a kt.Action) (bool, runtime.Object, error) {
		b, e := os.ReadFile(p.statePath)
		require.NoError(t, e)
		var before retained
		require.NoError(t, json.Unmarshal(b, &before))
		require.True(t, before.ManagementServiceCreateMayHaveSent)
		require.Empty(t, before.ManagementServiceUID)
		require.False(t, before.ReleaseMayHaveSent)
		return false, nil, nil
	})
	s, e := p.managementService(context.Background(), true)
	require.NoError(t, e)
	require.Equal(t, p.state.VMUID, s.OwnerReferences[0].UID)
	require.Equal(t, "api-assigned-service-uid", string(s.UID))
	require.Equal(t, s.UID, p.state.ManagementServiceUID)
	require.Equal(t, s.ResourceVersion, p.state.ManagementServiceResourceVersion)
	b, e := os.ReadFile(p.statePath)
	require.NoError(t, e)
	var after retained
	require.NoError(t, json.Unmarshal(b, &after))
	require.Equal(t, s.UID, after.ManagementServiceUID)
	c.ClearActions()
	_, e = p.managementService(context.Background(), false)
	require.NoError(t, e)
	for _, a := range c.Actions() {
		require.Equal(t, "get", a.GetVerb())
	}
	vm, e := p.vms.Get(context.Background(), p.wanted.Name, metav1.GetOptions{})
	require.NoError(t, e)
	require.False(t, vm.Spec.DSGABootstrap.Ready)
}
func TestRuntimeManagementServiceRejectsOriginalIdentityAndRouteDrift(t *testing.T) {
	for _, name := range []string{"uid", "owner", "project", "endpoint", "operation", "incarnation", "compute", "selector", "extra-selector", "port", "string-target", "deleting", "external", "extra-port"} {
		t.Run(name, func(t *testing.T) {
			p, c := managementServiceFixture(t)
			installManagementServiceReactor(t, c)
			s, e := p.managementService(context.Background(), true)
			require.NoError(t, e)
			switch name {
			case "uid":
				s.UID = "replacement"
			case "owner":
				s.OwnerReferences[0].UID = "replacement"
			case "project":
				s.Labels["neon-control/project-id"] = "replacement"
			case "endpoint":
				s.Labels["neon-control/endpoint-id"] = "ep_replacement"
			case "operation":
				s.Annotations[serviceOperation] = "replacement"
			case "incarnation":
				s.Annotations[serviceIncarnation] = "replacement"
			case "compute":
				s.Annotations[serviceCompute] = "replacement"
			case "selector":
				s.Spec.Selector["vm.neon.tech/name"] = "replacement"
			case "extra-selector":
				s.Spec.Selector["extra"] = "replacement"
			case "port":
				s.Spec.Ports[0].Port++
			case "string-target":
				s.Spec.Ports[0].TargetPort = intstr.FromString("3080")
			case "deleting":
				stamp := metav1.Now()
				s.DeletionTimestamp = &stamp
			case "external":
				s.Spec.ExternalIPs = []string{"192.0.2.1"}
			case "extra-port":
				s.Spec.Ports = append(s.Spec.Ports, s.Spec.Ports[0])
			}
			require.NoError(t, c.Tracker().Update(corev1.SchemeGroupVersion.WithResource("services"), s, s.Namespace))
			c.ClearActions()
			_, e = p.managementService(context.Background(), true)
			require.Error(t, e)
			for _, a := range c.Actions() {
				require.Equal(t, "get", a.GetVerb(), "drift must never cause PATCH, UPDATE or replacement CREATE")
			}
		})
	}
}
func TestRuntimeManagementServiceNeverAdoptsUnconfirmedOrDeletedName(t *testing.T) {
	for _, name := range []string{"unconfirmed-create", "existing-without-receipt", "known-deleted", "ready-without-receipt", "retiring"} {
		t.Run(name, func(t *testing.T) {
			p, c := managementServiceFixture(t)
			vm, e := p.vms.Get(context.Background(), p.wanted.Name, metav1.GetOptions{})
			require.NoError(t, e)
			switch name {
			case "unconfirmed-create":
				p.state.ManagementServiceCreateMayHaveSent = true
			case "existing-without-receipt":
				s, e := managementServiceIntent(vm, p.state)
				require.NoError(t, e)
				s.UID = "same-name-api-uid"
				s.ResourceVersion = "1"
				s.Spec.ClusterIP = "10.96.0.11"
				require.NoError(t, c.Tracker().Create(corev1.SchemeGroupVersion.WithResource("services"), s, s.Namespace))
			case "known-deleted":
				p.state.ManagementServiceCreateMayHaveSent = true
				p.state.ManagementServiceUID = "original-deleted-service"
			case "ready-without-receipt":
				vm.Spec.DSGABootstrap.Ready = true
				_, e = p.vms.Update(context.Background(), vm, metav1.UpdateOptions{})
				require.NoError(t, e)
			case "retiring":
				p.state.RetireMayHaveSent = true
			}
			c.ClearActions()
			_, e = p.managementService(context.Background(), true)
			require.Error(t, e)
			for _, a := range c.Actions() {
				require.Equal(t, "get", a.GetVerb())
			}
		})
	}
}
