# PG17 trusted Runtime 的首次部署准备

当前阶段仅完成部署接线与定向验证，没有执行 Kubernetes 部署，未签发任何资格，Linux/K8s 端到端验收仍未完成。新模式必须显式选择 `compute.startupMode=trusted-runtime-v1`；原默认 `legacy` 入口保留。

## 原始输入

`profiles/pg17-memory/neon-compute-trusted-required.json` 只选择 PG17、CPU2、初始/最小7GiB、最大8GiB及 `trusted-controller-v1`。它不是可直接部署的发行值。必须另外提供实际 Guest、Runner、kernel 镜像 digest，原 incarnation/Compute 实例、ServiceAccount、实际镜像构建计划的配置路径，以及实际 tenant/timeline。三节点约束固定为 worker-117、worker-118、worker-119，排除116。

PCP1024、固定P、System硬限及初始数组额度来自实际内核/镜像/完整 Runtime policy，不通过 Helm 容器 limit 或 execution_model 字符串生成预算许可。Agent 不新增同名执行模型字段；它使用已有认证接口和实际协商能力。实际资格仍须原 owner/Runner/Host 生产链建立，本工具不生成 qualification。

## 构建

本工具没有独立的 `go.mod` / `go.sum`；Helm 仓库也没有 Go 主模块。它从指定 autoscaling 源码根使用该模块的 `go.mod` / `go.sum` 编译公开库，不能在工具目录直接执行 `go build .`。`source-lock.json` 固定本轮 AS 提交、模块文件和4个生产/4个测试源码 SHA；它是明确构建输入记录，不是新增 Go replace 或自报资格。旧 f1f 构建票里的 e8c6 是旧构建 AS 输入，不是 Helm 的依赖版本。

从 GitHub 下载本 Helm 仓库后，在仓库根执行以下步骤。AS 原功能分支保留；只在新的专用 clone 读取固定提交并导出隔离源码，不对现有开发工作树切分支、detach 或 reset。下列两个目标目录必须是本次尚不存在的新目录。

```sh
TASK_TOOL_SOURCE="$PWD/tools/runtime-prepare"
TASK_AS_CHECKOUT=/data/neon-build/validation/runtime-prepare-as403eb25-clone
TASK_AS_SOURCE=/data/neon-build/validation/runtime-prepare-as403eb25-source
TASK_AS_COMMIT=403eb25b6821536c26bb1d0dbb91c7afce3ec311
# GitHub 网络沿部署者既有显式代理设置；本步骤不改代理或网络配置。
test ! -e "$TASK_AS_CHECKOUT" && test ! -e "$TASK_AS_SOURCE"
git clone --filter=blob:none --no-checkout --single-branch \
  --branch codex/dsga-autoscaling-20261019 \
  https://github.com/william-lbn/autoscaling.git "$TASK_AS_CHECKOUT"
git -C "$TASK_AS_CHECKOUT" cat-file -e "$TASK_AS_COMMIT^{commit}"
mkdir -m 0700 "$TASK_AS_SOURCE"
git -C "$TASK_AS_CHECKOUT" archive "$TASK_AS_COMMIT" | tar -x -C "$TASK_AS_SOURCE"

python3 - "$TASK_AS_SOURCE" "$TASK_TOOL_SOURCE" <<'CHECK_SOURCE'
from pathlib import Path
import hashlib, json, sys
as_source, tools = map(Path, sys.argv[1:])
lock = json.loads((tools / "source-lock.json").read_text())
for root, entries in [(as_source, lock["autoscaling_module_files_sha256"]),
                      (tools, lock["production_files_sha256"]),
                      (tools, lock["test_files_sha256"])]:
    for name, expected in entries.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
print("固定 AS 模块文件及4个生产/4个测试源码摘要一致")
CHECK_SOURCE

cd "$TASK_AS_SOURCE"
GOWORK=off CGO_ENABLED=0 go build -mod=readonly -p=2 -ldflags="-s -w" \
  -o /data/neon-build/bin/neon-runtime-prepare \
  "$TASK_TOOL_SOURCE/main.go" "$TASK_TOOL_SOURCE/render.go" \
  "$TASK_TOOL_SOURCE/recovery.go" "$TASK_TOOL_SOURCE/service.go"
GOWORK=off go test -mod=readonly -p=2 -race -json -count=1 -timeout=90s \
  -run '^(TestRuntimePrepare|TestRuntimeRender|TestRuntimeRetire|TestRuntimeManagementService)' \
  "$TASK_TOOL_SOURCE/main.go" "$TASK_TOOL_SOURCE/render.go" \
  "$TASK_TOOL_SOURCE/recovery.go" "$TASK_TOOL_SOURCE/service.go" \
  "$TASK_TOOL_SOURCE/main_test.go" "$TASK_TOOL_SOURCE/render_test.go" \
  "$TASK_TOOL_SOURCE/recovery_test.go" "$TASK_TOOL_SOURCE/service_test.go"
```

