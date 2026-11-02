# PG17 trusted Runtime 的首次部署准备

当前阶段仅完成部署接线与定向验证，没有执行 Kubernetes 部署，未签发任何资格，Linux/K8s 端到端验收仍未完成。新模式必须显式选择 `compute.startupMode=trusted-runtime-v1`；原默认 `legacy` 入口保留。

## 原始输入

`profiles/pg17-memory/neon-compute-trusted-required.json` 只选择 PG17、CPU2、初始/最小7GiB、最大8GiB及 `trusted-controller-v1`。它不是可直接部署的发行值。必须另外提供实际 Guest、Runner、kernel 镜像 digest，原 incarnation/Compute 实例、ServiceAccount、实际镜像构建计划的配置路径，以及实际 tenant/timeline。三节点约束固定为 worker-117、worker-118、worker-119，排除116。

PCP1024、固定P、System硬限及初始数组额度来自实际内核/镜像/完整 Runtime policy，不通过 Helm 容器 limit 或 execution_model 字符串生成预算许可。Agent 不新增同名执行模型字段；它使用已有认证接口和实际协商能力。实际资格仍须原 owner/Runner/Host 生产链建立，本工具不生成 qualification。

## 构建

该窄工具直接复用指定 autoscaling 源版本的公开库；在该仓库根目录以相同 go.mod/依赖执行：

```sh
go build -o /data/neon-build/bin/neon-runtime-prepare /absolute/neon-helm/tools/runtime-prepare/main.go /absolute/neon-helm/tools/runtime-prepare/render.go
```

`go test -race` 必须显式包含 main.go、render.go、main_test.go、render_test.go 四份文件。归档记录准确 autoscaling 全源码、工具源码、编译器、实际 COPY 校验、资源限制及产物 SHA。测试使用 typed fake API 分配 UID，是单元测试，不是 Kubernetes 实测。

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
