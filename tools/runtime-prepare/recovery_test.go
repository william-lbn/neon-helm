package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	vmv1 "github.com/neondatabase/autoscaling/neonvm/apis/neonvm/v1"
	vmclient "github.com/neondatabase/autoscaling/neonvm/client/clientset/versioned"
	vmfake "github.com/neondatabase/autoscaling/neonvm/client/clientset/versioned/fake"
	"github.com/neondatabase/autoscaling/pkg/dsga/hostguard"
	"github.com/neondatabase/autoscaling/pkg/dsga/journal"
	"github.com/neondatabase/autoscaling/pkg/dsga/resourceguard"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/kubernetes"
	kubefake "k8s.io/client-go/kubernetes/fake"
	"k8s.io/client-go/rest"
	kt "k8s.io/client-go/testing"
)

// 复用原Runtime公开库/首次封存夹具，仅把完成的原对象放到真实typed HTTP边界。
// 服务端明确模拟Controller终态，不把该测试当真实K8s/容器退出验收。
type retireAPI struct {
	mu                                                                       sync.Mutex
	p                                                                        *preparer
	vm                                                                       *vmv1.VirtualMachine
	secret                                                                   *corev1.Secret
	service                                                                  *corev1.Service
	deleted, deleting, replaceAfterDelete, missingFinalizer, lostDeleteReply bool
	paged, latePod, lateNodeUnknown                                          bool
	nodeLedger                                                               *corev1.Node
	deletes, otherWrites, podPages, nodePages                                int
}

