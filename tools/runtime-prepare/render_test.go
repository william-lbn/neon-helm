package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	vmv1 "github.com/neondatabase/autoscaling/neonvm/apis/neonvm/v1"
	vmfake "github.com/neondatabase/autoscaling/neonvm/client/clientset/versioned/fake"
	vmtyped "github.com/neondatabase/autoscaling/neonvm/client/clientset/versioned/typed/neonvm/v1"
	"github.com/neondatabase/autoscaling/pkg/dsga/journal"
	"github.com/neondatabase/autoscaling/pkg/dsga/resourceguard"
	"github.com/stretchr/testify/require"
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
	native := renderMajorNativeUnit(t, 17, true)
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
	contract := renderBuildContract{ProtocolVersion: 1, Scope: "neon-pg17-trusted-runtime-build-v1", GuestImage: guest, RunnerImage: runner, KernelImage: kernel, PolicyTemplatesSHA256: digest(policies), NativeBuildSHA256: digest(native), ComputeConfigPath: "/neonvm/config/compute-public.json"}
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
	for _, name := range []string{"bound-source", "key-drift", "private-signing-key", "unknown-jwk", "policy-drift", "native-build-drift", "image-drift", "public-credential-file", "retained-data-drift", "legacy-disk", "legacy-env", "public-config-path"} {
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
			case "legacy-disk":
				p.wanted.Spec.Disks = []vmv1.Disk{{Name: "forbidden-config", MountPath: "/neonvm/config"}}
				_, e := renderBootstrapFiles(p.wantedWithHeldIdentityForTest(), in)
				require.ErrorContains(t, e, "fixed runtime forbids legacy boot inputs")
				return
			case "legacy-env":
				p.wanted.Spec.Guest.Env = []vmv1.EnvVar{{Name: "UNDECLARED", Value: "input"}}
				_, e := renderBootstrapFiles(p.wantedWithHeldIdentityForTest(), in)
				require.ErrorContains(t, e, "fixed runtime forbids legacy boot inputs")
				return
			case "public-config-path":
				b, e := os.ReadFile(in.contract)
				require.NoError(t, e)
				var c renderBuildContract
				require.NoError(t, json.Unmarshal(b, &c))
				c.ComputeConfigPath = "/other/compute.json"
				b, e = json.Marshal(c)
				require.NoError(t, e)
				require.NoError(t, os.WriteFile(in.contract, b, 0600))
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

func (p *preparer) wantedWithHeldIdentityForTest() *vmv1.VirtualMachine {
	v := p.wanted.DeepCopy()
	v.UID = p.state.VMUID
	v.ResourceVersion = "unit-held-rv"
	return v
}

// 这些是假ELF引用的离线契约夹具；不声称18内核、Collector、normal或K8s通过。
func renderMajorNativeUnit(t *testing.T, major uint32, closure bool) []byte {
	t.Helper()
	m := map[string]any{"protocol_version": 1, "scope": "neon-native-pre-main-default-loader-v1", "pg_major": major,
		"launch_path": "/usr/local/bin/postgres", "postgres_path": "/usr/local/bin/postgres", "interpreter_path": "/lib/OFFLINE-only-loader",
		"files":        []any{map[string]any{"path": "/lib/OFFLINE-only-loader", "sha256": strings.Repeat("e", 64)}, map[string]any{"path": "/usr/local/bin/postgres", "sha256": strings.Repeat("f", 64)}},
		"array_helper": map[string]any{"protocol_version": 1, "path": "/neonvm/bin/neon-dsga-array-populate", "sha256": strings.Repeat("ab", 32)}}
	if closure {
		m["runtime_closure"] = map[string]any{"protocol_version": 1, "system_manifest_sha256": strings.Repeat("d", 64)}
	}
	raw, e := json.Marshal(m)
	require.NoError(t, e)
	return raw
}

func renderMajorFixture(t *testing.T, major uint32) (*preparer, renderFiles) {
	t.Helper()
	p, in, _ := renderUnit(t)
	if major == 18 {
		p.wanted.Annotations = map[string]string{"neon-control/postgres-major": "18"}
		live, e := p.vms.Get(context.Background(), p.wanted.Name, metav1.GetOptions{})
		require.NoError(t, e)
		if live.Annotations == nil {
			live.Annotations = map[string]string{}
		}
		live.Annotations["neon-control/postgres-major"] = "18"
		_, e = p.vms.Update(context.Background(), live, metav1.UpdateOptions{})
		require.NoError(t, e)
	}
	native := renderMajorNativeUnit(t, major, true)
	require.NoError(t, os.WriteFile(in.nativeBuild, native, 0600))
	renderMajorRewriteContract(t, in, major)
	return p, in
}
func renderMajorRewriteContract(t *testing.T, in renderFiles, major uint32) {
	t.Helper()
	native, e := os.ReadFile(in.nativeBuild)
	require.NoError(t, e)
	raw, e := os.ReadFile(in.policies)
	require.NoError(t, e)
	var templates map[string]any
	require.NoError(t, json.Unmarshal(raw, &templates))
	for _, v := range templates["templates"].([]any) {
		entry := v.(map[string]any)
		if entry["asset"] == "dsga-native-birth.json" {
			policy := entry["policy"].(map[string]any)
			policy["pg_major"] = major
			policy["build_manifest_sha256"] = digest(native)
		}
	}
	policies, e := json.Marshal(templates)
	require.NoError(t, e)
	require.NoError(t, os.WriteFile(in.policies, policies, 0600))
	raw, e = os.ReadFile(in.contract)
	require.NoError(t, e)
	var c renderBuildContract
	require.NoError(t, json.Unmarshal(raw, &c))
	c.Scope = fmt.Sprintf("neon-pg%d-trusted-runtime-build-v1", major)
	c.NativeBuildSHA256 = digest(native)
	c.PolicyTemplatesSHA256 = digest(policies)
	raw, e = json.Marshal(c)
	require.NoError(t, e)
	require.NoError(t, os.WriteFile(in.contract, raw, 0600))
}

func TestRuntimeRenderExplicitMajor18Contract(t *testing.T) {
	p, in := renderMajorFixture(t, 18)
	require.NoError(t, p.render(context.Background(), in))
	require.False(t, p.state.SecretCreateMayHaveSent)
	require.False(t, p.state.ReleaseMayHaveSent)
	vm, e := p.vms.Get(context.Background(), p.wanted.Name, metav1.GetOptions{})
	require.NoError(t, e)
	require.Equal(t, "18", vm.Annotations["neon-control/postgres-major"])
	s := secretFor(vm, map[string][]byte{})
	s.UID = "OFFLINE-actual-api-config-uid"
	s.ResourceVersion = "1"
	for _, key := range []string{"config.json", resourceguard.ResourceSecretKey, resourceguard.PolicyTemplatesSecretKey} {
		raw, e := os.ReadFile(filepath.Join(in.outputDir, key))
		require.NoError(t, e)
		s.Data[key] = raw
	}
	_, e = checkedRuntime(vm, s)
	require.NoError(t, e, "原完整Runtime policy库必须接受明确major18")
}

func TestRuntimeRenderRejectsMixedMajorBeforeOutput(t *testing.T) {
	for _, name := range []string{"missing-choice", "wrong-scope", "native17", "policy17", "native19", "closure-missing", "closure-invalid", "helper-missing", "helper-ELF-drift", "PG-ELF-missing", "duplicate-major", "unknown-native-field", "live-major-drift"} {
		t.Run(name, func(t *testing.T) {
			p, in := renderMajorFixture(t, 18)
			if name == "live-major-drift" {
				vm, e := p.vms.Get(context.Background(), p.wanted.Name, metav1.GetOptions{})
				require.NoError(t, e)
				vm.Annotations["neon-control/postgres-major"] = "17"
				_, e = p.vms.Update(context.Background(), vm, metav1.UpdateOptions{})
				require.NoError(t, e)
			} else if name == "missing-choice" {
				delete(p.wanted.Annotations, "neon-control/postgres-major")
				vm, e := p.vms.Get(context.Background(), p.wanted.Name, metav1.GetOptions{})
				require.NoError(t, e)
				delete(vm.Annotations, "neon-control/postgres-major")
				_, e = p.vms.Update(context.Background(), vm, metav1.UpdateOptions{})
				require.NoError(t, e)
			} else if name == "wrong-scope" {
				raw, e := os.ReadFile(in.contract)
				require.NoError(t, e)
				var c renderBuildContract
				require.NoError(t, json.Unmarshal(raw, &c))
				c.Scope = "neon-pg17-trusted-runtime-build-v1"
				raw, e = json.Marshal(c)
				require.NoError(t, e)
				require.NoError(t, os.WriteFile(in.contract, raw, 0600))
			} else {
				raw, e := os.ReadFile(in.nativeBuild)
				require.NoError(t, e)
				var native map[string]any
				require.NoError(t, json.Unmarshal(raw, &native))
				switch name {
				case "native17":
					native["pg_major"] = 17
				case "native19":
					native["pg_major"] = 19
				case "closure-missing":
					delete(native, "runtime_closure")
				case "closure-invalid":
					native["runtime_closure"].(map[string]any)["system_manifest_sha256"] = "invalid"
				case "helper-missing":
					delete(native, "array_helper")
				case "helper-ELF-drift":
					native["array_helper"].(map[string]any)["sha256"] = strings.Repeat("7", 64)
				case "PG-ELF-missing":
					native["files"] = native["files"].([]any)[:1]
				case "unknown-native-field":
					native["caller_claims_qualified"] = true
				}
				raw, e = json.Marshal(native)
				require.NoError(t, e)
				if name == "duplicate-major" {
					raw = bytes.Replace(raw, []byte("{"), []byte("{\"pg_major\":18,"), 1)
				}
				require.NoError(t, os.WriteFile(in.nativeBuild, raw, 0600))
				renderMajorRewriteContract(t, in, 18)
				if name == "policy17" {
					raw, e = os.ReadFile(in.policies)
					require.NoError(t, e)
					var ts map[string]any
					require.NoError(t, json.Unmarshal(raw, &ts))
					for _, v := range ts["templates"].([]any) {
						entry := v.(map[string]any)
						if entry["asset"] == "dsga-native-birth.json" {
							entry["policy"].(map[string]any)["pg_major"] = 17
						}
					}
					raw, e = json.Marshal(ts)
					require.NoError(t, e)
					require.NoError(t, os.WriteFile(in.policies, raw, 0600))
					cr, e := os.ReadFile(in.contract)
					require.NoError(t, e)
					var c renderBuildContract
					require.NoError(t, json.Unmarshal(cr, &c))
					c.PolicyTemplatesSHA256 = digest(raw)
					cr, e = json.Marshal(c)
					require.NoError(t, e)
					require.NoError(t, os.WriteFile(in.contract, cr, 0600))
				}
			}
			require.Error(t, p.render(context.Background(), in))
			_, e := os.Stat(in.outputDir)
			require.True(t, os.IsNotExist(e))
			require.False(t, p.state.SecretCreateMayHaveSent)
			require.False(t, p.state.ReleaseMayHaveSent)
		})
	}
}

func TestRuntimeRenderMajor17RejectsNative18Relabel(t *testing.T) {
	p, in := renderMajorFixture(t, 17)
	require.NoError(t, os.WriteFile(in.nativeBuild, renderMajorNativeUnit(t, 18, true), 0600))
	renderMajorRewriteContract(t, in, 17)
	require.Error(t, p.render(context.Background(), in))
	_, e := os.Stat(in.outputDir)
	require.True(t, os.IsNotExist(e))
}
