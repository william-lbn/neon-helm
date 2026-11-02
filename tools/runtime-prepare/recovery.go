package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"slices"

	vmv1 "github.com/neondatabase/autoscaling/neonvm/apis/neonvm/v1"
	"github.com/neondatabase/autoscaling/pkg/dsga/hostguard"
	"github.com/neondatabase/autoscaling/pkg/dsga/journal"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// 对齐原Controller finalizer；本工具只检查，不增删任何finalizer或Node账本。
const retireControllerFinalizer = "vm.neon.tech/finalizer"
const retireArchiveScope = "neon-runtime-original-retirement-point-v1"
const retireArchiveMaximum = 16 << 20

type retirementPoint struct {
	ProtocolVersion       uint32               `json:"protocol_version"`
	Scope                 string               `json:"scope"`
	ManifestSHA256        string               `json:"manifest_sha256"`
	PreviousArchiveSHA256 string               `json:"previous_archive_sha256,omitempty"`
	VM                    *vmv1.VirtualMachine `json:"vm"`
	ConfigMaps            []corev1.ConfigMap   `json:"configmaps"`
	SecretUID             string               `json:"secret_uid"`
	SecretDataSHA256      string               `json:"secret_data_sha256"`
	AdmissionObservation  string               `json:"admission_observation"`
}

func checkRetirementState(s retained) error {
	if !s.RetireMayHaveSent && !s.Retired && s.RetireArchiveSHA256 == "" {
		return nil
	}
	if !s.RetireMayHaveSent || !s.Complete || s.VMUID == "" || len(s.RetireArchiveSHA256) != 64 {
		return fmt.Errorf("original retirement ticket is incomplete")
	}
	for _, c := range s.RetireArchiveSHA256 {
		if !(c >= '0' && c <= '9' || c >= 'a' && c <= 'f') {
			return fmt.Errorf("original retirement archive digest invalid")
		}
	}
	return nil
}
func (p *preparer) retirementArchivePath(hash string) string {
	return p.statePath + ".retire-" + hash + ".json"
}
func syncParent(path string) error {
	d, e := os.Open(filepath.Dir(path))
	if e != nil {
		return e
	}
	defer d.Close()
	return d.Sync()
}

func (p *preparer) readRetirementArchive() (retirementPoint, error) {
	var point retirementPoint
	if e := checkRetirementState(p.state); e != nil {
		return point, e
	}
	path := p.retirementArchivePath(p.state.RetireArchiveSHA256)
	info, e := os.Lstat(path)
	if e != nil || !info.Mode().IsRegular() || info.Mode()&0077 != 0 {
		return point, fmt.Errorf("original private retirement archive unavailable")
	}
	raw, e := readBounded(path, retireArchiveMaximum)
	if e != nil || digest(raw) != p.state.RetireArchiveSHA256 {
		return point, fmt.Errorf("original retirement archive bytes changed")
	}
	if e = json.Unmarshal(raw, &point); e != nil || point.ProtocolVersion != 1 || point.Scope != retireArchiveScope || point.ManifestSHA256 != p.state.ManifestSHA256 || point.VM == nil || point.VM.UID != p.state.VMUID || point.VM.Namespace != p.state.Namespace || point.VM.Name != p.state.Name || point.VM.Spec.DSGABootstrap == nil || point.VM.Spec.DSGABootstrap.Incarnation != p.wanted.Spec.DSGABootstrap.Incarnation || point.VM.Spec.DSGABootstrap.ComputeInstanceID != p.wanted.Spec.DSGABootstrap.ComputeInstanceID {
		return point, fmt.Errorf("original retirement archive binding differs")
	}
	return point, nil
}
func (p *preparer) verifyRetirementArchive() error { _, e := p.readRetirementArchive(); return e }

