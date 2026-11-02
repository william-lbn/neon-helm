package main

import (
	"context"
	_ "embed"
	"encoding/json"
	vmv1 "github.com/neondatabase/autoscaling/neonvm/apis/neonvm/v1"
	vmfake "github.com/neondatabase/autoscaling/neonvm/client/clientset/versioned/fake"
	"github.com/neondatabase/autoscaling/pkg/dsga/bootstrap"
	"github.com/neondatabase/autoscaling/pkg/dsga/journal"
	"github.com/neondatabase/autoscaling/pkg/dsga/resourceguard"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	kubefake "k8s.io/client-go/kubernetes/fake"
	kt "k8s.io/client-go/testing"
	"os"
	"path/filepath"
	"testing"
)

//go:embed testdata/OFFLINE-runtime-seed.json
var seed []byte

func nativeUnit(t *testing.T) (*vmv1.VirtualMachine, map[string][]byte) {
	t.Helper()
	var doc resourceguard.RuntimeDocument
	require.NoError(t, json.Unmarshal(seed, &doc))
	source, e := doc.Source()
	require.NoError(t, e)
	source.Config.VMUID = "original-vm-uid"
	source.Config.ExecutionModel = resourceguard.TrustedControllerExecutionModel
	raw, e := json.Marshal(source)
	require.NoError(t, e)
	var templates struct {
		ProtocolVersion uint32 `json:"protocol_version"`
		Scope           string `json:"scope"`
		Templates       []struct {
			Asset  string         `json:"asset"`
			Policy map[string]any `json:"policy"`
		} `json:"templates"`
	}
	require.NoError(t, json.Unmarshal(doc.PolicyTemplatesJSON, &templates))
	for i := range templates.Templates {
		if templates.Templates[i].Asset == "dsga-native-birth.json" {
			templates.Templates[i].Policy["array_helper_protocol_version"] = 1
			templates.Templates[i].Policy["array_helper_path"] = "/neonvm/bin/neon-dsga-array-populate"
			templates.Templates[i].Policy["array_helper_elf_sha256"] = "abababababababababababababababababababababababababababababababab"
			templates.Templates[i].Policy["array_helper_address_space_max_bytes"] = "1048576"
			templates.Templates[i].Policy["array_helper_memlock_upper_bytes"] = "4096"
			templates.Templates[i].Policy["array_helper_reserve_bytes"] = "2097152"
		}
	}
	policies, e := json.Marshal(templates)
	require.NoError(t, e)
	config, e := json.Marshal(map[string]any{"spec": map[string]any{"dynamic_shared_buffers": map[string]any{"protocol_version": 2, "vm_uid": source.Config.VMUID, "compute_instance_id": source.Config.ComputeInstanceID, "minimum_guest_memory_bytes": uint64(7 << 30), "bootstrap_buffer_bytes": uint64(2 << 20)}}, "compute_ctl_config": map[string]any{"jwks": map[string]any{"keys": []any{map[string]any{"use": "sig", "key_ops": []string{"verify"}, "alg": "EdDSA", "kty": "OKP", "crv": "Ed25519", "x": source.ControlPublicKey}}}}})
	require.NoError(t, e)
	vm := &vmv1.VirtualMachine{ObjectMeta: metav1.ObjectMeta{Name: "unit-only-vm", Namespace: "unit-only", UID: types.UID(source.Config.VMUID), ResourceVersion: "1"}}
	vm.Spec.DSGABootstrap = &vmv1.DSGABootstrap{ProtocolVersion: 1, Incarnation: doc.Incarnation, ComputeInstanceID: source.Config.ComputeInstanceID}
	return vm, map[string][]byte{"config.json": config, resourceguard.ResourceSecretKey: raw, resourceguard.PolicyTemplatesSecretKey: policies}
}
func TestRuntimePrepareActualUIDAndImmutableBytes(t *testing.T) {
	vm, data := nativeUnit(t)
	s := secretFor(vm, data)
	s.UID = "original-secret-uid"
	s.ResourceVersion = "1"
	require.NoError(t, originalSecret(vm, s, data, s.UID))
	for name, mutate := range map[string]func(*corev1.Secret){"uid": func(s *corev1.Secret) { s.UID = "replacement" }, "owner": func(s *corev1.Secret) { s.OwnerReferences[0].UID = "replacement" }, "mutable": func(s *corev1.Secret) { v := false; s.Immutable = &v }, "bytes": func(s *corev1.Secret) { s.Data["config.json"] = []byte("changed") }} {
		t.Run(name, func(t *testing.T) {
			bad := s.DeepCopy()
			mutate(bad)
			require.Error(t, originalSecret(vm, bad, data, s.UID))
		})
	}
}
func TestRuntimePrepareSealUsesRealLibraryAndKeepsBadPolicyHeld(t *testing.T) {
	for _, name := range []string{"complete", "complete-public-kid", "unsupported-policy", "private-jwk", "unknown-jwk"} {
		bad := name == "unsupported-policy" || name == "private-jwk" || name == "unknown-jwk"
		t.Run(name, func(t *testing.T) {
			vm, data := nativeUnit(t)
			vms := vmfake.NewSimpleClientset(vm)
			store, e := journal.NewStore(vms.NeonvmV1().VirtualMachines(vm.Namespace), journal.Binding{Namespace: vm.Namespace, Name: vm.Name, VMUID: vm.UID, Incarnation: vm.Spec.DSGABootstrap.Incarnation})
			require.NoError(t, e)
			_, e = store.Initialize(context.Background(), vm.ResourceVersion, "unit-bootstrap-owner")
			require.NoError(t, e)
			client := kubefake.NewSimpleClientset()
			client.PrependReactor("create", "secrets", func(a kt.Action) (bool, runtime.Object, error) {
				s := a.(kt.CreateAction).GetObject().(*corev1.Secret).DeepCopy()
				s.UID = "api-assigned-secret-uid"
				s.ResourceVersion = "1"
				require.NoError(t, client.Tracker().Create(corev1.SchemeGroupVersion.WithResource("secrets"), s, s.Namespace))
				return true, s, nil
			})
			dir := t.TempDir()
			require.NoError(t, os.Chmod(dir, 0700))
			statePath := filepath.Join(dir, "original-state.json")
			wanted := vm.DeepCopy()
			wanted.UID = ""
			wanted.ResourceVersion = ""
			p := &preparer{core: client.CoreV1(), vms: vms.NeonvmV1().VirtualMachines(vm.Namespace), wanted: wanted, state: retained{ProtocolVersion: 1, Scope: stateScope, VMUID: vm.UID, Namespace: vm.Namespace, Name: vm.Name}, statePath: statePath}
			if name == "unsupported-policy" {
				data[resourceguard.PolicyTemplatesSecretKey] = []byte(`{"protocol_version":1,"scope":"unsupported","templates":[]}`)
			}
			if name == "complete-public-kid" || name == "private-jwk" || name == "unknown-jwk" {
				var cfg map[string]any
				require.NoError(t, json.Unmarshal(data["config.json"], &cfg))
				key := cfg["compute_ctl_config"].(map[string]any)["jwks"].(map[string]any)["keys"].([]any)[0].(map[string]any)
				switch name {
				case "complete-public-kid":
					key["kid"] = "original-public-key-id"
				case "private-jwk":
					key["d"] = "do-not-create-signing-seed-in-Guest-Secret"
				case "unknown-jwk":
					key["secret_seed"] = "do-not-forward-unknown-key-material"
				}
				data["config.json"], e = json.Marshal(cfg)
				require.NoError(t, e)
			}
			input := files{filepath.Join(dir, "config"), filepath.Join(dir, "resource"), filepath.Join(dir, "policies")}
			for k, path := range map[string]string{"config.json": input.config, resourceguard.ResourceSecretKey: input.resource, resourceguard.PolicyTemplatesSecretKey: input.policies} {
				require.NoError(t, os.WriteFile(path, data[k], 0600))
			}
			if !bad {
				// 正控先由同一个公开Runtime库验证，失败不得被后面的held负例掩盖。
				snapshot, err := store.Load(context.Background())
				require.NoError(t, err)
				preview := snapshot.VirtualMachine()
				preview.Spec.DSGABootstrap.Ready = true
				preview.Spec.DSGABootstrap.VMUID = string(vm.UID)
				preview.Spec.DSGABootstrap.ConfigSecretUID = "api-assigned-secret-uid"
				original := secretFor(vm, data)
				original.UID = "api-assigned-secret-uid"
				original.ResourceVersion = "1"
				_, err = bootstrap.Runtime(preview, original)
				require.NoError(t, err)
			}
			_, e = p.seal(context.Background(), input)
			actual, read := vms.NeonvmV1().VirtualMachines(vm.Namespace).Get(context.Background(), vm.Name, metav1.GetOptions{})
			require.NoError(t, read)
			if bad {
				require.Error(t, e)
				if name == "private-jwk" || name == "unknown-jwk" {
					require.Empty(t, client.Actions(), "private/unknown key must be rejected before any Secret API")
				}
				require.False(t, actual.Spec.DSGABootstrap.Ready)
				require.False(t, p.state.ReleaseMayHaveSent)
				require.False(t, p.state.Complete)
			} else {
				require.NoError(t, e)
				require.True(t, actual.Spec.DSGABootstrap.Ready)
				require.Equal(t, "api-assigned-secret-uid", actual.Spec.DSGABootstrap.ConfigSecretUID)
				require.True(t, p.state.Complete)
				require.NotEmpty(t, p.state.RuntimeSHA256)
			}
		})
	}
}

