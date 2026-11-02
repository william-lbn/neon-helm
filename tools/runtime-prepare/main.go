// runtime-prepare只完成受管VM首次部署的原UID/Runtime封存，不运行控制面服务、
// 不生成资格、不写PG/cgroup/QMP，也不在来源丢失后自动重建原对象。
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"sort"
	"time"

	vmv1 "github.com/neondatabase/autoscaling/neonvm/apis/neonvm/v1"
	vmclient "github.com/neondatabase/autoscaling/neonvm/client/clientset/versioned"
	vmtyped "github.com/neondatabase/autoscaling/neonvm/client/clientset/versioned/typed/neonvm/v1"
	control "github.com/neondatabase/autoscaling/pkg/api/dsga"
	"github.com/neondatabase/autoscaling/pkg/dsga/bootstrap"
	"github.com/neondatabase/autoscaling/pkg/dsga/journal"
	"github.com/neondatabase/autoscaling/pkg/dsga/resourceguard"
	"golang.org/x/sys/unix"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/equality"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes"
	coretyped "k8s.io/client-go/kubernetes/typed/core/v1"
	"k8s.io/client-go/tools/clientcmd"
)

type retained struct {
	ProtocolVersion         uint32    `json:"protocol_version"`
	Scope                   string    `json:"scope"`
	ManifestSHA256          string    `json:"manifest_sha256"`
	Namespace               string    `json:"namespace"`
	Name                    string    `json:"name"`
	VMCreateMayHaveSent     bool      `json:"VM_create_may_have_sent"`
	VMUID                   types.UID `json:"vm_uid,omitempty"`
	SecretCreateMayHaveSent bool      `json:"secret_create_may_have_sent"`
	SecretDataSHA256        string    `json:"secret_data_sha256,omitempty"`
	SecretUID               types.UID `json:"secret_uid,omitempty"`
	ReleaseMayHaveSent      bool      `json:"release_may_have_sent"`
	Complete                bool      `json:"complete"`
	RuntimeSHA256           string    `json:"runtime_sha256,omitempty"`
	RetireMayHaveSent       bool      `json:"retire_may_have_sent,omitempty"`
	RetireArchiveSHA256     string    `json:"retire_archive_sha256,omitempty"`
	Retired                 bool      `json:"retired,omitempty"`
}
type files struct{ config, resource, policies string }
type preparer struct {
	core      coretyped.CoreV1Interface
	vms       vmtyped.VirtualMachineInterface
	wanted    *vmv1.VirtualMachine
	state     retained
	statePath string
}

const stateScope = "neon-runtime-original-deployment-v1"

