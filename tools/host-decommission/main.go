//go:build linux

// 本工具只核验停用整个Host域前的快照，不释放VM、停止进程或改写运行账本。
// 必须与固定Autoscaling源码一同编译，复用原Model和Pod硬额度验证，禁止自造宽松解析器。
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"slices"
	"syscall"
	"time"

	vm "github.com/neondatabase/autoscaling/neonvm/apis/neonvm/v1"
	"github.com/neondatabase/autoscaling/pkg/dsga/hostguard"
	coordination "k8s.io/api/coordination/v1"
	core "k8s.io/api/core/v1"
)

type snapshot struct {
	Nodes        core.NodeList          `json:"nodes"`
	Pods         core.PodList           `json:"pods"`
	Leases       coordination.LeaseList `json:"leases"`
	VMs          vm.VirtualMachineList  `json:"vms"`
	Hosts        []hostguard.Binding    `json:"hosts"`
	WriterUIDs   []string               `json:"writerUIDs"`
	ObservedUnix int64                  `json:"observedUnix"`
}

func validate(s snapshot, now time.Time) error {
	if s.Nodes.Continue != "" || s.Pods.Continue != "" || s.Leases.Continue != "" || s.VMs.Continue != "" || len(s.VMs.Items) != 0 || len(s.Hosts) == 0 || len(s.WriterUIDs) == 0 || s.ObservedUnix > now.Unix() || now.Unix()-s.ObservedUnix > 15 {
		return errors.New("fresh complete inventories, original hosts and stopped writers are required")
	}
	pods := map[string]*core.Pod{}
	stopped := map[string]bool{}
	for i := range s.Pods.Items {
		p := &s.Pods.Items[i]
		if p.UID == "" || p.ResourceVersion == "" {
			return errors.New("original Pod identity required")
		}
		if pods[string(p.UID)] != nil {
			return errors.New("duplicate Pod UID")
		}
		pods[string(p.UID)] = p
		for _, owner := range p.OwnerReferences {
			if owner.Kind == "VirtualMachine" {
				return errors.New("Runner still exists; use original retirement")
			}
		}
		if slices.Contains(s.WriterUIDs, string(p.UID)) {
			// 此处要求原Pod仍保留且全部已启动容器明确终止；Pod404不冒充进程退出。
			if p.DeletionTimestamp == nil || len(p.Status.ContainerStatuses) != len(p.Spec.Containers) {
				return errors.New("original writer termination is not confirmed")
			}
			for _, c := range p.Status.ContainerStatuses {
				if c.State.Terminated == nil {
					return errors.New("capacity writer still running or unconfirmed")
				}
			}
			for _, c := range p.Status.InitContainerStatuses {
				if c.State.Running != nil {
					return errors.New("writer init process still running")
				}
			}
			stopped[string(p.UID)] = true
		}
	}
	for _, uid := range s.WriterUIDs {
		if !stopped[uid] {
			return errors.New("missing original writer exit proof")
		}
	}
	seen := map[string]bool{}
	for _, binding := range s.Hosts {
		if binding.Validate() != nil || seen[binding.NodeName] {
			return errors.New("invalid or duplicate original Host binding")
		}
		seen[binding.NodeName] = true
		var node *core.Node
		for i := range s.Nodes.Items {
			if s.Nodes.Items[i].Name == binding.NodeName {
				node = &s.Nodes.Items[i]
			}
		}
		if node == nil || node.UID != binding.NodeUID || node.ResourceVersion == "" || node.DeletionTimestamp != nil {
			return errors.New("original Node changed or unavailable")
		}
		ready := false
		for _, c := range node.Status.Conditions {
			if c.Type == core.NodeReady && c.Status == core.ConditionTrue {
				ready = true
			}
		}
		if !ready {
			return errors.New("Node is not currently ready")
		}
		var model hostguard.Model
		if json.Unmarshal([]byte(node.Annotations[hostguard.LedgerAnnotation]), &model) != nil || model.Validate() != nil || model.ProtocolVersion < 3 || model.Binding != binding || model.Profile == nil || model.Placements == nil || node.Annotations[hostguard.OriginAnnotation] != "1:"+model.Origin || !slices.Contains(node.Finalizers, hostguard.ProtectionFinalizer) {
			return errors.New("complete original protected Host model required")
		}
		if len(model.Holds) != 0 {
			return errors.New("unsettled Host hold blocks domain decommission")
		}
		for _, p := range *model.Placements {
			if p.Managed || p.VMUID != "" || p.VMName != "" || p.Incarnation != "" || p.Settled != nil || p.Barrier != nil {
				return errors.New("VM placement still held; cannot decommission")
			}
			actual := pods[p.PodUID]
			if actual == nil || actual.Namespace != p.Namespace || actual.Name != p.PodName || actual.Spec.NodeName != binding.NodeName {
				return errors.New("ordinary Pod identity is not currently confirmed")
			}
			memory, err := hostguard.PodMemoryLimit(actual)
			if err != nil || memory > p.MemoryBytes {
				return errors.New("ordinary Pod hardlimit handoff changed or is unconfirmed")
			}
		}
		var lease *coordination.Lease
		for i := range s.Leases.Items {
			l := &s.Leases.Items[i]
			if l.Namespace == binding.Namespace && l.Name == binding.LeaseName {
				lease = l
			}
		}
		if lease == nil || lease.UID != binding.LeaseUID || lease.ResourceVersion == "" || lease.Annotations[hostguard.LeaseAnnotation] != hostguard.LeaseMarker(binding) || len(lease.OwnerReferences) != 1 || lease.OwnerReferences[0].UID != binding.NodeUID || lease.OwnerReferences[0].Kind != "Node" || lease.OwnerReferences[0].Controller == nil || !*lease.OwnerReferences[0].Controller || lease.Spec.RenewTime == nil || lease.Spec.LeaseDurationSeconds == nil || *lease.Spec.LeaseDurationSeconds <= 0 {
			return errors.New("original Node-owned Lease proof required")
		}
		if !now.After(lease.Spec.RenewTime.Add(time.Duration(*lease.Spec.LeaseDurationSeconds)*time.Second + 2*time.Second)) {
			return errors.New("old capacity writer lease has not expired")
		}
	}
	return nil
}

