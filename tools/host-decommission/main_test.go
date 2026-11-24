//go:build linux

package main

import (
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	vm "github.com/neondatabase/autoscaling/neonvm/apis/neonvm/v1"
	"github.com/neondatabase/autoscaling/pkg/dsga/hostguard"
	"github.com/neondatabase/autoscaling/pkg/dsga/journal"
	coordination "k8s.io/api/coordination/v1"
	core "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func fixture(now time.Time) snapshot {
	binding := hostguard.Binding{NodeName: "host-a", NodeUID: "original-node-uid", Namespace: "workload-a", LeaseName: "neon-dsga-host-host-a", LeaseUID: "original-lease-uid"}
	yes := true
	duration := int32(10)
	renew := metav1.NewMicroTime(now.Add(-time.Minute))
	deleting := metav1.NewTime(now.Add(-30 * time.Second))
	containers := []core.Container{{Name: "process", Resources: core.ResourceRequirements{Limits: core.ResourceList{core.ResourceMemory: resource.MustParse("128Mi")}}}}
	ordinary := core.Pod{ObjectMeta: metav1.ObjectMeta{Name: "dns-original", Namespace: "kube-system", UID: "original-ordinary-uid", ResourceVersion: "11"}, Spec: core.PodSpec{NodeName: "host-a", Containers: containers}, Status: core.PodStatus{Phase: core.PodRunning}}
	writer := core.Pod{ObjectMeta: metav1.ObjectMeta{Name: "capacity-writer-original", Namespace: "kube-system", UID: "original-writer-uid", ResourceVersion: "12", DeletionTimestamp: &deleting}, Spec: core.PodSpec{NodeName: "host-a", Containers: containers}, Status: core.PodStatus{Phase: core.PodFailed, ContainerStatuses: []core.ContainerStatus{{Name: "process", State: core.ContainerState{Terminated: &core.ContainerStateTerminated{ExitCode: 0}}}}}}
	placements := []hostguard.Placement{{Namespace: ordinary.Namespace, PodName: ordinary.Name, PodUID: string(ordinary.UID), MemoryBytes: 128 << 20, HostOverheadBytes: 16 << 20}}
	model := hostguard.Model{ProtocolVersion: 10, Binding: binding, Origin: strings.Repeat("e", 32), LeaseFloor: journal.Owner{HolderID: "original-capacity-owner", Epoch: 1}, Sequence: 7, OutsideBytes: 4 << 30, Holds: []hostguard.Hold{}, Profile: &hostguard.Profile{ID: "explicit-test-only", SchedulerName: "autoscale-scheduler", VMOverheadBytes: 3 << 30, PodOverheadBytes: 16 << 20}, Placements: &placements}
	if model.Validate() != nil {
		panic("invalid explicit test fixture")
	}
	raw, _ := json.Marshal(model)
	node := core.Node{ObjectMeta: metav1.ObjectMeta{Name: binding.NodeName, UID: binding.NodeUID, ResourceVersion: "13", Finalizers: []string{hostguard.ProtectionFinalizer}, Annotations: map[string]string{hostguard.LedgerAnnotation: string(raw), hostguard.OriginAnnotation: "1:" + model.Origin}}, Status: core.NodeStatus{Conditions: []core.NodeCondition{{Type: core.NodeReady, Status: core.ConditionTrue}}}}
	lease := coordination.Lease{ObjectMeta: metav1.ObjectMeta{Name: binding.LeaseName, Namespace: binding.Namespace, UID: binding.LeaseUID, ResourceVersion: "14", Annotations: map[string]string{hostguard.LeaseAnnotation: hostguard.LeaseMarker(binding)}, OwnerReferences: []metav1.OwnerReference{{APIVersion: "v1", Kind: "Node", Name: binding.NodeName, UID: binding.NodeUID, Controller: &yes}}}, Spec: coordination.LeaseSpec{RenewTime: &renew, LeaseDurationSeconds: &duration}}
	return snapshot{Nodes: core.NodeList{Items: []core.Node{node}}, Pods: core.PodList{Items: []core.Pod{ordinary, writer}}, Leases: coordination.LeaseList{Items: []coordination.Lease{lease}}, VMs: vm.VirtualMachineList{Items: []vm.VirtualMachine{}}, Hosts: []hostguard.Binding{binding}, WriterUIDs: []string{string(writer.UID)}, ObservedUnix: now.Unix()}
}

