package main

import (
	"context"
	"encoding/json"
	vmv1 "github.com/neondatabase/autoscaling/neonvm/apis/neonvm/v1"
	vmfake "github.com/neondatabase/autoscaling/neonvm/client/clientset/versioned/fake"
	vmtyped "github.com/neondatabase/autoscaling/neonvm/client/clientset/versioned/typed/neonvm/v1"
	"github.com/neondatabase/autoscaling/pkg/dsga/journal"
	"github.com/neondatabase/autoscaling/pkg/dsga/resourceguard"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	kubefake "k8s.io/client-go/kubernetes/fake"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func renderUnit(t *testing.T) (*preparer, renderFiles, map[string][]byte) {
	t.Helper()
	vm, data := nativeUnit(t)
	guest := "example.invalid/OFFLINE-ONLY/guest@sha256:" + strings.Repeat("a", 64)
	runner := "example.invalid/OFFLINE-ONLY/runner@sha256:" + strings.Repeat("b", 64)
	kernel := "example.invalid/OFFLINE-ONLY/kernel@sha256:" + strings.Repeat("c", 64)
	vm.Spec.RunnerImage = &runner
	vm.Spec.Guest.KernelImage = &kernel
	vm.Spec.Guest.RootDisk.Image = guest
	vm.Spec.Guest.MemorySlotSize = resource.MustParse("1Gi")
	vm.Spec.Guest.MemorySlots = vmv1.MemorySlots{Min: 7, Use: 7, Max: 8}
	yes, no := true, false
	vm.Spec.Disks = []vmv1.Disk{{Name: "compute-config", MountPath: "/neonvm/config", ReadOnly: &yes, Watch: &no, DiskSource: vmv1.DiskSource{Secret: &corev1.SecretVolumeSource{SecretName: vm.Name + "-config", Items: []corev1.KeyToPath{{Key: "config.json", Path: "compute.json"}}}}}}
	native := []byte(`{"unit_only_Builder_bytes":"not-a-deployable-ELF-manifest"}`)
	var templates map[string]any
	require.NoError(t, json.Unmarshal(data[resourceguard.PolicyTemplatesSecretKey], &templates))
	for _, raw := range templates["templates"].([]any) {
		entry := raw.(map[string]any)
		if entry["asset"] == "dsga-native-birth.json" {
			entry["policy"].(map[string]any)["build_manifest_sha256"] = digest(native)
		}
	}
	policies, e := json.Marshal(templates)
	require.NoError(t, e)
	data[resourceguard.PolicyTemplatesSecretKey] = policies
	var source resourceguard.SourceConfig
	require.NoError(t, json.Unmarshal(data[resourceguard.ResourceSecretKey], &source))
	source.Config.VMUID = ""
	src, e := json.Marshal(source)
	require.NoError(t, e)
	var config map[string]any
	require.NoError(t, json.Unmarshal(data["config.json"], &config))
	config["spec"].(map[string]any)["dynamic_shared_buffers"].(map[string]any)["vm_uid"] = ""
	config["unit_preserved"] = map[string]any{"secret": "do-not-print-unit-credential", "array": []any{1, "two"}}
	cfg, e := json.Marshal(config)
	require.NoError(t, e)
	contract := renderBuildContract{ProtocolVersion: 1, Scope: "neon-pg17-trusted-runtime-build-v1", GuestImage: guest, RunnerImage: runner, KernelImage: kernel, PolicyTemplatesSHA256: digest(policies), NativeBuildSHA256: digest(native), ComputeConfigPath: "/neonvm/config/compute.json"}
	contractRaw, e := json.Marshal(contract)
	require.NoError(t, e)
	dir := t.TempDir()
	require.NoError(t, os.Chmod(dir, 0700))
	in := renderFiles{computeTemplate: filepath.Join(dir, "compute-template"), sourceTemplate: filepath.Join(dir, "source-template"), policies: filepath.Join(dir, "policies"), nativeBuild: filepath.Join(dir, "native"), contract: filepath.Join(dir, "contract"), outputDir: filepath.Join(dir, "rendered")}
	for f, b := range map[string][]byte{in.computeTemplate: cfg, in.sourceTemplate: src, in.policies: policies, in.nativeBuild: native, in.contract: contractRaw} {
		require.NoError(t, os.WriteFile(f, b, 0600))
	}
	vms := vmfake.NewSimpleClientset(vm)
	store, e := journal.NewStore(vms.NeonvmV1().VirtualMachines(vm.Namespace), journal.Binding{Namespace: vm.Namespace, Name: vm.Name, VMUID: vm.UID, Incarnation: vm.Spec.DSGABootstrap.Incarnation})
	require.NoError(t, e)
	_, e = store.Initialize(context.Background(), vm.ResourceVersion, "unit-bootstrap-owner")
	require.NoError(t, e)
	vms.ClearActions()
	wanted := vm.DeepCopy()
	wanted.UID = ""
	wanted.ResourceVersion = ""
	p := &preparer{core: kubefake.NewSimpleClientset().CoreV1(), vms: vms.NeonvmV1().VirtualMachines(vm.Namespace), wanted: wanted, state: retained{ProtocolVersion: 1, Scope: stateScope, VMUID: vm.UID, Namespace: vm.Namespace, Name: vm.Name}, statePath: filepath.Join(dir, "state")}
	return p, in, data
}
func TestRuntimeRenderBindsActualHeldUIDAndPreservesOriginalFields(t *testing.T) {
	p, in, _ := renderUnit(t)
	require.NoError(t, p.render(context.Background(), in))
	var source resourceguard.SourceConfig
	raw, e := os.ReadFile(filepath.Join(in.outputDir, resourceguard.ResourceSecretKey))
	require.NoError(t, e)
	require.NoError(t, json.Unmarshal(raw, &source))
	require.Equal(t, string(p.state.VMUID), source.Config.VMUID)
	cfg, e := os.ReadFile(filepath.Join(in.outputDir, "config.json"))
	require.NoError(t, e)
	var fields map[string]any
	require.NoError(t, json.Unmarshal(cfg, &fields))
	require.Equal(t, "do-not-print-unit-credential", fields["unit_preserved"].(map[string]any)["secret"])
	require.Equal(t, string(p.state.VMUID), fields["spec"].(map[string]any)["dynamic_shared_buffers"].(map[string]any)["vm_uid"])
	// 同一原输入可只读确认，但修改过的源不能覆盖已发布三文件。
	require.NoError(t, p.render(context.Background(), in))
	require.NotEmpty(t, p.state.SecretDataSHA256)
	for _, k := range []string{"config.json", resourceguard.ResourceSecretKey, resourceguard.PolicyTemplatesSecretKey} {
		st, e := os.Stat(filepath.Join(in.outputDir, k))
		require.NoError(t, e)
		require.Equal(t, os.FileMode(0600), st.Mode().Perm())
	}
	vm, e := p.vms.Get(context.Background(), p.wanted.Name, metav1.GetOptions{})
	require.NoError(t, e)
	require.False(t, vm.Spec.DSGABootstrap.Ready)
	s := secretFor(vm, map[string][]byte{})
	s.UID = "unit-api-secret-uid"
	s.ResourceVersion = "1"
	for _, key := range []string{"config.json", resourceguard.ResourceSecretKey, resourceguard.PolicyTemplatesSecretKey} {
		b, e := os.ReadFile(filepath.Join(in.outputDir, key))
		require.NoError(t, e)
		s.Data[key] = b
	}
	_, e = checkedRuntime(vm, s)
	require.NoError(t, e, "produced files must reach original complete Runtime library")
}
func TestRuntimeRenderRejectsDriftBeforePublishing(t *testing.T) {
	for _, name := range []string{"bound-source", "key-drift", "private-signing-key", "unknown-jwk", "policy-drift", "native-build-drift", "image-drift", "public-credential-file", "retained-data-drift"} {
		t.Run(name, func(t *testing.T) {
			p, in, _ := renderUnit(t)
			switch name {
			case "bound-source":
				b, e := os.ReadFile(in.sourceTemplate)
				require.NoError(t, e)
				var s resourceguard.SourceConfig
				require.NoError(t, json.Unmarshal(b, &s))
				s.Config.VMUID = "old-model-UID"
				b, e = json.Marshal(s)
				require.NoError(t, e)
				require.NoError(t, os.WriteFile(in.sourceTemplate, b, 0600))
			case "key-drift":
				b, e := os.ReadFile(in.computeTemplate)
				require.NoError(t, e)
				var s map[string]any
				require.NoError(t, json.Unmarshal(b, &s))
				s["compute_ctl_config"].(map[string]any)["jwks"].(map[string]any)["keys"].([]any)[0].(map[string]any)["x"] = "different"
				b, e = json.Marshal(s)
				require.NoError(t, e)
				require.NoError(t, os.WriteFile(in.computeTemplate, b, 0600))
			case "private-signing-key", "unknown-jwk":
				b, e := os.ReadFile(in.computeTemplate)
				require.NoError(t, e)
				var cfg map[string]any
				require.NoError(t, json.Unmarshal(b, &cfg))
				field := "d"
				if name == "unknown-jwk" {
					field = "secret_seed"
				}
				cfg["compute_ctl_config"].(map[string]any)["jwks"].(map[string]any)["keys"].([]any)[0].(map[string]any)[field] = "do-not-forward-private-signing-seed"
				b, e = json.Marshal(cfg)
				require.NoError(t, e)
				require.NoError(t, os.WriteFile(in.computeTemplate, b, 0600))
			case "policy-drift":
				f, e := os.OpenFile(in.policies, os.O_APPEND|os.O_WRONLY, 0600)
				require.NoError(t, e)
				_, e = f.WriteString(" ")
				require.NoError(t, e)
				require.NoError(t, f.Close())
			case "native-build-drift":
				require.NoError(t, os.WriteFile(in.nativeBuild, []byte("changed"), 0600))
			case "image-drift":
				b, e := os.ReadFile(in.contract)
				require.NoError(t, e)
				var c renderBuildContract
				require.NoError(t, json.Unmarshal(b, &c))
				c.RunnerImage += "changed"
				b, e = json.Marshal(c)
				require.NoError(t, e)
				require.NoError(t, os.WriteFile(in.contract, b, 0600))
			case "public-credential-file":
				require.NoError(t, os.Chmod(in.computeTemplate, 0644))
			case "retained-data-drift":
				p.state.SecretDataSHA256 = strings.Repeat("f", 64)
			}
			require.Error(t, p.render(context.Background(), in))
			_, e := os.Lstat(in.outputDir)
			require.True(t, os.IsNotExist(e))
			vm, e := p.vms.Get(context.Background(), p.wanted.Name, metav1.GetOptions{})
			require.NoError(t, e)
			require.False(t, vm.Spec.DSGABootstrap.Ready)
			require.False(t, p.state.SecretCreateMayHaveSent)
			require.False(t, p.state.ReleaseMayHaveSent)
		})
	}
}

// 模拟同UID的真实两次API快照：第一次Get匹配原manifest，journal Load返回的
// 第二次快照已漂移Max。不能只靠第一次Get或稍后seal再补救原输入绑定。
type renderSecondSnapshot struct {
	vmtyped.VirtualMachineInterface
	calls int
}

func (s *renderSecondSnapshot) Get(ctx context.Context, name string, opt metav1.GetOptions) (*vmv1.VirtualMachine, error) {
	v, e := s.VirtualMachineInterface.Get(ctx, name, opt)
	s.calls++
	if e == nil && s.calls == 2 {
		v = v.DeepCopy()
		v.Spec.Guest.MemorySlots.Max = 9
	}
	return v, e
}
func TestRuntimeRenderRejectsSameUIDSecondSnapshotDrift(t *testing.T) {
	p, in, _ := renderUnit(t)
	reader := &renderSecondSnapshot{VirtualMachineInterface: p.vms}
	p.vms = reader
	require.ErrorContains(t, p.render(context.Background(), in), "original VM immutable creation template differs")
	require.Equal(t, 2, reader.calls)
	_, e := os.Lstat(in.outputDir)
	require.True(t, os.IsNotExist(e))
	require.Empty(t, p.state.SecretDataSHA256)
}