// archiveRetirement保存点时VM/CM库存，不声称退出后新增来源也已归档；旧版本内容寻址保留。
// 不保存Runtime Secret内容或打印凭据，只记录已绑定UID/数据摘要。
func (p *preparer) archiveRetirement(ctx context.Context, vm *vmv1.VirtualMachine) (string, error) {
	point := retirementPoint{ProtocolVersion: 1, Scope: retireArchiveScope, ManifestSHA256: p.state.ManifestSHA256, PreviousArchiveSHA256: p.state.RetireArchiveSHA256, VM: vm.DeepCopy(), SecretUID: string(p.state.SecretUID), SecretDataSHA256: p.state.SecretDataSHA256, ConfigMaps: []corev1.ConfigMap{}, AdmissionObservation: "unknown"}
	snapshot, e := journal.Inspect(vm, journal.Binding{Namespace: vm.Namespace, Name: vm.Name, VMUID: vm.UID, Incarnation: vm.Spec.DSGABootstrap.Incarnation})
	if e != nil {
		return "", fmt.Errorf("original journal binding unavailable before retirement")
	}
	if snapshot.State().ServiceClosure != nil {
		point.AdmissionObservation = "original-closure-WAL-present; live admission not assumed"
	}
	opts := metav1.ListOptions{Limit: 64}
	seen := map[string]bool{}
	inventoryBytes := 0
	for {
		list, e := p.core.ConfigMaps(vm.Namespace).List(ctx, opts)
		if e != nil {
			return "", fmt.Errorf("original source point inventory unavailable")
		}
		for _, cm := range list.Items {
			for _, owner := range cm.OwnerReferences {
				if owner.UID == vm.UID {
					encoded, err := json.Marshal(cm)
					if err != nil {
						return "", err
					}
					inventoryBytes += len(encoded)
					if inventoryBytes > retireArchiveMaximum {
						return "", fmt.Errorf("original source point inventory exceeds fixed bound")
					}
					point.ConfigMaps = append(point.ConfigMaps, *cm.DeepCopy())
					break
				}
			}
		}
		if list.Continue == "" {
			break
		}
		if seen[list.Continue] {
			return "", fmt.Errorf("source inventory pagination repeated")
		}
		seen[list.Continue] = true
		opts.Continue = list.Continue
	}
	// 只接受同一原VM版本；源库存仍明确是点时观察而非跨对象原子快照。
	fresh, e := p.vms.Get(ctx, vm.Name, metav1.GetOptions{})
	if e != nil || fresh.UID != vm.UID || fresh.ResourceVersion != vm.ResourceVersion || fresh.DeletionTimestamp != nil {
		return "", fmt.Errorf("original VM changed during point archive; no DELETE sent")
	}
	raw, e := json.Marshal(point)
	if e != nil || len(raw)+1 > retireArchiveMaximum {
		return "", fmt.Errorf("original retirement point exceeds fixed archive bound")
	}
	raw = append(raw, '\n')
	hash := digest(raw)
	path := p.retirementArchivePath(hash)
	if info, e := os.Lstat(path); e == nil {
		old, e := readBounded(path, retireArchiveMaximum)
		if !info.Mode().IsRegular() || info.Mode()&0077 != 0 || e != nil || digest(old) != hash {
			return "", fmt.Errorf("existing original retirement archive differs")
		}
	} else if !os.IsNotExist(e) {
		return "", e
	} else {
		f, e := os.CreateTemp(filepath.Dir(path), ".retire-point-")
		if e != nil {
			return "", e
		}
		tmp := f.Name()
		defer os.Remove(tmp)
		if _, e = f.Write(raw); e == nil {
			e = f.Sync()
		}
		closeErr := f.Close()
		if e != nil || closeErr != nil {
			return "", fmt.Errorf("retirement archive durability unconfirmed")
		}
		if e = os.Rename(tmp, path); e != nil {
			return "", e
		}
	}
	f, e := os.Open(path)
	if e != nil {
		return "", e
	}
	e = f.Sync()
	closeErr := f.Close()
	if e != nil || closeErr != nil {
		return "", fmt.Errorf("retirement archive sync unconfirmed")
	}
	if e = syncParent(path); e != nil {
		return "", e
	}
	return hash, nil
}