// CREATE回应没有原UID时，后来同名对象即使模板相同也不能补签原身份。
func TestRuntimePrepareUnconfirmedCreateDoesNotAdoptSameName(t *testing.T) {
	for _, object := range []string{"vm", "secret"} {
		t.Run(object, func(t *testing.T) {
			vm, data := nativeUnit(t)
			vms := vmfake.NewSimpleClientset(vm)
			store, err := journal.NewStore(vms.NeonvmV1().VirtualMachines(vm.Namespace), journal.Binding{Namespace: vm.Namespace, Name: vm.Name, VMUID: vm.UID, Incarnation: vm.Spec.DSGABootstrap.Incarnation})
			require.NoError(t, err)
			_, err = store.Initialize(context.Background(), vm.ResourceVersion, "unit-bootstrap-owner")
			require.NoError(t, err)
			secret := secretFor(vm, data)
			secret.UID = "same-name-new-secret"
			secret.ResourceVersion = "1"
			core := kubefake.NewSimpleClientset(secret)
			vms.ClearActions()
			dir := t.TempDir()
			wanted := vm.DeepCopy()
			wanted.UID = ""
			wanted.ResourceVersion = ""
			p := &preparer{core: core.CoreV1(), vms: vms.NeonvmV1().VirtualMachines(vm.Namespace), wanted: wanted, state: retained{ProtocolVersion: 1, Scope: stateScope, Namespace: vm.Namespace, Name: vm.Name}, statePath: filepath.Join(dir, "state.json")}
			if object == "vm" {
				p.state.VMCreateMayHaveSent = true
				_, _, err = p.held(context.Background(), true)
			} else {
				p.state.VMUID = vm.UID
				p.state.SecretCreateMayHaveSent = true
				f := files{filepath.Join(dir, "config"), filepath.Join(dir, "resource"), filepath.Join(dir, "policies")}
				for k, path := range map[string]string{"config.json": f.config, resourceguard.ResourceSecretKey: f.resource, resourceguard.PolicyTemplatesSecretKey: f.policies} {
					require.NoError(t, os.WriteFile(path, data[k], 0600))
				}
				_, err = p.seal(context.Background(), f)
			}
			require.ErrorContains(t, err, "same-name adoption forbidden")
			for _, a := range vms.Actions() {
				require.Equal(t, "get", a.GetVerb(), "unconfirmed retry must not mutate original VM")
			}
			for _, a := range core.Actions() {
				require.Equal(t, "get", a.GetVerb(), "unconfirmed retry must not mutate original Secret")
			}
			actual, e := vms.NeonvmV1().VirtualMachines(vm.Namespace).Get(context.Background(), vm.Name, metav1.GetOptions{})
			require.NoError(t, e)
			require.False(t, actual.Spec.DSGABootstrap.Ready)
		})
	}
}
