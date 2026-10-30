# PG17 Helm DSGA Agent/Scheduler 接线

本批只在 Linux 自有 neon-helm 功能分支扩展 Agent/Scheduler 配置与离线验证。
没有部署、修改集群、修改 AS/控制面源码或提交推送。运行事实以对应
artifacts/pg17-dsga/ 时间戳目录的 summary.json 和原日志为准；本文不预填运行通过。

## 实际读取与节点身份

2026-10-30T12:36:13Z 通过 Linux 已有 kubectl 只读采集完整 NodeList 和版本：
Kubernetes v1.31.2，四节点均 Linux/amd64、Ready、无 taint。用户允许
worker-117/118/119，排除 ubuntu/116。当前四节点均没有本项目 pool 标签。

charts/neon-autoscaler/files/pg17-node-identities.json 保存这次真实的三节点 UID
及原 NodeList SHA256；模板会拒绝另一 UID，不能将同名重建节点当原域收养。
身份快照不是系统预算、平台资格或执行许可。Node 真实重建必须重新认证并更新
明确绑定，不能靠读取“最新 UID”自动恢复旧账本。

实际 PG17-S-H05 只证明节点/版本读取和兼容范围，PG17-S-H04 节点池标签验收
当前未准备。不要将 Ready 或身份格式通过当作可部署/扩缩容通过。

## 配置入口

neon-autoscaler 新增 dsga.enabled，默认 false 以保留旧配置语义。
启用时还会拒绝非1.31 minor及 allowUntestedKubernetes 旁路。
本轮专用 profiles/pg17-memory/neon-autoscaler-required.json 显式启用 PG17。
该 overlay 刻意不补未知 CA/原 Lease/profile/预算，单独使用必须失败，
不是一份已具备实际运行条件的 values。

启用后 Agent 配置增加真实源码的 config.dsga：

- gatewayURL 只允许受信 HTTPS 根 URL，禁止用户信息、路径、query/fragment。
- managementCASecret/key 只投射公共 CA 选中 key 至固定 ca.crt 文件；
  Secret 必须存在于 Agent 的 kube-system namespace。它不能是中心签名私钥。
- 专用投射 token 固定 audience=neon-dsga-credential-broker，600..3600 秒；
  与中心签给 Compute 的 neon-dsga 短 token 是不同身份。
- K8S_POD_UID 来自 DownwardAPI metadata.uid，不接受 values 或固定 UID。
- CA/token/配置只读、无 subPath，保留 Kubernetes 原子投射与轮转。
- requestTimeoutSeconds、computeTimeoutSeconds、pollIntervalSeconds 对齐源码界限。
- prepareQualifications 按真实原 VM UID 固定 claim 名称/UID/SHA256；
  automaticMemory 只接受同一 UID 已选原资格的精确目标与显式时间/阈值。
  不推测生产参数，不从 VM 普通注解接受资格或 URL。

ConfigMap 从原 Chart 基础 JSON 加入 DSGA 字段，基础 legacy 配置语义不变；
配置 checksum 会触发相应 Agent/Scheduler Pod 的受控滚动更新。
没有自动创建 CA、长期签名材料、资格证书或 token Secret。
VM namespace 和每个原 Host Lease 的 namespace 必须在安装前存在；本 Chart 不接管它们。

automaticMemory/prepareQualifications 空映射仅能作为初始化/待配置状态。
它不代表自动伸缩已开启或回归通过；正式自动伸缩必须有经过平台认证的原实例
映射、启动规格及后续精确目标。格式和 SHA256 不是平台认证。

Scheduler 插件 config.dsgaHost.nodes 要求恰好三台原节点，每项需要：

- binding.node_name、node_uid、namespace、lease_name、lease_uid。
- 已认证 profile.id、scheduler_name=autoscale-scheduler、vm_overhead_bytes、
  pod_overhead_bytes 和持续硬约束的 system_bytes。