func (p *preparer) originalRetiringVM(vm *vmv1.VirtualMachine) error {
	if vm == nil || vm.UID != p.state.VMUID {
		return fmt.Errorf("retirement refuses a same-name replacement UID")
	}
	copy := vm.DeepCopy()
	copy.DeletionTimestamp = nil
	// 退役原VM允许正常伸缩后的当前Use；原min/max、slot大小及其余Spec仍逐字固定。
	bounds := p.wanted.Spec.Guest.MemorySlots
	actual := vm.Spec.Guest.MemorySlots
	if bounds.Min < 1 || bounds.Max < bounds.Min || actual.Use < bounds.Min || actual.Use > bounds.Max {
		return fmt.Errorf("original VM current memory Use lies outside original min/max")
	}
	copy.Spec.Guest.MemorySlots.Use = bounds.Use
	if e := originalVM(p.wanted, copy, p.state.VMUID); e != nil {
		return e
	}
	if !vm.Spec.DSGABootstrap.Ready || vm.Spec.DSGABootstrap.ConfigSecretUID != string(p.state.SecretUID) {
		return fmt.Errorf("original ready Runtime UID changed")
	}
	return nil
}

// retire只请求原对象正常删除；错误/超时不意味着Guest停止，不清任何旧Unknown。
func (p *preparer) retire(ctx context.Context) error {
	if e := checkRetirementState(p.state); e != nil {
		return e
	}
	if !p.state.Complete || p.state.VMUID == "" || p.state.SecretUID == "" {
		return fmt.Errorf("original completed deployment UID required for retirement")
	}
	var vm *vmv1.VirtualMachine
	var e error
	if !p.state.RetireMayHaveSent {
		vm, e = p.vms.Get(ctx, p.wanted.Name, metav1.GetOptions{})
		if e != nil {
			return fmt.Errorf("actual original VM unavailable before retirement")
		}
		if vm.DeletionTimestamp != nil {
			return fmt.Errorf("already deleting VM without original retirement ticket is unknown")
		}
		if e = p.originalRetiringVM(vm); e != nil {
			return e
		}
		if !vm.Spec.DSGABootstrap.Ready || !slices.Contains(vm.Finalizers, retireControllerFinalizer) {
			return fmt.Errorf("actual ready original VM and controller finalizer required")
		}
		secret, read := p.core.Secrets(vm.Namespace).Get(ctx, vm.Name+"-config", metav1.GetOptions{})
		if read != nil || originalSecret(vm, secret, secret.Data, p.state.SecretUID) != nil || dataHash(secret.Data) != p.state.SecretDataSHA256 {
			return fmt.Errorf("original Runtime source UID/bytes unavailable before retirement")
		}
	} else {
		if _, e = p.readRetirementArchive(); e != nil {
			return e
		}
		vm, e = p.vms.Get(ctx, p.wanted.Name, metav1.GetOptions{})
		if apierrors.IsNotFound(e) {
			return p.finishRetirement(ctx)
		}
		if e != nil {
			return fmt.Errorf("original VM deletion state unknown; retirement intent retained")
		}
		if e = p.originalRetiringVM(vm); e != nil {
			return e
		}
		if p.state.Retired {
			return fmt.Errorf("retired original state cannot adopt a live VM")
		}
	}
	if vm.DeletionTimestamp == nil {
		if !slices.Contains(vm.Finalizers, retireControllerFinalizer) {
			return fmt.Errorf("original controller finalizer missing; no DELETE sent")
		}
		hash, e := p.archiveRetirement(ctx, vm)
		if e != nil {
			return e
		}
		p.state.RetireArchiveSHA256 = hash
		p.state.RetireMayHaveSent = true
		if e = p.save(); e != nil {
			return fmt.Errorf("retirement intent durability unconfirmed; no DELETE sent")
		}
		uid, rv := vm.UID, vm.ResourceVersion
		e = p.vms.Delete(ctx, vm.Name, metav1.DeleteOptions{Preconditions: &metav1.Preconditions{UID: &uid, ResourceVersion: &rv}})
		if e != nil && !apierrors.IsNotFound(e) {
			return fmt.Errorf("original VM DELETE outcome unknown; preserve retirement intent and retry")
		}
	}
	actual, e := p.vms.Get(ctx, p.wanted.Name, metav1.GetOptions{})
	if apierrors.IsNotFound(e) {
		return p.finishRetirement(ctx)
	}
	if e != nil {
		return fmt.Errorf("original VM stop not observable; retirement intent retained")
	}
	if actual.UID != p.state.VMUID {
		return fmt.Errorf("retirement refuses a same-name replacement UID")
	}
	// 有意不等待固定超时或把deleting视为退出；重复显式retire继续观察原UID。
	return fmt.Errorf("original VM is still stopping; retry retire with the same original state")
}

