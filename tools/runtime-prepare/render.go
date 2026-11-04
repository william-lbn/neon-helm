package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	vmv1 "github.com/neondatabase/autoscaling/neonvm/apis/neonvm/v1"
	control "github.com/neondatabase/autoscaling/pkg/api/dsga"
	"github.com/neondatabase/autoscaling/pkg/dsga/resourceguard"
	"golang.org/x/sys/unix"
)

// 这是发行工具的原构建输入索引，不是预算/平台资格或新控制面协议。
// 三个镜像必须等于原held VM；模板与manifest由已审核Builder产物摘要钉住。
type renderBuildContract struct {
	ProtocolVersion       uint32 `json:"protocol_version"`
	Scope                 string `json:"scope"`
	GuestImage            string `json:"guest_image"`
	RunnerImage           string `json:"runner_image"`
	KernelImage           string `json:"kernel_image"`
	PolicyTemplatesSHA256 string `json:"policy_templates_sha256"`
	NativeBuildSHA256     string `json:"native_build_sha256"`
	ComputeConfigPath     string `json:"compute_config_path"`
}

const postgresMajorAnnotation = "neon-control/postgres-major"

// 默认17兼容原manifest原字节。18必须由原Helm选择显式进入；这不是资格/预算许可。
func selectedPostgresMajor(vm *vmv1.VirtualMachine) (uint32, error) {
	if vm == nil {
		return 0, fmt.Errorf("original VM postgres major unavailable")
	}
	value, present := vm.Annotations[postgresMajorAnnotation]
	if !present {
		return 17, nil
	}
	switch value {
	case "17":
		return 17, nil
	case "18":
		return 18, nil
	default:
		return 0, fmt.Errorf("unsupported original VM postgres major")
	}
}

// 只投影原canonical Native的版本/ELF引用，不从镜像名或共享Root/Runner版本猜major。
// 完整ELF字节/FS闭包仍须由原Collector和盘读回确证，seal继续原Runtime库严格校验。
func renderNativeMajorMatches(raw []byte, major uint32, policyRaw []byte) error {
	var m struct {
		ProtocolVersion uint32 `json:"protocol_version"`
		Scope           string `json:"scope"`
		PGMajor         uint32 `json:"pg_major"`
		LaunchPath      string `json:"launch_path"`
		PostgresPath    string `json:"postgres_path"`
		InterpreterPath string `json:"interpreter_path"`
		Files           []struct {
			Path   string `json:"path"`
			SHA256 string `json:"sha256"`
		} `json:"files"`
		ArrayHelper *struct {
			ProtocolVersion uint32 `json:"protocol_version"`
			Path            string `json:"path"`
			SHA256          string `json:"sha256"`
		} `json:"array_helper,omitempty"`
		RuntimeClosure *struct {
			ProtocolVersion      uint32 `json:"protocol_version"`
			SystemManifestSHA256 string `json:"system_manifest_sha256"`
		} `json:"runtime_closure,omitempty"`
	}
	if control.UnmarshalObject(raw, &m) != nil || m.ProtocolVersion != 1 || m.Scope != "neon-native-pre-main-default-loader-v1" ||
		m.PGMajor != major || m.LaunchPath != resourceguard.FixedPostgresPath || len(m.Files) == 0 || len(m.Files) > 64 {
		return fmt.Errorf("original Native manifest postgres major or ELF references differ")
	}
	clean := func(p string) bool {
		return filepath.IsAbs(p) && filepath.Clean(p) == p && p != "/" && !strings.ContainsAny(p, "\x00\r\n")
	}
	hash := regexp.MustCompile("^[a-f0-9]{64}$")
	if !clean(m.PostgresPath) || m.InterpreterPath != "" && !clean(m.InterpreterPath) {
		return fmt.Errorf("original Native ELF path differs")
	}
	seen := map[string]bool{}
	for n, f := range m.Files {
		if !clean(f.Path) || !hash.MatchString(f.SHA256) || seen[f.Path] || n > 0 && m.Files[n-1].Path >= f.Path {
			return fmt.Errorf("original Native ELF references not canonical")
		}
		seen[f.Path] = true
	}
	if !seen[m.PostgresPath] || m.InterpreterPath != "" && !seen[m.InterpreterPath] {
		return fmt.Errorf("original Native ELF reference missing")
	}
	if m.RuntimeClosure != nil && (m.RuntimeClosure.ProtocolVersion != 1 || !hash.MatchString(m.RuntimeClosure.SystemManifestSHA256)) {
		return fmt.Errorf("original Native runtime closure differs")
	}
	var policy struct {
		PGmajor               uint32 `json:"pg_major"`
		HelperProtocolVersion uint32 `json:"array_helper_protocol_version"`
		HelperPath            string `json:"array_helper_path"`
		HelperSHA256          string `json:"array_helper_elf_sha256"`
	}
	if json.Unmarshal(policyRaw, &policy) != nil || policy.PGmajor != major {
		return fmt.Errorf("original native policy postgres major differs")
	}
	if m.ArrayHelper != nil {
		if m.ArrayHelper.ProtocolVersion != 1 || m.ArrayHelper.Path != "/neonvm/bin/neon-dsga-array-populate" || !hash.MatchString(m.ArrayHelper.SHA256) ||
			policy.HelperProtocolVersion != m.ArrayHelper.ProtocolVersion || policy.HelperPath != m.ArrayHelper.Path || policy.HelperSHA256 != m.ArrayHelper.SHA256 {
			return fmt.Errorf("original native helper ELF binding differs")
		}
	} else if policy.HelperProtocolVersion != 0 {
		return fmt.Errorf("original native helper ELF reference missing")
	}
	if major == 18 && (m.RuntimeClosure == nil || m.ArrayHelper == nil) {
		// 不能把旧Native18 seed当最终闭包；原helper和System引用必须由本次Collector绑定。
		return fmt.Errorf("PG18 requires original helper and canonical runtime closure")
	}
	return nil
}