- 首次初始化可提供冻结的 initialize_at_resource_version。
  这是一次性原 RV，不自动刷新；已存在原账本的恢复不重新初始化。

所有 uint64 字节值是规范十进制字符串，保留超过 2^53 的精度，
拒绝 JSON/YAML 数字、0、前导零和溢出。系统预算不取自 allocatable、
空闲页、RSS 或虚构比例。没有默认 Host profile、Lease UID、预算或资格。

## 原身份快照验收

只有主任务单机门槛达标后，才准备实际创建域和部署。
准备了真实输入、节点池及原 Host Lease 后，可使用只读文件检查：

    python3 tools/check-pg17-dsga.py --check-inputs 实际完整values.json \
      --nodes 实际全集群nodes.json --leases 实际原leases.json

工具不会执行 kubectl，不创建/替换 Lease，不改标签，不刷新冻结 RV。
检查节点池排他性、已观察原 Node UID、原 Lease UID/Node owner/marker、
首次初始化 RV 或既有账本存在性。输出只说明原身份与范围；
预算/平台资格和运行认证仍由真实领域生产者/消费者验证。

## 权限与实际 Host 范围门槛

新增角色只授予：Agent 在 VM namespace 的 owner Lease 操作及来源 ConfigMap GET；
仅配置原资格时，另给已有 Prepare Outside 的 CREATE，不给 UPDATE/PATCH/LIST/GC；
Scheduler 仅对三台明确节点 PATCH ledger，在 VM namespace 处理 Pod/来源；
各原 Host Lease 按 namespace/name 精确 GET/UPDATE，Agent 只 GET。
没有授予原 Host Lease CREATE/DELETE、Secret 读取、通配权限或
全 namespace 普通 Pod 的写权限。上游旧 watcher/framework 绑定本批保留，
不能将“新增权限受限”宣称为整套既有 RBAC 已通过最小权限认证。

准确 AS 的 hostscheduler 会枚举所选节点全部 namespace 的普通已有 Pod：
初始化要求完整硬内存额度，后续 Reserve 会添加 protection finalizer。
这包括已有 kube-system Pod，不只 neon。当前新增角色不会悄悄放开这些写。
必须由主任务解决整节点普通 Pod 额度/保护范围与权限策略后，才能认为 Host
模式可运行；不能跳过这些 Pod、按请求打折或给 cluster-admin 让测试变绿。
这项部署前门槛明确归档为未执行，不修改 AS 规避它。

## 准确源码与控制面边界

locks/pg17-dsga-runtime-source.json 固定 AS
02a1b0c90e58e3dfed2bb9f2c7c44e98a207ca28 的准确接口与文件摘要，
包括 Agent config、Host Config/Binding/Profile、专用 token audience、
原资格与自动策略。未修改 AS 源码。

Linux 经显式现有 HTTP_PROXY 执行 git ls-remote 确认：
https://github.com/william-lbn/control-plane.git
codex/dsga-control-plane-v3-20261020
d84c0b73004a7d8cc3e89f3c3f0e3f06cfa8cba9。
本批没有将 Mac 代码拷到 Linux，也没有创建控制面 checkout。

后续该分支最小修复需直接从 GitHub 在 Linux 获取：
dsga_vm.go 的 QMP 改为新 AS 要求的 Sysfs；把三节点 pool nodeSelector
作为原创建计划的冻结输入传入 VM。必须兼容或明确拒绝旧冻结计划，
不能在恢复时读取新 env 静默改 placement。中心还需8444专用监听、
独占证书私钥与允许的 kube-system/autoscaler-agent 主体等接线。

## 检查编号与执行入口

    python3 tools/check-pg17-dsga.py
    python3 tools/check-pg17-dsga.py --typed-contract