func readyRetireFixture(t *testing.T) (*preparer, *retireAPI) {
	t.Helper()
	ctx := context.Background()
	vm, data := nativeUnit(t)
	vm.Spec.Guest.MemorySlots = vmv1.MemorySlots{Min: 7, Max: 8, Use: 7}
	vms := vmfake.NewSimpleClientset(vm)
	store, err := journal.NewStore(vms.NeonvmV1().VirtualMachines(vm.Namespace), journal.Binding{Namespace: vm.Namespace, Name: vm.Name, VMUID: vm.UID, Incarnation: vm.Spec.DSGABootstrap.Incarnation})
	require.NoError(t, err)
	_, err = store.Initialize(ctx, vm.ResourceVersion, "unit-retire-bootstrap")
	require.NoError(t, err)
	core := kubefake.NewSimpleClientset()
	installManagementServiceReactor(t, core)
	core.PrependReactor("create", "secrets", func(a kt.Action) (bool, runtime.Object, error) {
		s := a.(kt.CreateAction).GetObject().(*corev1.Secret).DeepCopy()
		s.UID = "original-secret-uid"
		s.ResourceVersion = "1"
		require.NoError(t, core.Tracker().Create(corev1.SchemeGroupVersion.WithResource("secrets"), s, s.Namespace))
		return true, s, nil
	})
	dir := t.TempDir()
	require.NoError(t, os.Chmod(dir, 0700))
	wanted := vm.DeepCopy()
	wanted.UID = ""
	wanted.ResourceVersion = ""
	p := &preparer{core: core.CoreV1(), vms: vms.NeonvmV1().VirtualMachines(vm.Namespace), wanted: wanted, state: retained{ProtocolVersion: 1, Scope: stateScope, ManifestSHA256: digest([]byte("original-held-manifest")), Namespace: vm.Namespace, Name: vm.Name, VMUID: vm.UID, VMCreateMayHaveSent: true}, statePath: filepath.Join(dir, "state.json")}
	input := files{filepath.Join(dir, "config"), filepath.Join(dir, "resource"), filepath.Join(dir, "policies")}
	for key, path := range map[string]string{"config.json": input.config, resourceguard.ResourceSecretKey: input.resource, resourceguard.PolicyTemplatesSecretKey: input.policies} {
		require.NoError(t, os.WriteFile(path, data[key], 0600))
	}
	_, err = p.seal(ctx, input)
	require.NoError(t, err)
	actual, err := vms.NeonvmV1().VirtualMachines(vm.Namespace).Get(ctx, vm.Name, metav1.GetOptions{})
	require.NoError(t, err)
	actual.Finalizers = []string{retireControllerFinalizer}
	actual.TypeMeta = metav1.TypeMeta{APIVersion: vmv1.SchemeGroupVersion.String(), Kind: "VirtualMachine"}
	secret, err := core.CoreV1().Secrets(vm.Namespace).Get(ctx, vm.Name+"-config", metav1.GetOptions{})
	require.NoError(t, err)
	svc, err := core.CoreV1().Services(vm.Namespace).Get(ctx, vm.Name+"-management", metav1.GetOptions{})
	require.NoError(t, err)
	api := &retireAPI{p: p, vm: actual, secret: secret, service: svc}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) { api.serve(t, w, req) }))
	t.Cleanup(server.Close)
	generated, err := vmclient.NewForConfig(&rest.Config{Host: server.URL})
	require.NoError(t, err)
	native, err := kubernetes.NewForConfig(&rest.Config{Host: server.URL})
	require.NoError(t, err)
	p.vms = generated.NeonvmV1().VirtualMachines(vm.Namespace)
	p.core = native.CoreV1()
	return p, api
}
func (f *retireAPI) serve(t *testing.T, w http.ResponseWriter, r *http.Request) {
	t.Helper()
	f.mu.Lock()
	defer f.mu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	reply := func(v any) { require.NoError(t, json.NewEncoder(w).Encode(v)) }
	missing := func() {
		w.WriteHeader(404)
		reply(metav1.Status{TypeMeta: metav1.TypeMeta{APIVersion: "v1", Kind: "Status"}, Status: "Failure", Reason: metav1.StatusReasonNotFound, Code: 404})
	}
	vmPath := fmt.Sprintf("/apis/vm.neon.tech/v1/namespaces/%s/virtualmachines/%s", f.vm.Namespace, f.vm.Name)
	if r.URL.Path == vmPath {
		if r.Method == http.MethodDelete {
			f.deletes++
			var options metav1.DeleteOptions
			require.NoError(t, json.NewDecoder(r.Body).Decode(&options))
			require.NotNil(t, options.Preconditions)
			require.Equal(t, f.vm.UID, *options.Preconditions.UID)
			require.Equal(t, f.vm.ResourceVersion, *options.Preconditions.ResourceVersion)
			require.Nil(t, options.GracePeriodSeconds, "不得force删除")
			// 真正HTTP DELETE到达前，原私有archive和may-send必须已持久可读。
			raw, e := os.ReadFile(f.p.statePath)
			require.NoError(t, e)
			var retainedState retained
			require.NoError(t, json.Unmarshal(raw, &retainedState))
			require.True(t, retainedState.RetireMayHaveSent)
			require.False(t, retainedState.Retired)
			archive, e := os.ReadFile(f.p.retirementArchivePath(retainedState.RetireArchiveSHA256))
			require.NoError(t, e)
			require.Equal(t, retainedState.RetireArchiveSHA256, digest(archive))
			if f.deleting {
				stamp := metav1.Now()
				f.vm.DeletionTimestamp = &stamp
			} else {
				f.deleted = true
			}
			if f.lostDeleteReply {
				f.lostDeleteReply = false
				w.WriteHeader(504)
				reply(metav1.Status{Status: "Failure", Reason: metav1.StatusReasonTimeout, Code: 504})
				return
			}
			reply(metav1.Status{TypeMeta: metav1.TypeMeta{APIVersion: "v1", Kind: "Status"}, Status: "Success", Code: 200})
			return
		}
		if r.Method != http.MethodGet {
			f.otherWrites++
			t.Errorf("unexpected VM write %s", r.Method)
			w.WriteHeader(409)
			return
		}
		if f.deleted && !f.replaceAfterDelete {
			missing()
			return
		}
		vm := f.vm.DeepCopy()
		if f.replaceAfterDelete && f.deleted {
			vm.UID = "same-name-replacement"
		}
		if f.missingFinalizer {
			vm.Finalizers = nil
		}
		reply(vm)
		return
	}
	if r.Method != http.MethodGet {
		f.otherWrites++
		t.Errorf("retire must not write Pod/Node/CM/Secret %s", r.URL.Path)
		w.WriteHeader(409)
		return
	}
	base := "/api/v1/namespaces/" + f.vm.Namespace
	switch r.URL.Path {
	case base + "/services/" + f.vm.Name + "-management":
		reply(f.service)
	case base + "/secrets/" + f.vm.Name + "-config":
		reply(f.secret)
	case base + "/configmaps":
		list := corev1.ConfigMapList{TypeMeta: metav1.TypeMeta{APIVersion: "v1", Kind: "ConfigMapList"}, ListMeta: metav1.ListMeta{ResourceVersion: "source-point-1"}}
		if f.paged && r.URL.Query().Get("continue") == "" {
			list.Continue = "cm-page2"
		} else {
			list.Items = []corev1.ConfigMap{{ObjectMeta: metav1.ObjectMeta{Namespace: f.vm.Namespace, Name: "original-claim", UID: "original-claim-uid", ResourceVersion: "1", OwnerReferences: []metav1.OwnerReference{{UID: f.vm.UID}}}, Data: map[string]string{"point": "original-wal-unknown-retained"}}}
		}
		reply(list)
	case base + "/pods":
		f.podPages++
		list := corev1.PodList{TypeMeta: metav1.TypeMeta{APIVersion: "v1", Kind: "PodList"}}
		if f.paged && r.URL.Query().Get("continue") == "" {
			list.Continue = "pod-page2"
		} else if f.latePod {
			list.Items = []corev1.Pod{{ObjectMeta: metav1.ObjectMeta{Name: "original-runner", Namespace: f.vm.Namespace, OwnerReferences: []metav1.OwnerReference{{UID: f.vm.UID}}}}}
		}
		reply(list)
	case "/api/v1/nodes":
		f.nodePages++
		list := corev1.NodeList{TypeMeta: metav1.TypeMeta{APIVersion: "v1", Kind: "NodeList"}, Items: []corev1.Node{{ObjectMeta: metav1.ObjectMeta{Name: "worker-117", UID: "node117"}}}}
		if f.paged && r.URL.Query().Get("continue") == "" {
			list.Continue = "node-page2"
		} else if f.lateNodeUnknown {
			list.Items[0].Annotations = map[string]string{hostguard.OriginAnnotation: "ledger-missing"}
		} else if f.nodeLedger != nil {
			list.Items = []corev1.Node{*f.nodeLedger.DeepCopy()}
		}
		reply(list)
	default:
		t.Errorf("unexpected API route %s", r.URL.Path)
		missing()
	}
}