func (p *preparer) finishRetirement(ctx context.Context) error {
	if !p.state.RetireMayHaveSent {
		return fmt.Errorf("VM 404 without original retirement ticket is unknown")
	}
	if _, e := p.readRetirementArchive(); e != nil {
		return e
	}
	opts := metav1.ListOptions{Limit: 64}
	seen := map[string]bool{}
	for {
		list, e := p.core.Pods(p.state.Namespace).List(ctx, opts)
		if e != nil {
			return fmt.Errorf("original Pod termination inventory unknown")
		}
		for _, pod := range list.Items {
			for _, owner := range pod.OwnerReferences {
				if owner.UID == p.state.VMUID {
					return fmt.Errorf("original VM still has a Pod; retirement not confirmed")
				}
			}
		}
		if list.Continue == "" {
			break
		}
		if seen[list.Continue] {
			return fmt.Errorf("Pod inventory pagination repeated")
		}
		seen[list.Continue] = true
		opts.Continue = list.Continue
	}
	opts = metav1.ListOptions{Limit: 64}
	seen = map[string]bool{}
	nodes := 0
	for {
		list, e := p.core.Nodes().List(ctx, opts)
		if e != nil {
			return fmt.Errorf("all-Node retirement inventory unknown")
		}
		for _, node := range list.Items {
			nodes++
			if e := hostguard.InspectVMUnheld(&node, string(p.state.VMUID)); e != nil {
				return fmt.Errorf("original VM Node commitments remain unconfirmed: %w", e)
			}
		}
		if list.Continue == "" {
			break
		}
		if seen[list.Continue] {
			return fmt.Errorf("Node inventory pagination repeated")
		}
		seen[list.Continue] = true
		opts.Continue = list.Continue
	}
	if nodes == 0 {
		return fmt.Errorf("actual Node inventory absent; retirement not confirmed")
	}
	actual, e := p.vms.Get(ctx, p.wanted.Name, metav1.GetOptions{})
	if !apierrors.IsNotFound(e) {
		if e == nil && actual.UID != p.state.VMUID {
			return fmt.Errorf("retirement refuses a same-name replacement UID")
		}
		return fmt.Errorf("original VM 404 must remain fresh after Pod/Node checks")
	}
	p.state.Retired = true
	if e = p.save(); e != nil {
		return fmt.Errorf("retired state durability unconfirmed")
	}
	return nil
}

// Complete保留原bootstrap历史；退役意图之后不把它展示为当前ready。
func (p *preparer) deploymentOutput(action string) map[string]any {
	return map[string]any{"action": action, "vm_uid": p.state.VMUID, "secret_uid": p.state.SecretUID, "runtime_sha256": p.state.RuntimeSHA256, "bootstrap_ready": p.state.Complete && !p.state.RetireMayHaveSent, "original_bootstrap_complete": p.state.Complete, "retire_may_have_sent": p.state.RetireMayHaveSent, "retired": p.state.Retired, "retire_archive_sha256": p.state.RetireArchiveSHA256, "qualification_created": false, "E": 0}
}