必须列全4个生产文件及4个测试文件，遗漏 recovery.go 或 service.go 会直接编译失败。`GOWORK=off` 防止外围工作区替换固定模块，`-mod=readonly` 防止构建修改原模块锁。已有原 Go 模块缓存可直接复用；全新机器需要按原 go.mod/go.sum 下载第三方依赖，不从旧 CP 的 go.mod 获取 AS。

本轮生产工具输入为 AS403eb25，Helm四个生产Go文件保持979原字节。实际同源编译在 `host-v10-six-reader-release-20261103T172102Z-ffde4b` 完成，6个读者全部编译和CLI help成功，11666份前后源码校验一致。Runtime ELF SHA256为 `c7d8c8fa5733aad8e4591efbfba6c471e392402a2662b257a965ff751c6a6f4f`；准确来源、资源与结果见 source-lock。

14个 race 测试根、67个 pass 事件来自9f7061的Runtime成功子阶段（测试/CLI/help均0）。该批整体仍是FAIL，因为独立Owner测试准备使用了Linux不存在的Mac临时目录；修复后单独181634已通过，原失败票保持。ffde4b在16个AS生产文件和8个工具文件SHA逐项相同后明确复用Runtime结果，不反复刷已通过用例。

新增用例验证：VM/Pod已404但Host v10仍持有原11Gi Pod floor时，工具必须拒绝确认退役；原Node owner已结清该行后，沿同一私有state和原意图继续观察，原DELETE仅派发一次，不写Node/Pod/Secret或重置账本。typed fake HTTP只证明工具协议，不替代真实Guest退出、QEMU硬限或Neon内存端到端。

不同绝对源码路径或Go工具链重编的ELF不保证逐字节相同，本记录不冒称可重现二进制认证。PG/Guest normal真实硬降限及三节点实际功能仍按最终计划验收。

## 先持有，再封存，再由原 CAS 释放

1. 使用真实发行值 `helm template --namespace <实际命名空间>`；提取 VirtualMachine 为 JSON，保留原始 manifest。新模式从 CREATE 即 `dsgaBootstrap.ready=false`，未写入 VMUID 或 SecretUID，不会在配置尚未绑定时启动。
2. 显式 `hold`：实际 API 创建或读取同一个 held VM，取服务器分配 UID，调用原 `journal.Initialize`；状态文件必须在持久 `/data` 私有目录，0600并独占锁。缺失或不确定的 CREATE 原 UID 不会按同名对象补造。
3. 在实际 VMUID 已知后，使用显式 `render` 只读原API并绑定原私有模板（见 RENDER.zh-CN.md），生成该 VM-bound `config.json`、`dsga-resource.json` 与完整 `dsga-policy-templates.json`。资源 Source.Config 的 execution_model 必须明确为 trusted-controller-v1；Compute 公钥、VMUID/Compute实例/初始预算与模板必须一致。不得用离线测试 seed、模型预算、手写资格代替实际来源。
4. 显式 `seal`：工具检查实际 VM UID/RV、原 immutable Secret UID/ownerref/三份准确字节，通过公开 `bootstrap.Runtime`、`RenderRuntimePolicyAssets`、`DeriveRuntimeBootRequirements` 完整预检。只由原 `journal.ReleaseBootstrap` 的 UID/RV CAS 释放。Secret 数据不打印到日志。
5. `inspect` 为默认动作，只读实际保留身份和原 bootstrap。失败时保留状态、原 nonce、API结果及日志，先核原对象，禁止删除状态或同名重建以绕过 Unknown。

```sh
neon-runtime-prepare -action hold -kubeconfig <既有配置> -vm-json <原held-vm.json> -state /data/<本次归档>/deployment/state.json
neon-runtime-prepare -action seal -kubeconfig <既有配置> -vm-json <原held-vm.json> -state /data/<本次归档>/deployment/state.json -compute-config <实际config.json> -resource-config <实际dsga-resource.json> -policy-templates <原完整dsga-policy-templates.json>
neon-runtime-prepare -action inspect -kubeconfig <既有配置> -vm-json <原held-vm.json> -state /data/<本次归档>/deployment/state.json
```