func digest(b []byte) string { v := sha256.Sum256(b); return hex.EncodeToString(v[:]) }
func readBounded(path string, maximum int64) ([]byte, error) {
	f, e := os.Open(path)
	if e != nil {
		return nil, fmt.Errorf("required input unavailable")
	}
	defer f.Close()
	b, e := io.ReadAll(io.LimitReader(f, maximum+1))
	if e != nil || len(b) == 0 || int64(len(b)) > maximum {
		return nil, fmt.Errorf("input outside fixed size bound")
	}
	return b, nil
}
func manifest(path string) (*vmv1.VirtualMachine, string, error) {
	b, e := readBounded(path, 1<<20)
	if e != nil {
		return nil, "", e
	}
	var v vmv1.VirtualMachine
	if e = json.Unmarshal(b, &v); e != nil {
		return nil, "", fmt.Errorf("invalid original VM JSON")
	}
	if v.Kind != "VirtualMachine" || v.APIVersion != vmv1.SchemeGroupVersion.String() || v.Namespace == "" || v.Name == "" || v.UID != "" || v.ResourceVersion != "" || v.DeletionTimestamp != nil || v.Spec.DSGABootstrap == nil {
		return nil, "", fmt.Errorf("original held VM manifest required")
	}
	birth := v.Spec.DSGABootstrap
	if birth.ProtocolVersion != 1 || birth.Ready || birth.VMUID != "" || birth.ConfigSecretUID != "" || control.ValidateIncarnation(birth.Incarnation) != nil || control.ValidateID(birth.ComputeInstanceID, "Compute") != nil || control.Managed(v.Annotations) {
		return nil, "", fmt.Errorf("manifest must be from CREATE held, without preclaimed UID/journal")
	}
	if _, e = v.ValidateCreate(); e != nil {
		return nil, "", fmt.Errorf("VM manifest violates original source API")
	}
	// 复用已授权三节点范围；每个OR term均必须精确约束，不能只靠可漂移pool标签。
	if v.Spec.Affinity == nil || v.Spec.Affinity.NodeAffinity == nil || v.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution == nil {
		return nil, "", fmt.Errorf("explicit three-worker affinity required")
	}
	terms := v.Spec.Affinity.NodeAffinity.RequiredDuringSchedulingIgnoredDuringExecution.NodeSelectorTerms
	if len(terms) == 0 {
		return nil, "", fmt.Errorf("empty Node affinity")
	}
	for _, term := range terms {
		known := false
		for _, m := range term.MatchExpressions {
			if m.Key == "kubernetes.io/hostname" && m.Operator == corev1.NodeSelectorOpIn {
				names := append([]string(nil), m.Values...)
				sort.Strings(names)
				known = reflect.DeepEqual(names, []string{"worker-117", "worker-118", "worker-119"})
			}
		}
		if !known {
			return nil, "", fmt.Errorf("every scheduling term must exclude116 and bind117/118/119")
		}
	}
	slot, exact := v.Spec.Guest.MemorySlotSize.AsInt64()
	cpus := v.Spec.Guest.CPUs
	slots := v.Spec.Guest.MemorySlots
	if !exact || slot != 1<<30 || slots.Min != 7 || slots.Use != 7 || slots.Max != 8 || cpus.Min != 2000 || cpus.Use != 2000 || cpus.Max != 2000 || v.Spec.CpuScalingMode == nil || *v.Spec.CpuScalingMode != vmv1.CpuScalingModeSysfs {
		return nil, "", fmt.Errorf("trusted original CPU2/min7/use7/max8 geometry required")
	}
	pinned := regexp.MustCompile(`@sha256:[0-9a-f]{64}$`)
	if v.Spec.RunnerImage == nil || v.Spec.Guest.KernelImage == nil || !pinned.MatchString(*v.Spec.RunnerImage) || !pinned.MatchString(*v.Spec.Guest.KernelImage) || !pinned.MatchString(v.Spec.Guest.RootDisk.Image) {
		return nil, "", fmt.Errorf("actual Runner/kernel/Guest image digests required")
	}
	canonical, e := json.Marshal(v)
	if e != nil {
		return nil, "", e
	}
	return &v, digest(canonical), nil
}
func (p *preparer) save() error {
	b, e := json.Marshal(p.state)
	if e != nil {
		return e
	}
	dir := filepath.Dir(p.statePath)
	f, e := os.CreateTemp(dir, ".runtime-state-")
	if e != nil {
		return fmt.Errorf("deployment state write unavailable")
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if _, e = f.Write(append(b, '\n')); e == nil {
		e = f.Sync()
	}
	closeErr := f.Close()
	if e != nil || closeErr != nil {
		return fmt.Errorf("deployment state durability unconfirmed")
	}
	if e = os.Rename(tmp, p.statePath); e != nil {
		return fmt.Errorf("deployment state replace unconfirmed")
	}
	d, e := os.Open(dir)
	if e != nil {
		return e
	}
	defer d.Close()
	return d.Sync()
}
func originalVM(wanted, got *vmv1.VirtualMachine, expected types.UID) error {
	if got == nil || got.UID == "" || got.ResourceVersion == "" || got.DeletionTimestamp != nil || got.Namespace != wanted.Namespace || got.Name != wanted.Name || expected != "" && got.UID != expected {
		return fmt.Errorf("original VM identity unavailable or replaced")
	}
	a := got.DeepCopy()
	b := a.Spec.DSGABootstrap
	w := wanted.Spec.DSGABootstrap
	if b == nil || b.ProtocolVersion != w.ProtocolVersion || b.Incarnation != w.Incarnation || b.ComputeInstanceID != w.ComputeInstanceID {
		return fmt.Errorf("original VM birth differs")
	}
	if b.Ready {
		if b.VMUID != string(got.UID) || b.ConfigSecretUID == "" {
			return fmt.Errorf("ready VM original UID missing")
		}
		b.Ready = false
		b.VMUID = ""
		b.ConfigSecretUID = ""
	}
	if !equality.Semantic.DeepEqual(a.Spec, wanted.Spec) {
		return fmt.Errorf("original VM immutable creation template differs")
	}
	for k, v := range wanted.Labels {
		if got.Labels[k] != v {
			return fmt.Errorf("original VM ownership label changed")
		}
	}
	return nil
}
func (p *preparer) held(ctx context.Context, create bool) (*vmv1.VirtualMachine, *journal.Store, error) {
	if p.state.RetireMayHaveSent || p.state.Retired {
		return nil, nil, fmt.Errorf("original deployment has a retirement intent; hold/render/seal and live recovery are forbidden")
	}
	if p.state.VMCreateMayHaveSent && p.state.VMUID == "" {
		return nil, nil, fmt.Errorf("original VM CREATE UID unconfirmed; same-name adoption forbidden")
	}
	if !create && p.state.VMUID == "" {
		return nil, nil, fmt.Errorf("original held UID must first be durably confirmed by hold")
	}
	vm, e := p.vms.Get(ctx, p.wanted.Name, metav1.GetOptions{})
	if apierrors.IsNotFound(e) && create && p.state.VMUID == "" && !p.state.VMCreateMayHaveSent {
		p.state.VMCreateMayHaveSent = true
		if e = p.save(); e != nil {
			return nil, nil, e
		}
		vm, e = p.vms.Create(ctx, p.wanted.DeepCopy(), metav1.CreateOptions{})
		if e != nil {
			return nil, nil, fmt.Errorf("VM CREATE unconfirmed; retain original state and inspect")
		}
		if vm.UID == "" {
			return nil, nil, fmt.Errorf("VM CREATE original UID absent")
		}
		p.state.VMUID = vm.UID
		if e = p.save(); e != nil {
			return nil, nil, e
		}
		vm, e = p.vms.Get(ctx, p.wanted.Name, metav1.GetOptions{})
	}
	if e != nil {
		return nil, nil, fmt.Errorf("original VM read unavailable; automatic replacement forbidden")
	}
	if e = originalVM(p.wanted, vm, p.state.VMUID); e != nil {
		return nil, nil, e
	}
	if p.state.Complete && (!vm.Spec.DSGABootstrap.Ready || vm.Spec.DSGABootstrap.ConfigSecretUID != string(p.state.SecretUID)) {
		return nil, nil, fmt.Errorf("original completed bootstrap identity changed")
	}
	if p.state.VMUID == "" {
		p.state.VMUID = vm.UID
		if e = p.save(); e != nil {
			return nil, nil, e
		}
	}
	store, e := journal.NewStore(p.vms, journal.Binding{Namespace: vm.Namespace, Name: vm.Name, VMUID: vm.UID, Incarnation: vm.Spec.DSGABootstrap.Incarnation})
	if e != nil {
		return nil, nil, e
	}
	if !control.Managed(vm.Annotations) {
		if !create || vm.Spec.DSGABootstrap.Ready {
			return nil, nil, fmt.Errorf("original journal missing; no automatic runtime reset")
		}
		snapshot, initErr := store.Initialize(ctx, vm.ResourceVersion, "bootstrap-"+vm.Spec.DSGABootstrap.Incarnation)
		if initErr != nil {
			return nil, nil, fmt.Errorf("original held journal initialization unconfirmed")
		}
		vm = snapshot.VirtualMachine()
	} else {
		snapshot, load := store.Load(ctx)
		if load != nil {
			return nil, nil, fmt.Errorf("original journal cannot be decoded")
		}
		vm = snapshot.VirtualMachine()
	}
	return vm, store, nil
}
func dataFrom(files files) (map[string][]byte, error) {
	out := map[string][]byte{}
	for key, path := range map[string]string{"config.json": files.config, resourceguard.ResourceSecretKey: files.resource, resourceguard.PolicyTemplatesSecretKey: files.policies} {
		max := int64(16 << 10)
		if key == "config.json" {
			max = 1 << 20
		}
		b, e := readBounded(path, max)
		if e != nil {
			return nil, e
		}
		out[key] = b
	}
	total := 0
	for _, b := range out {
		total += len(b)
	}
	if total > 1<<20 {
		return nil, fmt.Errorf("complete Runtime Secret exceeds Kubernetes bound")
	}
	return out, nil
}
func (p *preparer) inspect(ctx context.Context) error {
	vm, _, e := p.held(ctx, false)
	if e != nil {
		return e
	}
	if p.state.SecretUID == "" {
		return nil
	}
	secret, e := p.core.Secrets(vm.Namespace).Get(ctx, vm.Name+"-config", metav1.GetOptions{})
	if e != nil {
		return fmt.Errorf("original Runtime Secret not observable")
	}
	if e = originalSecret(vm, secret, secret.Data, p.state.SecretUID); e != nil {
		return e
	}
	if dataHash(secret.Data) != p.state.SecretDataSHA256 {
		return fmt.Errorf("retained Runtime Secret data differs")
	}
	if p.state.Complete {
		if e = bootstrap.CheckReady(vm, secret, false); e != nil {
			return fmt.Errorf("actual original bootstrap no longer confirmed")
		}
	}
	return nil
}
func dataHash(data map[string][]byte) string { b, _ := json.Marshal(data); return digest(b) }
func secretFor(vm *vmv1.VirtualMachine, data map[string][]byte) *corev1.Secret {
	yes := true
	labels := map[string]string{}
	for _, k := range []string{"neon-control/project-id", "neon-control/endpoint-id"} {
		if v, ok := vm.Labels[k]; ok {
			labels[k] = v
		}
	}
	return &corev1.Secret{ObjectMeta: metav1.ObjectMeta{Name: vm.Name + "-config", Namespace: vm.Namespace, Labels: labels, OwnerReferences: []metav1.OwnerReference{{APIVersion: vmv1.SchemeGroupVersion.String(), Kind: "VirtualMachine", Name: vm.Name, UID: vm.UID, Controller: &yes, BlockOwnerDeletion: &yes}}}, Immutable: &yes, Data: data}
}
func originalSecret(vm *vmv1.VirtualMachine, s *corev1.Secret, data map[string][]byte, expected types.UID) error {
	if s == nil || s.Namespace != vm.Namespace || s.Name != vm.Name+"-config" || s.UID == "" || s.ResourceVersion == "" || s.DeletionTimestamp != nil || s.Immutable == nil || !*s.Immutable || expected != "" && s.UID != expected || !reflect.DeepEqual(s.Data, data) || len(s.StringData) != 0 {
		return fmt.Errorf("original immutable Runtime Secret differs or was replaced")
	}
	owner := metav1.GetControllerOf(s)
	if owner == nil || owner.APIVersion != vmv1.SchemeGroupVersion.String() || owner.Kind != "VirtualMachine" || owner.Name != vm.Name || owner.UID != vm.UID {
		return fmt.Errorf("Runtime Secret lacks original VM owner UID")
	}
	return nil
}
func checkedRuntime(vm *vmv1.VirtualMachine, s *corev1.Secret) ([]byte, error) {
	// 预检使用的仍是实际API分配UID；只构造预期CAS投影，不写VM/生成nonce或资格。
	preview := vm.DeepCopy()
	preview.Spec.DSGABootstrap.Ready = true
	preview.Spec.DSGABootstrap.VMUID = string(vm.UID)
	preview.Spec.DSGABootstrap.ConfigSecretUID = string(s.UID)
	doc, e := bootstrap.Runtime(preview, s)
	if e != nil {
		return nil, fmt.Errorf("original Runtime/Compute/key/budget/template contract rejected")
	}
	source, e := doc.Source()
	if e != nil || source.Config.ExecutionModel != resourceguard.TrustedControllerExecutionModel || doc.ProtocolVersion != 2 {
		return nil, fmt.Errorf("original sealed trusted-controller Runtime v2 required")
	}
	b, e := json.Marshal(doc)
	if e != nil {
		return nil, e
	}
	assets, e := resourceguard.RenderRuntimePolicyAssets(b)
	if e != nil {
		return nil, fmt.Errorf("complete original policy render rejected")
	}
	assets[resourceguard.RuntimeResourceAssetName] = b
	var capability struct {
		ArrayHelperProtocolVersion uint32 `json:"array_helper_protocol_version"`
	}
	if json.Unmarshal(assets["dsga-native-birth.json"], &capability) != nil || capability.ArrayHelperProtocolVersion != 1 {
		return nil, fmt.Errorf("original helper ABI1 normal Runtime required")
	}
	req, e := resourceguard.DeriveRuntimeBootRequirements(b, assets)
	if e != nil || !req.Enabled() || req.BootMemoryUpperBoundBytes() < 512<<20 {
		return nil, fmt.Errorf("original initial/memory2 boot policy missing")
	}
	return b, nil
}
func (p *preparer) seal(ctx context.Context, f files) ([]byte, error) {
	vm, store, e := p.held(ctx, false)
	if e != nil {
		return nil, e
	}
	data, e := dataFrom(f)
	if e != nil {
		return nil, e
	}
	var source resourceguard.SourceConfig
	if json.Unmarshal(data[resourceguard.ResourceSecretKey], &source) != nil || source.Config.ExecutionModel != resourceguard.TrustedControllerExecutionModel || source.Config.VMUID != string(vm.UID) || source.Config.ComputeInstanceID != vm.Spec.DSGABootstrap.ComputeInstanceID {
		return nil, fmt.Errorf("actual original VM-bound resource source required")
	}
	publicKey, e := originalPublicControlKey(data["config.json"])
	if e != nil {
		return nil, e
	}
	if publicKey != source.ControlPublicKey {
		return nil, fmt.Errorf("original credential public keys differ")
	}
	hash := dataHash(data)
	if p.state.SecretDataSHA256 != "" && p.state.SecretDataSHA256 != hash {
		return nil, fmt.Errorf("original sealed Runtime bytes changed")
	}
	p.state.SecretDataSHA256 = hash
	if p.state.SecretCreateMayHaveSent && p.state.SecretUID == "" {
		return nil, fmt.Errorf("original Secret CREATE UID unconfirmed; same-name adoption forbidden")
	}
	secrets := p.core.Secrets(vm.Namespace)
	s, e := secrets.Get(ctx, vm.Name+"-config", metav1.GetOptions{})
	if apierrors.IsNotFound(e) && p.state.SecretUID == "" && !p.state.SecretCreateMayHaveSent && !vm.Spec.DSGABootstrap.Ready {
		p.state.SecretCreateMayHaveSent = true
		if e = p.save(); e != nil {
			return nil, e
		}
		s, e = secrets.Create(ctx, secretFor(vm, data), metav1.CreateOptions{})
		if e != nil {
			return nil, fmt.Errorf("Runtime Secret CREATE unconfirmed; original state retained")
		}
		if s.UID == "" {
			return nil, fmt.Errorf("Runtime Secret actual UID missing")
		}
		p.state.SecretUID = s.UID
		if e = p.save(); e != nil {
			return nil, e
		}
		s, e = secrets.Get(ctx, s.Name, metav1.GetOptions{})
	}
	if e != nil {
		return nil, fmt.Errorf("original Runtime Secret unavailable; automatic replacement forbidden")
	}
	if e = originalSecret(vm, s, data, p.state.SecretUID); e != nil {
		return nil, e
	}
	if p.state.SecretUID == "" {
		p.state.SecretUID = s.UID
		if e = p.save(); e != nil {
			return nil, e
		}
	}
	runtime, e := checkedRuntime(vm, s)
	if e != nil {
		return nil, e
	}
	snap, e := store.Load(ctx)
	if e != nil {
		return nil, fmt.Errorf("original journal read unavailable before release")
	}
	if e = originalVM(p.wanted, snap.VirtualMachine(), p.state.VMUID); e != nil {
		return nil, e
	}
	if !snap.VirtualMachine().Spec.DSGABootstrap.Ready {
		p.state.ReleaseMayHaveSent = true
		if e = p.save(); e != nil {
			return nil, e
		}
		if _, e = store.ReleaseBootstrap(ctx, snap.ResourceVersion(), s.UID); e != nil {
			return nil, fmt.Errorf("original bootstrap release CAS unconfirmed; inspect retained state")
		}
	}
	actual, e := p.vms.Get(ctx, vm.Name, metav1.GetOptions{})
	if e != nil {
		return nil, fmt.Errorf("original released VM read unavailable")
	}
	actualSecret, e := secrets.Get(ctx, s.Name, metav1.GetOptions{})
	if e != nil {
		return nil, fmt.Errorf("original released Secret read unavailable")
	}
	if e = originalVM(p.wanted, actual, p.state.VMUID); e != nil {
		return nil, e
	}
	if e = originalSecret(actual, actualSecret, data, p.state.SecretUID); e != nil {
		return nil, e
	}
	if e = bootstrap.CheckReady(actual, actualSecret, false); e != nil {
		return nil, fmt.Errorf("actual original UID bootstrap is not ready")
	}
	if !bytes.Equal(s.Data[resourceguard.ResourceSecretKey], actualSecret.Data[resourceguard.ResourceSecretKey]) {
		return nil, fmt.Errorf("Runtime source changed after release")
	}
	p.state.Complete = true
	p.state.RuntimeSHA256 = digest(runtime)
	if e = p.save(); e != nil {
		return nil, e
	}
	return runtime, nil
}
func run() error {
	action := flag.String("action", "inspect", "hold, render, seal, inspect or retire; mutations require explicit selection")
	vmFile := flag.String("vm-json", "", "original held VM JSON from Helm")
	stateFile := flag.String("state", "", "private persistent /data original deployment state")
	kubeconfig := flag.String("kubeconfig", "", "existing Kubernetes config; never printed")
	configFile := flag.String("compute-config", "", "actual VM-bound Compute config JSON")
	resourceFile := flag.String("resource-config", "", "actual VM-bound resource source JSON")
	policyFile := flag.String("policy-templates", "", "original immutable complete policy template JSON")
	nativeBuildFile := flag.String("native-build-manifest", "", "original actual Builder NativeBirth manifest")
	buildContractFile := flag.String("build-contract", "", "original pinned image/template/native build index")
	renderOutputDir := flag.String("render-output-dir", "", "private new directory for the three original bound inputs")
	flag.Parse()
	if *action != "hold" && *action != "render" && *action != "seal" && *action != "inspect" && *action != "retire" {
		return fmt.Errorf("unsupported fixed deployment action")
	}
	if !filepath.IsAbs(*stateFile) || filepath.Clean(*stateFile) != *stateFile || *vmFile == "" || *kubeconfig == "" {
		return fmt.Errorf("original VM/state/kubeconfig inputs required")
	}
	v, sha, e := manifest(*vmFile)
	if e != nil {
		return e
	}
	dir := filepath.Dir(*stateFile)
	if e = os.MkdirAll(dir, 0700); e != nil {
		return fmt.Errorf("private deployment state directory unavailable")
	}
	st, e := os.Lstat(dir)
	if e != nil || !st.IsDir() || st.Mode()&0077 != 0 {
		return fmt.Errorf("deployment state directory must be private")
	}
	fd, e := unix.Open(*stateFile+".lock", unix.O_CREAT|unix.O_RDWR|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0600)
	if e != nil {
		return fmt.Errorf("deployment original lock unavailable")
	}
	defer unix.Close(fd)
	if e = unix.Flock(fd, unix.LOCK_EX|unix.LOCK_NB); e != nil {
		return fmt.Errorf("original deployment is already running")
	}
	state := retained{ProtocolVersion: 1, Scope: stateScope, ManifestSHA256: sha, Namespace: v.Namespace, Name: v.Name}
	if info, statErr := os.Lstat(*stateFile); statErr == nil {
		if !info.Mode().IsRegular() || info.Mode()&0077 != 0 {
			return fmt.Errorf("original deployment state must be private regular file")
		}
		b, read := readBounded(*stateFile, 64<<10)
		if read != nil || control.UnmarshalObject(b, &state) != nil || state.ProtocolVersion != 1 || state.Scope != stateScope || state.ManifestSHA256 != sha || state.Namespace != v.Namespace || state.Name != v.Name {
			return fmt.Errorf("original deployment state belongs to another plan")
		}
	} else if !os.IsNotExist(statErr) {
		return fmt.Errorf("original deployment state unreadable")
	} else if *action != "hold" {
		return fmt.Errorf("original deployment state absent; hold is explicit first action")
	}
	if e = checkRetirementState(state); e != nil {
		return e
	}
	if state.RetireMayHaveSent && (*action == "hold" || *action == "render" || *action == "seal") {
		return fmt.Errorf("original deployment retirement is irreversible; use a new state/Compute/incarnation for a new Guest")
	}
	cfg, e := clientcmd.BuildConfigFromFlags("", *kubeconfig)
	if e != nil {
		return fmt.Errorf("existing Kubernetes configuration invalid")
	}
	if cfg.Insecure || len(cfg.Host) < 8 || cfg.Host[:8] != "https://" {
		return fmt.Errorf("authenticated original HTTPS Kubernetes API required")
	}
	cfg.Timeout = 10 * time.Second
	core, e := kubernetes.NewForConfig(cfg)
	if e != nil {
		return fmt.Errorf("Kubernetes client unavailable")
	}
	vms, e := vmclient.NewForConfig(cfg)
	if e != nil {
		return fmt.Errorf("original VM client unavailable")
	}
	p := &preparer{core: core.CoreV1(), vms: vms.NeonvmV1().VirtualMachines(v.Namespace), wanted: v, state: state, statePath: *stateFile}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	switch *action {
	case "hold":
		if e = p.save(); e == nil {
			_, _, e = p.held(ctx, true)
		}
	case "render":
		e = p.render(ctx, renderFiles{*configFile, *resourceFile, *policyFile, *nativeBuildFile, *buildContractFile, *renderOutputDir})
	case "seal":
		_, e = p.seal(ctx, files{*configFile, *resourceFile, *policyFile})
	case "retire":
		e = p.retire(ctx)
	case "inspect":
		if p.state.RetireMayHaveSent {
			e = p.verifyRetirementArchive()
		} else {
			e = p.inspect(ctx)
		}
	}
	if e != nil {
		return e
	}
	return json.NewEncoder(os.Stdout).Encode(p.deploymentOutput(*action))
}
func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, "Runtime prepare:", e)
		os.Exit(1)
	}
}