第二条复用现有 Go1.24.3 开发镜像及 BuildKit shared cache，
通过额外 fixture context 读取 Helm 输出，不往 AS 源目录塞测试文件。
使用已安装 builtin frontend、RUN 禁网、每次 nonce 强制真正执行；
local exporter 保存真实 Go 契约收据与容器内实际 COPY 快照的 Go 文件摘要，
不拿宿主随后并行修改冒充执行源码。宿主前后变化另行记录。
主代理已实际核实 BuildKit 同 ID 混用 locked/shared 可能选择不同 mutable ref，
旧缓存不完整时禁网契约会如实失败。本工具最终统一使用独立模块 cache ID
 autoscaling-gomod-amd64-shared-v2/sharing=shared，编译缓存保留原 ID/sharing=shared，
不再混用旧 locked refs。旧缓存不删除，历史失败不改写。
仅在确实缺依赖时显式执行 python3 tools/check-pg17-dsga.py --prepare-cache：
它通过现有明确代理请求实际 Go module info，探测通过后只执行
 go list -mod=readonly -deps ./pkg/agent ./pkg/dsga/hostscheduler，前后比对mod/sum，
单独以 PG17-ENV-H01 归档。它不运行测试；真正 typed 契约仍为禁网 RUN。
每个运行记录所加载 Dockerfile SHA256，不是缓存结果或接口桩。

| 编号 | 内容 |
| --- | --- |
| PG17-U-H07 | Agent PodUID/公共CA/专用token与Scheduler原输入精确渲染 |
| PG17-U-H08 | 版本、身份、URL、超时、原域、预算、策略与不完整启用拒绝 |
| PG17-U-H09 | 新增 RBAC 范围、原 Lease 禁止重建、停用撤销 |
| PG17-U-H10 | 准确 AS 接口与真实节点身份来源锁比对 |
| PG17-U-H11 | 原Node/Lease重建、owner/marker/RV漂移及部分NodeList拒绝 |
| PG17-S-H05 | 实际只读 Node/Kubernetes 身份与版本记录 |
| PG17-S-H06 | 实际 Agent.ReadConfig / Host Config.Validate、缺PodUID预先拒绝及真实负路径 |
| PG17-S-H07 | 实际原 Host Lease/profile/system预算与每 VM 资格，尚无这些来源 |
| PG17-S-H08 | 全节点普通 Pod 硬额度/保护范围及完整 RBAC，尚未解决 |
| PG17-S-H09 | 真实gateway/CA/token/Runner/PG17自动扩缩容，单机门槛后执行 |

所有合成 Lease/VM/资格/预算/策略及 example.invalid 镜像仅存在于明确
OFFLINE-NOT-DEPLOYABLE 的 artifacts fixture 中，不能用于部署。
失败与未执行记录不会改写为通过。Source input SHA256 绑定实际测试输入。

## 并行控制面结果补记

最小控制面 v3 已由独立子任务在 Linux 实现：冻结完整 placement.node_selector 与
allowed_node_names，固定 Sysfs，原计划深拷贝；v2未绑定拒绝新创建，既有同UID恢复不读env补授权。
实际 Go1.27.1 race 采用17 root/57 subcase通过，含隔离metadata PG，未做实际Kube/KVM/内存E2E。
详见 /data/neon-build/src/control-plane/docs/PG17-冻结三节点放置与Sysfs-Linux验收-20261030.md。
本次仅记录并行结果，不替其他仓库提交或声称其已推送；主代理统一绑定准确提交。

最终执行顺序已按所有者最新要求固定：PG17首版全部缺口（含安全normal降限）及Linux/K8s完整端到端通过后，才重新取得届时最新自有控制面完成正式接入，再推进PG18/PG16底层适配与统一回归。前期最小VM profile/Sysfs修复不是最终控制面对接基线。

本批运行接口来源锁已绑定GitHub已推送的AS `79ec6501da167e6ae7abb47a48065e722865e611`，精确接口SHA与禁网真实类型门槛在独立干净Linux工作树复验通过；CRD锁仍保留内容相同的原准确02a来源。已归档小型原始收据及673文件的实际编译源码摘要；并行normal实现未混入本次证据。