func socketClosed(path string) error {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return errors.New("explicit clean absolute socket path required")
	}
	parent, err := os.Lstat(filepath.Dir(path))
	if err != nil {
		return err
	}
	owner, ok := parent.Sys().(*syscall.Stat_t)
	if !ok || !parent.IsDir() || parent.Mode()&os.ModeSymlink != 0 || parent.Mode().Perm() != 0700 || owner.Uid != 0 {
		return errors.New("original private root-owned socket directory required")
	}
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || info.Mode()&os.ModeSocket == 0 || info.Mode().Perm() != 0600 || stat.Uid != 0 {
		return errors.New("only the original protected Unix socket can be checked")
	}
	conn, err := net.DialTimeout("unix", path, 300*time.Millisecond)
	if err == nil {
		conn.Close()
		return errors.New("socket still accepts connections; refuse cleanup")
	}
	if errors.Is(err, syscall.ECONNREFUSED) || errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return errors.New("socket liveness remains unconfirmed")
}

func main() {
	if len(os.Args) == 3 && os.Args[1] == "socket-closed" {
		if err := socketClosed(os.Args[2]); err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}
		fmt.Println(`{"socketClosed":true,"clusterMutated":false}`)
		return
	}
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: host-decommission-check ORIGINAL-SNAPSHOT.json")
		os.Exit(2)
	}
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, "snapshot unavailable")
		os.Exit(1)
	}
	var s snapshot
	if err = json.Unmarshal(raw, &s); err == nil {
		err = validate(s, time.Now())
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err.Error())
		os.Exit(1)
	}
	fmt.Println(`{"nativeHostValidation":"PASS","vmCount":0,"heldVMCount":0,"ordinaryPods":"return-to-original-kubernetes-hardlimits","clusterMutated":false}`)
}