func TestRuntimeRetireArchivesBeforeDeleteAndKeepsOldStateClosed(t *testing.T) {
	p, api := readyRetireFixture(t)
	api.paged = true
	api.vm.Spec.Guest.MemorySlots.Use = 8
	require.NoError(t, p.retire(context.Background()))
	require.True(t, p.state.Retired)
	require.True(t, p.state.RetireMayHaveSent)
	point, err := p.readRetirementArchive()
	require.NoError(t, err)
	require.Equal(t, p.state.VMUID, point.VM.UID)
	require.Len(t, point.ConfigMaps, 1)
	require.EqualValues(t, 8, point.VM.Spec.Guest.MemorySlots.Use)
	require.Equal(t, false, p.deploymentOutput("retire")["bootstrap_ready"])
	require.Equal(t, true, p.deploymentOutput("retire")["original_bootstrap_complete"])
	require.Equal(t, "unknown", point.AdmissionObservation)
	_, _, err = p.held(context.Background(), true)
	require.ErrorContains(t, err, "retirement intent")
	api.mu.Lock()
	require.Equal(t, 1, api.deletes)
	require.Zero(t, api.otherWrites)
	require.Equal(t, 2, api.podPages)
	require.Equal(t, 2, api.nodePages)
	api.mu.Unlock()
}
func TestRuntimeRetireLostDeleteReplyDoesNotMeanStopped(t *testing.T) {
	p, api := readyRetireFixture(t)
	api.lostDeleteReply = true
	require.ErrorContains(t, p.retire(context.Background()), "DELETE outcome unknown")
	require.True(t, p.state.RetireMayHaveSent)
	require.False(t, p.state.Retired)
	require.NoError(t, p.retire(context.Background()))
	require.True(t, p.state.Retired)
	api.mu.Lock()
	require.Equal(t, 1, api.deletes)
	require.Zero(t, api.otherWrites)
	api.mu.Unlock()
}
func TestRuntimeRetireRefusesMissingTicketFinalizerAndReplacement(t *testing.T) {
	for _, mode := range []string{"404-without-ticket", "missing-finalizer", "replacement-after-delete", "archive-changed", "still-deleting", "Use-below-min", "Use-above-max", "other-spec-drift"} {
		t.Run(mode, func(t *testing.T) {
			p, api := readyRetireFixture(t)
			switch mode {
			case "Use-below-min":
				api.vm.Spec.Guest.MemorySlots.Use = 6
			case "Use-above-max":
				api.vm.Spec.Guest.MemorySlots.Use = 9
			case "other-spec-drift":
				api.vm.Spec.Guest.MemorySlots.Max++
			case "404-without-ticket":
				api.deleted = true
			case "missing-finalizer":
				api.missingFinalizer = true
			case "replacement-after-delete":
				api.replaceAfterDelete = true
			case "archive-changed", "still-deleting":
				api.deleting = true
			}
			err := p.retire(context.Background())
			require.Error(t, err)
			require.False(t, p.state.Retired)
			if mode == "archive-changed" {
				require.True(t, p.state.RetireMayHaveSent)
				require.NoError(t, os.WriteFile(p.retirementArchivePath(p.state.RetireArchiveSHA256), []byte("changed"), 0600))
				require.ErrorContains(t, p.retire(context.Background()), "archive bytes changed")
			}
			if mode == "replacement-after-delete" {
				require.ErrorContains(t, err, "replacement UID")
				require.ErrorContains(t, p.retire(context.Background()), "replacement UID")
			}
			api.mu.Lock()
			want := 1
			if mode == "404-without-ticket" || mode == "missing-finalizer" || strings.HasPrefix(mode, "Use-") || mode == "other-spec-drift" {
				want = 0
			}
			require.Equal(t, want, api.deletes)
			require.Zero(t, api.otherWrites)
			api.mu.Unlock()
		})
	}
}
func TestRuntimeRetireRequiresEveryPodAndNodePageUnheld(t *testing.T) {
	for _, mode := range []string{"old-pod-page2", "unknown-node-page2"} {
		t.Run(mode, func(t *testing.T) {
			p, api := readyRetireFixture(t)
			api.paged = true
			if mode == "old-pod-page2" {
				api.latePod = true
			} else {
				api.lateNodeUnknown = true
			}
			require.Error(t, p.retire(context.Background()))
			require.True(t, p.state.RetireMayHaveSent)
			require.False(t, p.state.Retired)
			api.mu.Lock()
			api.latePod = false
			api.lateNodeUnknown = false
			api.mu.Unlock()
			require.NoError(t, p.retire(context.Background()))
			require.True(t, p.state.Retired)
			api.mu.Lock()
			require.Equal(t, 1, api.deletes)
			require.Zero(t, api.otherWrites)
			api.mu.Unlock()
		})
	}
}

