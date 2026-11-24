# Neon Helm 标准部署与验收

本标准以维护分支的实际代码和声明的站点配置为准。已完成完整清理、从空状态一次自动安装，以及第二轮 PG17/PG18 的公开 SQL、Guest 物理自动内存、暂停恢复和退役验收。结果见 [阶段验收报告](acceptance-20261124.zh-CN.md) 与 evidence/summary.json，不能用历史 118 结果替代。

## 站点边界与前置

本次验收为 228 的现有 RKE2 集群，5 个 worker，linux/amd64、KVM、声明的本地存储与 Harbor。内置 MinIO 使用明确许可的实验 HTTP 配置；Compute 管理和 SQL 客户端分别校验 CA 与 verify-full。这不是生产 HA、全链路 TLS、外部 S3 或多站点共享 Host 域的验收。

平台先提供 Kubernetes 管理凭据、Ready/可调度且有 KVM 资源的 worker、网络附件 CRD、共享 cert-manager、实际 StorageClass 和可用的 Harbor 摘要镜像。系统组件按当前原生发行使用 kube-system/neonvm-system；产品空间可配置，独立平台空间沿原生协议采用 neon-control-*。所有普通 Pod（包括 init container）必须有明确的内存硬限；入口检查实际值，缺失时拒绝初始化，不能以估算容量填平。

管理节点需要 Python 3.12+、PyYAML、OpenSSL 和 kubectl。发布包携带固定版本 Linux Helm、Node 及已通过原生 SDK 测试的 Host 核验工具。Harbor 与这些平台前置由运维明确配置，不属于卸载时可删除的 Neon 数据。

## 构建与安装

profiles/standard-site/site.json 声明 kubeconfig、clusterDomain、namespace、registry、存储根目录、Host 开销策略、工具镜像、9 个 release 的 Chart/values 和发行目录模板。IP、路径和运行规格是可替换的站点输入；程序不写死 worker 名单或拼接实验池标签。

控制面 Chart 来自 control-plane 对应提交的 charts/neon-control-plane。禁止用 Helm 仓库中旧的同名 Chart 替代。先提交源码，再以 package-standard-site.py 的 --control-plane-source、--runtime-bin、--host-proof 和 --out 组装包；包内 standard-source-lock.json 与 SHA256SUMS 固定源码、实际测试及二进制摘要。Go 工具的上下文生成器位于 tools/host-decommission/context.py，必须使用干净且精确的 Autoscaling 提交。

解包后检查摘要，在管理节点执行：

```bash
cd neon-standard
sha256sum -c SHA256SUMS
export PATH="$PWD/bin:$PATH"
python3 -B tools/standard-site.py install --site profiles/standard-site/site.json --state /var/lib/neon/site-install
```

state 必须是本机所有、权限 0700 的专用目录。先为独占环境选择新的目录；不要把生产或另一站点的 namespace 声明为待清理范围。

入口先确认没有旧 release、VM、Host 域或产品 PV，再生成全新密码、标准 Base64 幂等密钥、存储签名材料与证书。Namespace 的 Helm 归属只允许绑定本次入口已创建、UID 匹配的对象，不接管其他站点。

入口先创建各自 release 的依赖对象，读取新的 Service/Secret UID 后完成存储接线；管理 CA 只向 Agent 投影公钥。随后动态发现当前 worker，按原 Node UID 创建新 Lease、读取真实 capacity/allocatable、应用声明的预留与开销，准备私有 socket、预热 Agent、检查普通 Pod 硬限、冻结首次 CAS 输入。Host 账本确认后才生成新发行目录并开启控制面创建与暂停。KVM 资源使用 Kubernetes Quantity 解析，接受合法的 1k 表达。

每次实际 Helm 渲染均检查使用的镜像来自声明的 Harbor 并按 digest 可用；不能用节点缓存代替仓库可用证明。当前发行默认使用主 CNI，不部署旧的额外 VXLAN；Controller 启动仍需要的 IPAM 配置附件保留。

## 端到端流程

使用 tools/acceptance/prepare-standard-acceptance.py 的 --site、--deployment、--out 建立新验收目录。它核对本次安装输入摘要和 Namespace、API Secret、发行目录 Secret 的实际 UID，经公开 API 创建新组织。所有业务 helper 必须显式设置 NEON_SITE_ROOT、KUBECONFIG，不能复制旧 Host/PKI 回执或组织 ID。

每个 PG 大版本均执行公开创建、真实资格、Proxy verify-full SQL、10000 行校验、业务压力触发的 VM/Runner 自动 7→8→7Gi、独立 root-only 只读接口取得 Guest 物理增长与回缩、WAL 两次结清和数据保持。Root watcher 必须在压力前取得原 VM/PG 实例基线；目标 IP 来自当前 Node 的 InternalIP，不使用固定名称到 IP 映射。

