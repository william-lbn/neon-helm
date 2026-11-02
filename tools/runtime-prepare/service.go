package main

import (
	"context"
	"fmt"
	"net"
	"regexp"

	vmv1 "github.com/neondatabase/autoscaling/neonvm/apis/neonvm/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/intstr"
)

const (
	serviceOperation   = "neon-control/dsga-creation-operation"
	serviceIncarnation = "neon-control/dsga-creation-incarnation"
	serviceCompute     = "neon-control/dsga-creation-compute-instance"
)

// 与原dsga_services.go相同的固定投影，原UID只能从held实际API快照取得。
// 这里的operation绑定首次CREATE前已持久的canonical ManifestSHA，不造CP SQL行。
func managementServiceIntent(vm *vmv1.VirtualMachine, state retained) (*corev1.Service, error) {
	if vm == nil || vm.UID == "" || vm.ResourceVersion == "" || vm.DeletionTimestamp != nil || vm.Spec.DSGABootstrap == nil || state.VMUID != vm.UID || !regexp.MustCompile(`^[a-f0-9]{64}$`).MatchString(state.ManifestSHA256) || !regexp.MustCompile(`^cp-[a-f0-9]{16}$`).MatchString(vm.Name) || vm.Labels["neon-control/project-id"] == "" || vm.Labels["neon-control/endpoint-id"] != "ep_"+vm.Name[3:] {
		return nil, fmt.Errorf("original held Service creation identity required")
	}
	yes, no := true, false
	return &corev1.Service{ObjectMeta: metav1.ObjectMeta{Name: vm.Name + "-management", Namespace: vm.Namespace, Labels: map[string]string{"neon-control/project-id": vm.Labels["neon-control/project-id"], "neon-control/endpoint-id": vm.Labels["neon-control/endpoint-id"]}, Annotations: map[string]string{serviceOperation: state.ManifestSHA256, serviceIncarnation: vm.Spec.DSGABootstrap.Incarnation, serviceCompute: vm.Spec.DSGABootstrap.ComputeInstanceID}, OwnerReferences: []metav1.OwnerReference{{APIVersion: vmv1.SchemeGroupVersion.String(), Kind: "VirtualMachine", Name: vm.Name, UID: vm.UID, Controller: &yes, BlockOwnerDeletion: &no}}}, Spec: corev1.ServiceSpec{Type: corev1.ServiceTypeClusterIP, SessionAffinity: corev1.ServiceAffinityNone, Selector: map[string]string{"vm.neon.tech/name": vm.Name}, Ports: []corev1.ServicePort{{Name: "compute-control", Protocol: corev1.ProtocolTCP, Port: 3080, TargetPort: intstr.FromInt32(3080)}}}}, nil
}
func originalManagementService(wanted, actual *corev1.Service, uid types.UID) error {
	if wanted == nil || actual == nil || uid == "" || actual.UID != uid || actual.ResourceVersion == "" || actual.DeletionTimestamp != nil || actual.Namespace != wanted.Namespace || actual.Name != wanted.Name || len(actual.OwnerReferences) != 1 {
		return fmt.Errorf("original management Service missing or replaced")
	}
	for key, value := range wanted.Labels {
		if actual.Labels[key] != value {
			return fmt.Errorf("original management Service labels differ")
		}
	}
	for key, value := range wanted.Annotations {
		if actual.Annotations[key] != value {
			return fmt.Errorf("original management Service creation reference differs")
		}
	}
	a, w := actual.OwnerReferences[0], wanted.OwnerReferences[0]
	if a.APIVersion != w.APIVersion || a.Kind != w.Kind || a.Name != w.Name || a.UID != w.UID || a.Controller == nil || !*a.Controller || a.BlockOwnerDeletion != nil && *a.BlockOwnerDeletion {
		return fmt.Errorf("original management Service VM controller UID differs")
	}
	s := actual.Spec
	ip := net.ParseIP(s.ClusterIP)
	if s.Type != corev1.ServiceTypeClusterIP || ip == nil || !ip.IsGlobalUnicast() || ip.IsLoopback() || s.ExternalName != "" || len(s.ExternalIPs) != 0 || s.PublishNotReadyAddresses || len(s.Selector) != 1 || s.Selector["vm.neon.tech/name"] != wanted.Spec.Selector["vm.neon.tech/name"] || len(s.Ports) != 1 || (s.SessionAffinity != "" && s.SessionAffinity != corev1.ServiceAffinityNone) || s.SessionAffinityConfig != nil || s.HealthCheckNodePort != 0 || s.LoadBalancerIP != "" || len(s.LoadBalancerSourceRanges) != 0 || s.LoadBalancerClass != nil || s.AllocateLoadBalancerNodePorts != nil || (s.InternalTrafficPolicy != nil && *s.InternalTrafficPolicy != corev1.ServiceInternalTrafficPolicyCluster) || s.TrafficDistribution != nil || (s.ExternalTrafficPolicy != "" && s.ExternalTrafficPolicy != corev1.ServiceExternalTrafficPolicyCluster) {
		return fmt.Errorf("original management Service route differs")
	}
	p, target := s.Ports[0], wanted.Spec.Ports[0]
	if p.Name != target.Name || p.Protocol != target.Protocol || p.Port != target.Port || p.TargetPort != target.TargetPort || p.NodePort != 0 || p.AppProtocol != nil {
		return fmt.Errorf("original management Service exact integer3080 target differs")
	}
	return nil
}