// 内部Host v10必须由更新后的工具真实解码。VM/Pod 404不能抹除仍持有的
// 完整Pod硬限floor；只有原Node行已结清才允许同一退役意图完成。
// typed HTTP仅验证本工具的调用及拒绝语义，不代替真实Host/Guest退出验收。
func TestRuntimeRetireRetainsV10PodHardlimitUntilOriginalRowClosed(t *testing.T) {
	p, api := readyRetireFixture(t)
	api.paged = true
	placements := []hostguard.Placement{{
		Namespace: p.state.Namespace, PodName: "original-runner", PodUID: "original-runner-uid",
		VMName: p.state.Name, VMUID: string(p.state.VMUID),
		Incarnation: p.wanted.Spec.DSGABootstrap.Incarnation, Managed: true,
		MemoryBytes: 7 << 30, HostOverheadBytes: 3 << 30, PodMemoryLimitBytes: 11 << 30,
	}}
	model := hostguard.Model{
		ProtocolVersion: 10,
		Binding:         hostguard.Binding{NodeName: "worker-117", NodeUID: "node117", Namespace: "kube-system", LeaseName: "original-allocator", LeaseUID: "original-allocator-uid"},
		Origin:          strings.Repeat("a", 32), LeaseFloor: journal.Owner{HolderID: "original-allocator", Epoch: 1},
		Sequence: 1, OutsideBytes: 4 << 30, Holds: []hostguard.Hold{},
		Profile:    &hostguard.Profile{ID: "unit-v10-pod-floor", SchedulerName: "autoscale-scheduler", VMOverheadBytes: 3 << 30, PodOverheadBytes: 16 << 20},
		Placements: &placements,
	}
	require.NoError(t, model.Validate())
	used, err := model.UsedBytes()
	require.NoError(t, err)
	require.EqualValues(t, 15<<30, used, "计完整11Gi Pod，不能只按7Gi VM加3Gi记账")
	raw, err := json.Marshal(model)
	require.NoError(t, err)
	node := &corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "worker-117", UID: "node117", ResourceVersion: "1", Finalizers: []string{hostguard.ProtectionFinalizer}, Annotations: map[string]string{hostguard.LedgerAnnotation: string(raw), hostguard.OriginAnnotation: "1:" + model.Origin}}}
	api.nodeLedger = node
	require.ErrorContains(t, p.retire(context.Background()), "original VM still has a Pod allocation")
	require.True(t, p.state.RetireMayHaveSent)
	require.False(t, p.state.Retired, "Pod已404也必须保留未结清原预算")
	originalArchive := p.state.RetireArchiveSHA256

	// 模拟外部原owner已正常结清该行；本工具自身从不写Node或清floor。
	empty := []hostguard.Placement{}
	model.Placements = &empty
	model.Sequence++
	require.NoError(t, model.Validate())
	raw, err = json.Marshal(model)
	require.NoError(t, err)
	closed := node.DeepCopy()
	closed.ResourceVersion = "2"
	closed.Annotations[hostguard.LedgerAnnotation] = string(raw)
	api.mu.Lock()
	api.nodeLedger = closed
	api.mu.Unlock()
	require.NoError(t, p.retire(context.Background()))
	require.True(t, p.state.Retired)
	require.Equal(t, originalArchive, p.state.RetireArchiveSHA256)
	api.mu.Lock()
	require.Equal(t, 1, api.deletes, "原DELETE只派发一次，后续观察同一退役意图")
	require.Zero(t, api.otherWrites, "不得写Node/Pod/Secret或重置旧账本")
	require.Equal(t, 4, api.nodePages, "两次观察均核到第二页Node")
	api.mu.Unlock()
}