随后通过原公开 Operation 暂停、确认原 VM/Runner Gone 与 Host 结算，再恢复到新 VM UID，复核原数据，最后正常退役并确认 holds/managed placements 为零。VM/Runner 清单或单独的 manifest 改变不能代替 Guest 物理证据；失败、未知和原重试操作分别留档，不重放未知写请求。

## 干净卸载

先通过公开业务流程完成 Compute 退役。独占站点可执行：

```bash
bash tools/standard-clean.sh profiles/standard-site/site.json /var/lib/neon/site-clean EXACT_SITE_NAME --erase-data
```

入口存档原 Helm 输入、对象 UID、Host 快照及私有元数据库备份；停止业务生产者并确认没有活动 Operation，再正常停止全部原容量写入者，等待原 Lease 自然过期。停域工具复用 SDK 的完整模型验证，接受新 Host 合法的 v3/v5 普通 Pod 账本以及后续 v10；未知格式、不完整来源、VM/Runner、Hold、managed placement 或未确认退出都拒绝。

正式结束原 Host 域后，普通 Pod 保护交回 Kubernetes，保留共享 CNI/DNS。只清理可证明属于原 Neon 的 VXLAN 接口、桥和 NAT 链引用；只删除声明且确认无监听的私有 socket；Node 变更绑定原 UID/RV 与原内容。旧派生标签只有原快照、完整原池及当前值共同确认时才清理。

Helm 逆依赖卸载后，删除独占 namespace 和 Neon CRD。Retain 数据卷按原 PVC/PV/Node UID 与明确的存储根目录逐一核验，仅删除原 PVC UID 对应子目录，确认物理数据不存在后删除原 PV；不递归删除整个存储根目录。原现场 8 卷；标准方案关闭重复的旧内置 Pageserver 后为 7 卷。外部 S3 不在此内置 MinIO 擦除合同内，须提供明确的供应方清理流程。

最终必须同时确认 release、独占 namespace/CRD、旧 Host 材料、普通 Pod 保护和原 PV 数据均无残留，共享平台健康且 Harbor 可用。卸载不会删除 RKE2、共享网络、StorageClass、共享 cert-manager 或 Harbor。

## 失败接续与待优化项

每个阶段先持久化意图，再执行变更。进程退出或客户端等待超时不表示操作未执行；优先查原回执、Helm history 和对象 UID。禁止手改回执制造成功、删除 VM finalizer、清 WAL 或重置预算。

reconcile-helm 仅处理原生进程明确失败、当前 revision 已失败且用户 values 与原冻结输入一致的情形；它建立新的明确 revision 并保留原失败。--retry-phase 只开放有证据证明尚未提交 Host Lease/CAS 输入的边界，或失败且 release 不存在的 Helm 安装。存在未知写入时保留原意图，不自动重放。

Root 资源读取未确认时关闭准入仍是正确选择。已修复已结清安全关闭后暂停排空的活性断点，保留原预算、Owner、实例和原 Operation 的身份校验；首次 HTTP 异常的细分根因和自动可信恢复状态机仍需后续研发，当前只使用已有受权恢复协议。

初装能够发现当时真实合格节点，Compute 放置使用 Kubernetes 原生选择条件和冻结的真实 Host 身份。当前尚无新 Node 持续注册、预算/资格接入与候选发布的完整闭环；未登记节点不会自动进入已有 Compute 的冻结池。待提供新节点后实施和验收，不能把已有节点的跨节点恢复宣称为新节点持续自动接入。

本轮 Host Chart 合同为 1..16 域、已验证 5 个 worker，控制面计划的更高上限不代表整套系统已验证该规模。其他资源规格、生产 HA/TLS、外部存储和故障恢复需分别资格与验收。既有 4 项私有 journal fixture 的跳过不计为通过。本轮核心 SQL/存储/控制面/内存流程不自动证明 Auth、Data API、Functions 等可选产品能力。

镜像构建早于最终 Git 提交，其已记录的基线加补丁不能改称为后来提交 SHA 的完整可重现认证。全量镜像与源码发行重新对齐按用户要求后续进行；当前实际所需制品已先发布 Harbor、精确摘要预检后才使用。

权限边界补充：placement.allowedNodeNames 只是放置筛选，开放筛选不能代表全局 Node 写授权。Agent 的 Node GET 与 Scheduler 的 Node GET/PATCH 都由本次可信 dsga.hostIdentities 的完整键集合生成非空 resourceNames；空可信集合直接拒绝。新增 Node 必须先完成可信登记和相应发行更新，不能借空列表扩大全局权限。本次 1、5、16 Host 渲染回归及实际 Kubernetes SubjectAccessReview 均核验该边界；Agent 始终无 Node PATCH 权限。