type renderFiles struct {
	computeTemplate, sourceTemplate, policies, nativeBuild, contract, outputDir string
}

// Compute/source可能含原凭据，必须从调用者原私有regular文件读取；不跟随symlink，
// 不记录正文。公开发行manifest也必须是原受控regular文件，且不能被group/other写。
func renderInput(path string, maximum int64, private bool) ([]byte, error) {
	f, e := os.OpenFile(path, os.O_RDONLY|unix.O_NOFOLLOW|unix.O_NONBLOCK, 0)
	if e != nil {
		return nil, fmt.Errorf("original render input unavailable")
	}
	defer f.Close()
	before, e := f.Stat()
	if e != nil || !before.Mode().IsRegular() || before.Size() <= 0 || before.Size() > maximum || before.Mode().Perm()&0022 != 0 {
		return nil, fmt.Errorf("original render input not bounded controlled regular file")
	}
	if private && before.Mode().Perm()&0077 != 0 {
		return nil, fmt.Errorf("credential-bearing render input must be private")
	}
	b, e := io.ReadAll(io.LimitReader(f, maximum+1))
	after, se := f.Stat()
	if e != nil || se != nil || len(b) == 0 || int64(len(b)) != before.Size() || !os.SameFile(before, after) || before.Size() != after.Size() || before.ModTime() != after.ModTime() {
		return nil, fmt.Errorf("original render input changed")
	}
	return b, nil
}
func renderObject(raw []byte) (map[string]json.RawMessage, error) {
	if e := control.ValidateJSON(raw, 1<<20, 65536); e != nil {
		return nil, fmt.Errorf("render JSON not canonical-key bounded object")
	}
	var out map[string]json.RawMessage
	if json.Unmarshal(raw, &out) != nil || out == nil {
		return nil, fmt.Errorf("render object required")
	}
	return out, nil
}
func originalPublicControlKey(configRaw []byte) (string, error) {
	config, e := renderObject(configRaw)
	if e != nil {
		return "", e
	}
	ctl, e := renderObject(config["compute_ctl_config"])
	if e != nil {
		return "", e
	}
	jwks, e := renderObject(ctl["jwks"])
	if e != nil {
		return "", e
	}
	var rawKeys []json.RawMessage
	if json.Unmarshal(jwks["keys"], &rawKeys) != nil || len(rawKeys) != 1 {
		return "", fmt.Errorf("original unique public JWK required")
	}
	var key struct {
		Use   string   `json:"use"`
		Ops   []string `json:"key_ops"`
		Alg   string   `json:"alg"`
		Type  string   `json:"kty"`
		Curve string   `json:"crv"`
		X     string   `json:"x"`
		KeyID string   `json:"kid,omitempty"`
	}
	// 管理JWK只允许公钥成员。d/未知key成员必须在Secret CREATE前拒绝，不能剥离。
	if control.UnmarshalObject(rawKeys[0], &key) != nil {
		return "", fmt.Errorf("original management JWK must contain public fields only")
	}
	if key.Use != "sig" || len(key.Ops) != 1 || key.Ops[0] != "verify" || key.Alg != "EdDSA" || key.Type != "OKP" || key.Curve != "Ed25519" || key.X == "" {
		return "", fmt.Errorf("original management public JWK unsupported")
	}
	return key.X, nil
}