// allowCreate只由seal静态调用；inspect始终false。不是HTTP输入/预算授权开关。
func (p *preparer) managementService(ctx context.Context, allowCreate bool) (*corev1.Service, error) {
	if allowCreate && (p.state.Retired || p.state.RetireMayHaveSent) {
		return nil, fmt.Errorf("retiring original VM cannot create management Service")
	}
	vm, e := p.vms.Get(ctx, p.wanted.Name, metav1.GetOptions{})
	if e != nil {
		return nil, fmt.Errorf("original VM unavailable before management Service")
	}
	if e = originalVM(p.wanted, vm, p.state.VMUID); e != nil {
		return nil, e
	}
	wanted, e := managementServiceIntent(vm, p.state)
	if e != nil {
		return nil, e
	}
	if p.state.ManagementServiceCreateMayHaveSent && p.state.ManagementServiceUID == "" {
		return nil, fmt.Errorf("original management Service CREATE unconfirmed; same-name adoption forbidden")
	}
	services := p.core.Services(vm.Namespace)
	s, e := services.Get(ctx, wanted.Name, metav1.GetOptions{})
	if apierrors.IsNotFound(e) && allowCreate && p.state.ManagementServiceUID == "" && !p.state.ManagementServiceCreateMayHaveSent && !vm.Spec.DSGABootstrap.Ready {
		p.state.ManagementServiceCreateMayHaveSent = true
		if e = p.save(); e != nil {
			return nil, e
		}
		s, e = services.Create(ctx, wanted, metav1.CreateOptions{})
		if e != nil {
			return nil, fmt.Errorf("original management Service CREATE unconfirmed; keep original prefix")
		}
		if s.UID == "" {
			return nil, fmt.Errorf("original management Service CREATE UID unavailable")
		}
		p.state.ManagementServiceUID = s.UID
		p.state.ManagementServiceResourceVersion = s.ResourceVersion
		if e = p.save(); e != nil {
			return nil, e
		}
		s, e = services.Get(ctx, wanted.Name, metav1.GetOptions{})
	}
	if e != nil {
		return nil, fmt.Errorf("original management Service unavailable; automatic replacement forbidden")
	}
	if p.state.ManagementServiceUID == "" {
		return nil, fmt.Errorf("management Service exists without original retained UID; same-name adoption forbidden")
	}
	if e = originalManagementService(wanted, s, p.state.ManagementServiceUID); e != nil {
		return nil, e
	}
	if p.state.ManagementServiceResourceVersion == "" {
		p.state.ManagementServiceResourceVersion = s.ResourceVersion
		if e = p.save(); e != nil {
			return nil, e
		}
	}
	return s, nil
}