本工具仅用于 pristine 首次创建。已有运行历史/owner接管不能重新包装成首次来源，恢复走原运行期合同。工具不启动旧控制面服务，不创建私钥/签名体系，不写PG、cgroup或QMP，不替代 normal 降限、VM物理读回或三节点 Helm 回归。

## 已验证边界

- Helm：新模式正控渲染/命名空间/held/固定CPU与内存形状通过，lint通过；缺输入、未知模式、错误CPU/内存/Secret/incarnation/镜像与节点范围均拒绝。
- 部署工具：实际公开 Runtime 库与原 ReleaseBootstrap CAS 的 typed fake API 正控；原 UID/Secret owner/immutable/字节漂移、未确认CREATE的同名对象、坏policy保持held等定向 race 单元测试通过。
- 额外用真实已编 CLI 解析最终 Helm VM JSON，完整原 typed manifest 门通过，故意不存在的 kubeconfig 使其在任何 API 访问前停止。此前写成 Sysfs 的 CRD枚举已修为原 SysfsScaling；旧离线渲染成功不冒充API就绪，原件保留。
- 后继render与手工seal共用严格public-only JWK检查，私钥d/未知成员在任何Secret API前拒绝，合法kid保留；这不更改AS库或签名体系。
- 首两次工具测试夹具 helper 六字段不全导致 Runtime 拒绝，原失败保留；后继只补完整夹具和未知CREATE拒绝，未放宽生产校验。

上述不表示单服务或 E/K8s 通过；正式镜像和真实资格确认前不得使用示例 digest/测试 seed 部署。


受控退役与新 Guest 恢复：显式选择 `--action=retire`，继续使用原 `--state`、原 `--vm-json` 和原 kubeconfig。该动作先读取实际 ready VM/原 Runtime Secret UID、完整原 journal 与 Controller finalizer，再将点时 VM/同 UID CM 库存存入 state 同目录的私有内容寻址 archive；它不是退出后所有最终来源的完整归档，也不把准入 Unknown 说成已关闭。archive 和 `retire_may_have_sent` 持久之后，才用 UID/RV 前置条件正常 Delete 原 VM。

出现 DELETE 丢回复、VM 仍 deleting、网络失败、旧 Pod 尚在或任一 Node 账本未知时，动作返回未确认，保留原意图；继续用同一原 state 显式重试。不移除 finalizer、不 force delete、不修改 Node 账本或把旧 Resize 未知写成 NoEffect。Controller/Scheduler 负责原 Pod/容器退出及 Node 预算结清；工具仅在 VM 实际404、分页无旧UID Pod、全部实际 Node `InspectVMUnheld` 且再次404后记录 retired。

只要退役意图已保存，旧 state 的 hold/render/seal 永久拒绝，不等待 retired 才闭门。同名不同 UID 会拒绝，不收养新对象。新 Guest 必须换新 state、Compute 身份、incarnation，并用原 hold/render/seal 创建新 UID；若沿用 VM 名，须等待旧 config Secret 正常 GC，不能接管其 UID。需要保留业务数据时沿用原 tenant/timeline/存储数据配置，验证新 Guest 实际读回故障前已提交的数据；本工具不保证任意业务高可用或数据迁移。


## 显式17/18选择（候选源码，历史c7发行保持不变）

默认compute.pgVersion仍为17，默认/显式17的Helm输出必须与原518版本逐字一致。
18必须明确选择trusted-runtime-v1及真实18 Guest digest，不能回退17镜像。共享的
Runner、Kernel和Root无需另造18专用ELF；实际PG18及其DSO/helper/闭包由独立产物
锁和Collector/盘读回绑定。版本选择不产生Source、资格、预算或执行许可。

trusted18在原VM manifest加入neon-control/postgres-major="18"选择注解；原manifest
与后续live VM均强绑定这个字段，缺失只表示历史17，未知/畸形值拒绝。private build
scope分别为neon-pg17-trusted-runtime-build-v1或neon-pg18-trusted-runtime-build-v1。
scope、manifest选择、Native.pg_major及native-birth policy.pg_major必须一致。
18必须有本次canonical runtime_closure和完整PG/helper ELF引用，不接受旧seed冒闭包。
render只核原构建引用/字节SHA；实际文件内容仍由正式Collector和盘读回确证。

本改动不生成Collector之前缺失的业务public config、argv/env/loader plan/JWK，也不
放开旧CP中仍固定17的业务creation producer。当前真实PG18 normal/Source/E/K8s
未因此通过。旧c7二进制/source-lock及已冻结PG17 chart/40700e输入均不被此源码替换；
Root独立构建、提交、绑定和启用新private CLI后才可使用新增能力。