func fixedJSON(b json.RawMessage, out any) error {
	if len(b) == 0 || bytes.Equal(bytes.TrimSpace(b), []byte("null")) || json.Unmarshal(b, out) != nil {
		return fmt.Errorf("original Compute template field missing")
	}
	return nil
}
func sameRenderBuild(vm *vmv1.VirtualMachine, c renderBuildContract, policies, native []byte) error {
	major, e := selectedPostgresMajor(vm)
	if e != nil {
		return e
	}
	hexSHA := regexp.MustCompile(`^[0-9a-f]{64}$`)
	if c.ProtocolVersion != 1 || c.Scope != fmt.Sprintf("neon-pg%d-trusted-runtime-build-v1", major) || vm.Spec.RunnerImage == nil || vm.Spec.Guest.KernelImage == nil || c.GuestImage != vm.Spec.Guest.RootDisk.Image || c.RunnerImage != *vm.Spec.RunnerImage || c.KernelImage != *vm.Spec.Guest.KernelImage || !hexSHA.MatchString(c.PolicyTemplatesSHA256) || !hexSHA.MatchString(c.NativeBuildSHA256) || digest(policies) != c.PolicyTemplatesSHA256 || digest(native) != c.NativeBuildSHA256 {
		return fmt.Errorf("original release build contract differs")
	}
	// 受信镜像只从原构建计划内的公开JWKS/spec:null启动；业务spec由既有
	// management Gateway /configure 在真实Secret封存后交付。不能把旧Secret
	// disk挂到/neonvm/config遮盖Root可信源，也不向固定启动入口注入env/script。
	if c.ComputeConfigPath != "/neonvm/config/compute-public.json" {
		return fmt.Errorf("original image public Compute config path differs")
	}
	if len(vm.Spec.Disks) != 0 || len(vm.Spec.Guest.Env) != 0 || len(vm.Spec.Guest.Command) != 0 || len(vm.Spec.Guest.Args) != 0 || vm.Spec.TLS != nil || vm.Spec.InitScript != "" || vm.Spec.EnableSSH != nil && *vm.Spec.EnableSSH {
		return fmt.Errorf("original fixed runtime forbids legacy boot inputs")
	}
	// 这里只比较原产物字节与原policy指向；真正完整policy语义仍由seal取得实际
	// Secret UID后调用公开Runtime库核验，不为预检伪造临时UID。
	var templates struct {
		ProtocolVersion uint32 `json:"protocol_version"`
		Scope           string `json:"scope"`
		Templates       []struct {
			Asset  string          `json:"asset"`
			Policy json.RawMessage `json:"policy"`
		} `json:"templates"`
	}
	if control.UnmarshalObject(policies, &templates) != nil || templates.ProtocolVersion != 1 || templates.Scope != "neon-dsga-policy-templates-v1" {
		return fmt.Errorf("original complete policy templates required")
	}
	found := 0
	for _, entry := range templates.Templates {
		if entry.Asset == "dsga-native-birth.json" {
			var policy struct {
				BuildManifestSHA256 string `json:"build_manifest_sha256"`
				PGMajor             uint32 `json:"pg_major"`
			}
			if json.Unmarshal(entry.Policy, &policy) != nil || policy.BuildManifestSHA256 != c.NativeBuildSHA256 || policy.PGMajor != major {
				return fmt.Errorf("native policy does not bind original Builder manifest")
			}
			if e := renderNativeMajorMatches(native, major, entry.Policy); e != nil {
				return e
			}
			found++
		}
	}
	if found != 1 {
		return fmt.Errorf("exact original native build policy missing")
	}
	return nil
}