func TestHostDomainHandoffKeepsOrdinaryPodRunning(t *testing.T) {
	now := time.Now()
	s := fixture(now)
	if err := validate(s, now); err != nil {
		t.Fatal(err)
	}
	if s.Pods.Items[0].Status.Phase != core.PodRunning {
		t.Fatal("handoff must not require deleting shared DNS/CNI Pods")
	}
}

func TestHostDomainHandoffAcceptsFreshNativePodLedgerVersions(t *testing.T) {
	now := time.Now()
	for _, version := range []uint32{3, 5, 10} {
		t.Run(fmt.Sprint(version), func(t *testing.T) {
			s := fixture(now)
			var model hostguard.Model
			json.Unmarshal([]byte(s.Nodes.Items[0].Annotations[hostguard.LedgerAnnotation]), &model)
			model.ProtocolVersion = version
			if err := model.Validate(); err != nil {
				t.Fatal(err)
			}
			raw, _ := json.Marshal(model)
			s.Nodes.Items[0].Annotations[hostguard.LedgerAnnotation] = string(raw)
			if err := validate(s, now); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestHostDomainHandoffRejectsIncompleteOrUnsupportedProtocol(t *testing.T) {
	now := time.Now()
	for _, version := range []uint32{2, 11} {
		t.Run(fmt.Sprint(version), func(t *testing.T) {
			s := fixture(now)
			var model hostguard.Model
			json.Unmarshal([]byte(s.Nodes.Items[0].Annotations[hostguard.LedgerAnnotation]), &model)
			model.ProtocolVersion = version
			raw, _ := json.Marshal(model)
			s.Nodes.Items[0].Annotations[hostguard.LedgerAnnotation] = string(raw)
			if validate(s, now) == nil {
				t.Fatal("incomplete or unsupported native protocol accepted")
			}
		})
	}
}

func TestHostDomainHandoffRejectsUnconfirmedOrHeldSources(t *testing.T) {
	now := time.Now()
	cases := map[string]func(*snapshot){
		"vm-still-exists": func(s *snapshot) { s.VMs.Items = append(s.VMs.Items, vm.VirtualMachine{}) },
		"runner-still-exists": func(s *snapshot) {
			s.Pods.Items[0].OwnerReferences = []metav1.OwnerReference{{Kind: "VirtualMachine", UID: "old-vm"}}
		},
		"writer-still-running": func(s *snapshot) {
			s.Pods.Items[1].Status.ContainerStatuses[0].State = core.ContainerState{Running: &core.ContainerStateRunning{}}
		},
		"writer-404-is-not-exit-proof": func(s *snapshot) { s.Pods.Items = s.Pods.Items[:1] },
		"writer-same-name-new-uid":     func(s *snapshot) { s.Pods.Items[1].UID = "replacement-writer-uid" },
		"ordinary-same-name-new-uid":   func(s *snapshot) { s.Pods.Items[0].UID = "replacement-ordinary-uid" },
		"ordinary-limit-missing":       func(s *snapshot) { s.Pods.Items[0].Spec.Containers[0].Resources.Limits = nil },
		"lease-not-expired":            func(s *snapshot) { renew := metav1.NewMicroTime(now); s.Leases.Items[0].Spec.RenewTime = &renew },
		"lease-uid-changed":            func(s *snapshot) { s.Leases.Items[0].UID = "replacement-lease-uid" },
		"node-uid-changed":             func(s *snapshot) { s.Nodes.Items[0].UID = "replacement-node-uid" },
		"stale-snapshot":               func(s *snapshot) { s.ObservedUnix = now.Add(-16 * time.Second).Unix() },
		"paginated-pods":               func(s *snapshot) { s.Pods.Continue = "more-pods" },
		"origin-changed": func(s *snapshot) {
			s.Nodes.Items[0].Annotations[hostguard.OriginAnnotation] = "1:" + strings.Repeat("f", 32)
		},
		"native-model-corrupt": func(s *snapshot) {
			s.Nodes.Items[0].Annotations[hostguard.LedgerAnnotation] = `{"protocol_version":10}`
		},
		"managed-placement-remains": func(s *snapshot) {
			var m hostguard.Model
			if json.Unmarshal([]byte(s.Nodes.Items[0].Annotations[hostguard.LedgerAnnotation]), &m) != nil {
				panic("fixture")
			}
			p := &(*m.Placements)[0]
			p.Managed = true
			p.VMName = "old-vm"
			p.VMUID = "original-vm-uid"
			p.Incarnation = strings.Repeat("b", 32)
			p.PodMemoryLimitBytes = 128 << 20
			raw, _ := json.Marshal(m)
			s.Nodes.Items[0].Annotations[hostguard.LedgerAnnotation] = string(raw)
		},
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			s := fixture(now)
			mutate(&s)
			if validate(s, now) == nil {
				t.Fatal("unconfirmed or held source accepted")
			}
		})
	}
}

func TestSocketCleanupRequiresConfirmedClosedOriginalSocket(t *testing.T) {
	if os.Getuid() != 0 {
		t.Fatal("release validation requires explicit root-owned Linux socket fixtures")
	}
	t.Run("absent", func(t *testing.T) {
		d := t.TempDir()
		if err := os.Chmod(d, 0700); err != nil {
			t.Fatal(err)
		}
		p := filepath.Join(d, "original.sock")
		if err := socketClosed(p); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("active", func(t *testing.T) {
		d := t.TempDir()
		if err := os.Chmod(d, 0700); err != nil {
			t.Fatal(err)
		}
		p := filepath.Join(d, "original.sock")
		l, err := net.ListenUnix("unix", &net.UnixAddr{Name: p, Net: "unix"})
		if err != nil {
			t.Fatal(err)
		}
		defer l.Close()
		if err = os.Chmod(p, 0600); err != nil {
			t.Fatal(err)
		}
		if socketClosed(p) == nil {
			t.Fatal("live server accepted for cleanup")
		}
	})
	t.Run("stale", func(t *testing.T) {
		d := t.TempDir()
		if err := os.Chmod(d, 0700); err != nil {
			t.Fatal(err)
		}
		p := filepath.Join(d, "original.sock")
		l, err := net.ListenUnix("unix", &net.UnixAddr{Name: p, Net: "unix"})
		if err != nil {
			t.Fatal(err)
		}
		l.SetUnlinkOnClose(false)
		if err = os.Chmod(p, 0600); err != nil {
			t.Fatal(err)
		}
		l.Close()
		if err = socketClosed(p); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("ordinary-file", func(t *testing.T) {
		d := t.TempDir()
		if err := os.Chmod(d, 0700); err != nil {
			t.Fatal(err)
		}
		p := filepath.Join(d, "original.sock")
		if err := os.WriteFile(p, []byte("not a socket"), 0600); err != nil {
			t.Fatal(err)
		}
		if socketClosed(p) == nil {
			t.Fatal("ordinary file accepted")
		}
	})
	t.Run("symlink", func(t *testing.T) {
		d := t.TempDir()
		if err := os.Chmod(d, 0700); err != nil {
			t.Fatal(err)
		}
		p := filepath.Join(d, "original.sock")
		if err := os.Symlink(filepath.Join(d, "other.sock"), p); err != nil {
			t.Fatal(err)
		}
		if socketClosed(p) == nil {
			t.Fatal("symlink accepted")
		}
	})
}