func renderBootstrapFiles(vm *vmv1.VirtualMachine, in renderFiles) (map[string][]byte, error) {
	if vm == nil || vm.UID == "" || vm.ResourceVersion == "" || vm.Spec.DSGABootstrap == nil || vm.Spec.DSGABootstrap.Ready {
		return nil, fmt.Errorf("actual original held VM required")
	}
	raw, e := renderInput(in.sourceTemplate, 16<<10, true)
	if e != nil {
		return nil, e
	}
	var source resourceguard.SourceConfig
	if json.Unmarshal(raw, &source) != nil || source.Config.VMUID != "" || source.Config.ComputeInstanceID != vm.Spec.DSGABootstrap.ComputeInstanceID || source.Config.ExecutionModel != resourceguard.TrustedControllerExecutionModel {
		return nil, fmt.Errorf("unbound original trusted resource creation template required")
	}
	source.Config.VMUID = string(vm.UID)
	if e = source.Validate(); e != nil {
		return nil, fmt.Errorf("original typed resource template rejected")
	}
	sourceRaw, e := json.Marshal(source)
	if e != nil {
		return nil, e
	}
	configRaw, e := renderInput(in.computeTemplate, 1<<20, true)
	if e != nil {
		return nil, e
	}
	config, e := renderObject(configRaw)
	if e != nil {
		return nil, e
	}
	spec, e := renderObject(config["spec"])
	if e != nil {
		return nil, e
	}
	dynamic, e := renderObject(spec["dynamic_shared_buffers"])
	if e != nil {
		return nil, e
	}
	var protocol uint32
	var uid, compute string
	var minimum, bootstrap uint64
	if fixedJSON(dynamic["protocol_version"], &protocol) != nil || protocol != 2 || fixedJSON(dynamic["vm_uid"], &uid) != nil || uid != "" || fixedJSON(dynamic["compute_instance_id"], &compute) != nil || compute != source.Config.ComputeInstanceID || fixedJSON(dynamic["minimum_guest_memory_bytes"], &minimum) != nil || fixedJSON(dynamic["bootstrap_buffer_bytes"], &bootstrap) != nil || bootstrap == 0 {
		return nil, fmt.Errorf("original unbound native v2 creation template required")
	}
	slot, exact := vm.Spec.Guest.MemorySlotSize.AsInt64()
	minSlots := uint64(vm.Spec.Guest.MemorySlots.Min)
	if !exact || slot <= 0 || minSlots > ^uint64(0)/uint64(slot) || minimum != minSlots*uint64(slot) {
		return nil, fmt.Errorf("native minimum differs from original held geometry")
	}
	upper, e := source.Limits.TotalUpperBytes()
	if e != nil || upper > minimum || bootstrap > uint64(source.Limits.MemoryMaxBytes) {
		return nil, fmt.Errorf("original resource bootstrap does not fit native minimum")
	}
	// 原可信输入只携带公钥。既不生成seed、也不从测试key/模型Source复制凭据。
	publicKey, e := originalPublicControlKey(configRaw)
	if e != nil {
		return nil, e
	}
	if publicKey != source.ControlPublicKey {
		return nil, fmt.Errorf("original credential public keys differ")
	}
	dynamic["vm_uid"], _ = json.Marshal(string(vm.UID))
	spec["dynamic_shared_buffers"], e = json.Marshal(dynamic)
	if e != nil {
		return nil, e
	}
	config["spec"], e = json.Marshal(spec)
	if e != nil {
		return nil, e
	}
	configRaw, e = json.Marshal(config)
	if e != nil {
		return nil, e
	}
	policies, e := renderInput(in.policies, 16<<10, false)
	if e != nil {
		return nil, e
	}
	nativeBuild, e := renderInput(in.nativeBuild, 32<<10, false)
	if e != nil {
		return nil, e
	}
	contract, e := renderInput(in.contract, 16<<10, false)
	if e != nil {
		return nil, e
	}
	var build renderBuildContract
	if control.UnmarshalObject(contract, &build) != nil {
		return nil, fmt.Errorf("original release build index required")
	}
	if e = sameRenderBuild(vm, build, policies, nativeBuild); e != nil {
		return nil, e
	}
	data := map[string][]byte{"config.json": configRaw, resourceguard.ResourceSecretKey: sourceRaw, resourceguard.PolicyTemplatesSecretKey: policies}
	total := 0
	for _, b := range data {
		total += len(b)
	}
	if total > 1<<20 {
		return nil, fmt.Errorf("complete original Runtime Secret too large")
	}
	return data, nil
}
func publishRenderedFiles(dir string, data map[string][]byte) error {
	if !filepath.IsAbs(dir) || filepath.Clean(dir) != dir || dir == "/" {
		return fmt.Errorf("private persistent output directory required")
	}
	parent := filepath.Dir(dir)
	st, e := os.Lstat(parent)
	if e != nil || !st.IsDir() || st.Mode().Perm()&0077 != 0 {
		return fmt.Errorf("render parent must be an existing private directory")
	}
	if current, e := os.Lstat(dir); e == nil {
		if !current.IsDir() || current.Mode().Perm()&0077 != 0 {
			return fmt.Errorf("existing render output is not private")
		}
		entries, e := os.ReadDir(dir)
		if e != nil || len(entries) != len(data) {
			return fmt.Errorf("existing render output is not the original complete set")
		}
		for key, wanted := range data {
			b, e := renderInput(filepath.Join(dir, key), 1<<20, true)
			if e != nil || !bytes.Equal(b, wanted) {
				return fmt.Errorf("existing original render output differs")
			}
			f, e := os.OpenFile(filepath.Join(dir, key), os.O_RDONLY|unix.O_NOFOLLOW, 0)
			if e != nil {
				return fmt.Errorf("original rendered file durability unavailable")
			}
			se, ce := f.Sync(), f.Close()
			if se != nil || ce != nil {
				return fmt.Errorf("original rendered file durability unconfirmed")
			}
		}
		// 前次可能已rename但父目录fsync未确认。只读同字节不能把这类Unknown
		// 当耐久成功；重新确认原文件/目录/父目录，不覆盖或生成新内容。
		for _, path := range []string{dir, parent} {
			d, e := os.Open(path)
			if e != nil {
				return e
			}
			se, ce := d.Sync(), d.Close()
			if se != nil || ce != nil {
				return fmt.Errorf("original rendered directory durability unconfirmed")
			}
		}
		return nil
	} else if !os.IsNotExist(e) {
		return fmt.Errorf("render output unavailable")
	}
	stage, e := os.MkdirTemp(parent, ".runtime-render-")
	if e != nil {
		return fmt.Errorf("private render staging unavailable")
	}
	defer os.RemoveAll(stage)
	for key, b := range data {
		f, e := os.OpenFile(filepath.Join(stage, key), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if e != nil {
			return e
		}
		_, we := f.Write(b)
		if we == nil {
			we = f.Sync()
		}
		ce := f.Close()
		if we != nil || ce != nil {
			return fmt.Errorf("rendered file durability unconfirmed")
		}
	}
	d, e := os.Open(stage)
	if e != nil {
		return e
	}
	se := d.Sync()
	ce := d.Close()
	if se != nil || ce != nil {
		return fmt.Errorf("rendered set durability unconfirmed")
	}
	if e = unix.Renameat2(unix.AT_FDCWD, stage, unix.AT_FDCWD, dir, unix.RENAME_NOREPLACE); e != nil {
		return fmt.Errorf("render output publication unconfirmed; original output retained")
	}
	d, e = os.Open(parent)
	if e != nil {
		return e
	}
	defer d.Close()
	return d.Sync()
}
func (p *preparer) render(ctx context.Context, in renderFiles) error {
	vm, _, e := p.held(ctx, false)
	if e != nil {
		return e
	}
	// held内第一次Get后还会Load journal；同一次返回的完整快照也须匹配原模板。
	if e = originalVM(p.wanted, vm, p.state.VMUID); e != nil {
		return e
	}
	if vm.Spec.DSGABootstrap.Ready || p.state.SecretUID != "" || p.state.SecretCreateMayHaveSent || p.state.ReleaseMayHaveSent || p.state.Complete {
		return fmt.Errorf("render only before original Secret/bootstrap publication")
	}
	data, e := renderBootstrapFiles(vm, in)
	if e != nil {
		return e
	}
	hash := dataHash(data)
	if p.state.SecretDataSHA256 != "" && p.state.SecretDataSHA256 != hash {
		return fmt.Errorf("original retained creation inputs changed")
	}
	p.state.SecretDataSHA256 = hash
	if e = p.save(); e != nil {
		return e
	}
	// 只写私有三份输入。没有Kube写、Secret UID投影、runtime许可或PG/VM效果。
	return publishRenderedFiles(in.outputDir, data)
}
