# Neon Helm 标准化阶段验收报告 V3.2

最终提交包冷安装验收已完成：运行源码为Helm提交1f04cc6de49c6d8cfdd589c59a672c752a69718b，完整离线包SHA256为f025993a6a4ccabaf4610e025b0bfbf484e4e31118ee2a3a1d47f18187f9871e。当前9个release deployed、6个Node Ready、Compute VM为零，5个Host无Hold及managed placement。后续归档提交只更新本报告、手册和公开证据，运行代码/Chart/站点参数/镜像摘要保持与该已验收提交相同。


本轮核心任务已完成业务验收：新 228 集群既有 5 个 worker 的标准 Host 域建立、PG17/PG18 控制面创建、真实 SQL、自动内存增长与回缩、暂停恢复、正常退役、完整清理，以及从空状态一次自动重装后的第二轮全链路验证。最终 9 个选定 Helm release 均 deployed、6 个 Node Ready、Compute VM 为零，5 个 Host 的 holds/managed placements 均为零。普通平台 Pod 和其正常预算登记继续保留。

本报告与部署手册、evidence/summary.json 为本轮标准依据。V3.0 和早期执行草案保留为历史来源，不应继续照抄其中旧节点名单、派生标签、旧 UID、旧 CA 或“未推送/通道中断”等阶段状态。

## 一、方案结论

采用 Helm 声明工作负载与站点参数，配合有界初始化入口完成凭据、PKI、存储身份、新 Host/Lease 和发行目录接线，是合理的标准化方向。运行期资格、预算、Owner fencing、WAL 和退役结算继续由原生 SDK 协议负责。

站点配置明确 registry、namespace、clusterDomain、存储根目录、实际制品和预留策略；worker 由当时真实 Kubernetes 状态发现。生成的 Node UID、Lease UID 和冻结节点集合是本次运行身份，不能作为下一个环境的静态模板。新的部署默认使用主 CNI，保留 Controller 必需的 IPAM 配置，不再依赖额外实验 VXLAN。

当前发行声明 linux/amd64、KVM、指定平台前置和合格 Guest 规格。本轮实际验证 5 个 worker、7/8Gi 自动内存规格。更大规模、其他规格、生产 HA/TLS 和新增 Node 持续注册须分别验收，不能因本轮通过而推定完成。

## 二、从空状态一次自动安装

旧现场 8 个 Retain 卷、候选标准环境 7 个 Retain 卷均完成原 UID 绑定的物理目录清理与 PV 删除。标准环境关闭了重复的旧内置 Pageserver，故 7 卷为预期数量。清理后确认选定 release、独占 namespace/CRD、旧 Host 身份、保护标记和专用网络均无残留；保留 RKE2、共享 CNI/DNS、StorageClass、cert-manager 和 Harbor。

第二轮安装从 2026-11-24 19:01:52 开始，19:04:44 完成，共 172 秒。该次入口从 fresh-preflight 到 control-runtime-ready 一次完成，没有 retry/reconcile 或人工修改，安装输入 SHA256：

`45af92098e5b345cecd183e1454b3a46a397ec6635303750e105698f88323c7d`

前期候选试运行暴露的失败全部保留，包括 Namespace 归属、合法 KVM Quantity `1k`、幂等密钥编码、Pod 终止状态观察及新 Host 账本版本。它们不算作上述无人干预安装的成功证据。

## 三、第二轮独立业务验收

以下第二轮结果来自该轮新安装及新组织 `org_c98a8a084dc022bdce480e98`，没有复用第一轮回执。

| 项目 | PG17 | PG18 |
|---|---|---|
| 实际 PostgreSQL | 17.11 | 18.2 |
| 公开创建 Operation | op_99f1a2884fb1c549de634d7b | op_1ab3341f7d8b7cd3ebbbe5d7 |
| SQL 与数据 | verify-full；10000 行；sum(id)=50005000 | 相同 |
| 自动内存 | 原 VM/Runner 7→8→7Gi；无测试侧 VM patch/策略修改 | 相同 |
| Guest 独立物理读回（字节） | 7413817344→8487559168→7413817344 | 相同 |
| 原内存实例 | 71ba182e-5a72-446e-9fba-882b56e40d8a，node4 | 8b81e280-c92e-4eda-8c5e-be8043ac4497，node2 |
| 暂停 Operation | op_4d96b762dd02a352a7d73190 | op_62778cc8e16836c0b49852c2 |
| 恢复 Operation | op_d3590955fe22ec1d0a401c66 | op_f5a149bdc5da9878d505b766 |
| 自动调度结果 | 新 VM c85ca2e1-02a0-49d1-9bee-2f826ec34525，node5 | 新 VM 0f5af160-da7a-40c3-8b24-56697e68bc2e，node1 |
| 最终退役 Operation | op_557934f169318d9297122d16 | op_2c57bf340c88fb2eccee5f90 |
| Host 结算 | 原/恢复后 VM 与 Runner Gone；持有与 managed placement 均零 | 相同 |

两版本数据校验和始终为 `55dd7184c7eae5d9a2bae0b66e2924e3`。8 个有界标准 psql 客户端触发真实自动增长；负载后自动回缩，两条 WAL 历史结清、Active 为空。独立 root-only 只读观察绑定原 VM、Compute instance 和 PG boot；只有 manifest 数值变化不计通过。

第一轮 PG17 case003、PG18 case001 的完整结果和两个失败项目的正常清理已经另行留档。第一轮安全关闭后的原暂停 Operation 重试、跨节点恢复和原数据保持也已通过。原子阶段回执中的 NOT_COMPLETE 字段保持原样；整体验收由汇总程序逐项核对原实例与全部阶段结果，生成 BUSINESS_ACCEPTANCE_PASSED，不修改原件制造通过。

## 四、整改内容

1. 放置统一为原生 selector/affinity，保留完整 AND 条件，开放池不生成非法 In: []。控制面节点池使用完整冻结集合及前向迁移95。
2. 节点、Service、Secret、Lease 和发行目录身份在当次初始化时建立。跨 namespace Role/Binding 使用显式站点引用，保持 API、Worker、Agent 的职责分离。
3. MinIO 初始化使用 Harbor 中同时具有 shell/mc 的固定摘要镜像；初始化 Job 是配置任务，不是第二个 MinIO 服务。每次实际部署及关键业务阶段均先验证内网镜像可用。
4. 管理 CA 具备真实 CA/sign 用途，Agent 只取得公开 CA；SQL 客户端使用 verify-full。存储管理采用新签名材料、精确新 UID 和认证 HTTPS 回调。
5. Qualifier CREATE 只提交一次，只在已知原 UID 时只读确认；未知 UID 不按名字收养。补齐职责所需的只读来源权限。
6. 对已完整结清的安全关闭，Agent、控制面证明与 Gateway 同步支持原授权暂停的排空；仍核原永久预算、原 VM/PG、当前 Owner、准确关闭请求及原 Operation。
7. 新增正式 Host 停域流程：原写者全部终止、Lease 自然过期、VM/Runner/Hold/managed placement 均无，SDK 校验原模型及普通 Pod 原身份/硬限后才归还 Kubernetes。
8. 停域兼容合法的新 Host v3/v5 与后续 v10 完整普通 Pod 模型。版本上限仍由固定 SDK 的 Validate 决定，未知/不完整模型拒绝；不修改在线账本版本号。Host 模型版本与 Compute 关闭日志版本是不同协议。
9. 清理绑定原 UID/RV、原存储根与精确 PVC UID 子目录；旧 VXLAN 仅处理原接口/桥/链引用；socket 必须 root 私有、原路径且无监听。共享平台始终保留。
10. 全新安装修复 Namespace 归属、Quantity 解析、标准 Base64 幂等密钥；每阶段冻结输入、持久化意图，已知失败接续和未知结果严格区分。幂等密钥必须持久保留，不能通过重新生成来修复运行中的历史操作。

## 五、源码与验证依据

| 仓库 | 本轮来源/变更 |
|---|---|
| Autoscaling | a5e925b5f9180e083e9c86dd7be4ee3f55b014cb（前序3567）；Owner/Qualifier修复，中文提交并SSH推送；Host工具与CP依赖的SDK仍固定3567 |
| Control Plane | e8935831c6aea14f93b8414686962038815d70d2（前序 7ac94d00）；可变池、安全关闭排空、站点 RBAC 与 CI 合同，中文 SSH 提交 |
| Helm | 本报告所在提交树；标准包在 standard-source-lock.json 中记录精确提交及二进制摘要 |
| Neon | ef037b91b69cbdce4beba83e0cd282e230bb5f3b；本轮不修改其运行源码 |
| PostgreSQL 17 | 646159ec9e7a5a53ca19cf77184efd8684431855；无源码变更 |
| PostgreSQL 18 | 47f4ff0d390996bffeaa6a14aa58ea6c29637855；无源码变更 |

公开 SDK 依赖完成真实 PostgreSQL/网关 262 项回归，无失败无跳过；Host 停域/socket 工具 30 项原生测试、5 项 Quantity 回归均通过。源码扫描、Node/Helm 模板、组合所有权/NodePort、DSGA 权限拒绝门及包检查分别留有回执。实际 GitHub CI 状态由最终交付索引列出，不沿用旧 HEAD 的成功。

所有新提交正常快进到指定维护分支；通过 118 显式代理读取远端 HEAD，使用 SSH 推送并读回确认。无变更的 Neon/PG 分支不做空提交。

## 五补充、权限收紧版第三轮实测

复核发现开放 placement.allowedNodeNames 时，旧 Scheduler Role 的空 resourceNames 会授予所有 Node 的 PATCH 权限。该问题已按可信 dsga.hostIdentities 的非空完整键集合修正，放置筛选与权限集合分开。1、5、16 Host 渲染回归通过；真实 SubjectAccessReview 证实 Scheduler 只可 PATCH 五个可信 worker、master 被拒绝，Agent 对所有 Node 都无 PATCH 权限。新 Chart 已再次完成干净清理和从空状态一次自动安装：21:14:56→21:17:40，七个 Retain 卷物理清理，平台/Harbor保留，新 Host 冷启动激活全部成功。

该轮原 PG17 case001 在 node3 的资格发布阶段失败，日志只保留 publication/unconfirmed，未保留细分原错误；不能断言根因就是后述来源漂移，也不能把它误称为 Root HTTP 异常。原 Project 经公开删除 Operation op_93b7201444d1b7f1c1c14265 正常退役，VM/Runner 与 Host 持有全部结清，失败回执保留。

源码审查另发现明确活性缺陷：发布前两次完整只读来源不同就直接终止。修复以 SDK 具名错误证明该分支尚未进入 CREATE，仅在原期限内重读同一报告；不重新采集或更换报告。未知 CREATE、没有原返回 UID、替换原身份仍拒绝。发布前新增固定白名单诊断码。CLI/SDK 共72项通过、无失败无跳过；新 Qualifier f8bbfbac40ae9dc10f3d131e66270ab1d9c571ba61aadca523ca6d702d3772df 已在118编译、发布Harbor，228精确摘要预检后滚动更新新实例发行目录，未修改原冻结计划。

第三轮新组织 org_722655a24e7590823feac2c5 的最终通过案例如下，均使用新 Qualifier：

| 项目 | PG17 case002 | PG18 case001 |
|---|---|---|
| 创建Operation | op_8645d78a9b2eced5b6abf540 | op_20b8b15cfa5be82da55eb690 |
| 原VM/Node | 302888ce-0dfd-49bd-85fd-d080bd2f9a8f / node1 | 8b26ca3c-45d5-4622-88a2-f4df5da5c0ca / node3 |
| 自动内存 | 7→8→7Gi；8个标准psql客户端；WAL历史2条结清 | 相同 |
| 原Guest独立物理内存 | 7413817344→8487559168→7413817344 | 相同 |
| 暂停Operation | op_fc376d87c33a52d57dcc83ec | op_72b311c3245ca7863cd389c1 |
| 恢复Operation | op_9cfeb821b11663c9c2f333ea | op_4ff1db4f572210503ad63cae |
| 恢复VM/Node | 5eb48958-a9d6-410a-a9a1-5a9015b10578 / node5 | dcba2e62-b00a-4083-acd7-5af004d53c6d / node1 |
| 退役Operation | op_bc06aba855c99aa56b6ca2af | op_bc38447a83ac766be3e60c88 |
| 最终结果 | 全部succeeded；VM/Runner Gone；Host持有归零 | 相同 |

两版本均 verify-full、10000行、sum(id)=50005000、校验和55dd7184c7eae5d9a2bae0b66e2924e3；原Compute/PG身份在内存往返中保持，无测试侧VM patch或策略修改。PG18在此前失败的node3上完整通过资格、SQL和自动物理内存，不能以排除该节点制造成功。

该轮是空态安装后必要的单组件滚动升级验收；下一节第四轮另以精确提交包完成整套冷安装，二者证据分开。

## 五补充之二、精确提交包最终冷安装验收

先核对离线包SHA256、源码锁和包内全部SHA256SUMS，再正式停止旧写者并以原UID/RV结束Host域、归还普通Pod保护、删除七个Retain卷的原物理目录。22:53:06空态验收通过，随后同一入口用包内已提交工具安装；22:55:35全部27阶段一次成功，约150秒，没有人工接线、retry-phase或Helm reconciliation。Harbor及RKE2/CNI/DNS/StorageClass/共享cert-manager保留。

该次新组织org_91c96b773f0c4130df5efaf6，PG17和PG18均为全新case001，公开创建首次成功，未换案例或重放Operation。Qualifier f8bb从冷安装目录生成，不依赖上一轮滚动更新。两版本verify-full、10000行、sum(id)=50005000、md5=55dd7184c7eae5d9a2bae0b66e2924e3；各8个有界标准psql客户端触发原VM/Runner自动7→8→7Gi，原Guest独立物理7413817344→8487559168→7413817344，原Compute/PG实例未变，WAL历史2条完整结清、Active为空，无测试侧VM patch或策略更改。

| 项目 | PG17 | PG18 |
|---|---|---|
| 创建 | op_e8be0fc0f00fcc27c5164086 | op_a3bc0682fb58e7926d437e51 |
| 原VM/节点 | 13f67938-555d-4de2-87e9-476fbdc4b362 / node2 | 56018c5b-0244-4490-a0f9-9fa6886a0fef / node4 |
| 暂停 | op_4ff984852cfb3465b4f1acf4 | op_64d7f540d6dd85cc45dcf959 |
| 恢复 | op_a8d25b05a5b0b9a893379e64 | op_4bd7dd5fed550f9d25e04874 |
| 恢复VM/节点 | 857b403a-b43e-4c3e-b677-66e351c043cd / node2 | 610c6df6-4dd3-4dc2-916d-af6cc90c74c7 / node5 |
| 正常退役 | op_17c19d89f9d969de4bfd2682 | op_94f98346c98bf3a2e2081ec8 |
| 结果 | 全部succeeded；原/新VM及Runner Gone；原数据保持；Host零持有 | 相同 |

PG17本轮恢复在同一节点，PG18恢复到另一节点；跨节点调度也已在前轮多次实测，不能把同节点恢复误报为跨节点。最终原生SubjectAccessReview再次核对：Scheduler仅能PATCH本次五个可信Host，master拒绝；Agent对所有Node均无PATCH。所有选定release均deployed、6个Node Ready、全局VM为零、5个Host的Hold/managed placement均零。普通平台Pod与其真实预算登记继续保留。

公开最终证据汇总为BUSINESS_ACCEPTANCE_PASSED且committedBundleColdAcceptance=true；原子阶段NOT_COMPLETE等字段保持原样，由独立汇总逐项交叉核对原实例、数据及所有阶段，不修改原件制造成功。最终证据包SHA256：6e08249fd019e76e13973cc9e0d2a7694836b0be90bd39491d0d6e6f89dc02cf。清理卷数依次为8、7、7、7，所有原UID物理清理均留有回执。

## 六、未解决项与下一阶段验收条件

| 事项 | 当前事实和影响 | 后续完成条件 |
|---|---|---|
| 首次 Root HTTP 未确认的细分原因 | 已证实关闭触发；原异常的网络/时序细分证据不足。fail-close 保留，不以旧读数继续准入 | 增加无凭据的有界阶段/状态码诊断，复现并闭环根因；不能伪称已定位为 OOM |
| 第三轮原资格发布的细分原因 | 原Job只保留通用unconfirmed，原错误证据不足；已补安全诊断并修复确定的发布前零写入漂移接续缺陷，后续新实例通过 | 保留并分析固定诊断码；不得把推测写成已确认根因 |
| 自动可信恢复 | 原 root-only 管理协议已实测受权恢复；没有完整自动自愈状态机 | 设计去重、Owner fencing、原预算与身份复核、未知结果接续和告警，并验证故障矩阵 |
| 新 Node 持续接入 | 初装动态发现、既有池自动调度与跨节点恢复已通过；当前尚无持续 Host 注册、资格接入与候选发布闭环，新节点也尚未提供 | 节点加入后验证/完善 Host 登记、预算和资格、候选发布及真实调度；不得仅添加标签或手填 UID |
| 源码/镜像组合统一发行 | 按用户要求先完成当前镜像的 Helm 闭环。Neon 旧组合发行仍锁旧 Helm cbeedb79，不能当成本次独立标准包 | 后续统一精确源码锁、reusable workflow 引用、镜像构建/Harbor 摘要和组合发行验收；本轮不触发无关全量重编 |
| 规模、异构硬件及其他规格 | Host Chart 为1..16域、本轮5个worker；本轮 Guest/Kernel 和7/8Gi规格有实际资格证据 | 扩容或换硬件/镜像/规格前完成对应资格和预算边界测试；控制面更高 schema 上限不是实测规模 |
| 私有 fixture | 既有 journal 回归1181通过，4项私有 fixture 按原条件跳过 | 提供受控 fixture 后补齐；4项不得计入通过数或据此声明全量覆盖 |
| 生产与可选能力 | 当前为实验 HTTP MinIO、声明的平台前置与核心 SQL 系统；未证明生产 HA/完整 TLS/外部 S3 或 Auth/Data API/Functions | 分别补齐外部存储清理/备份恢复、凭据/TLS策略、故障与产品专项验收 |

Root 读取未确认时关闭准入的安全原则正确；本轮修复的是取得可信事实后正式排空、恢复和退出的活性。不存在强制开放准入、清 WAL、重置预算或强删 VM finalizer 的验收捷径。

## 七、归档范围

公开证据包含四轮 SQL/内存/生命周期回执、第二轮原 Guest 物理观测、两次空态清理回执、最终一次自动安装回执及文件摘要。源意图、完整 WAL、凭据和元数据库备份保留在管理节点的专用 0700 目录，公开归档只给出必要摘要与索引，GitHub 不提交这些私有原件。

本轮最终状态保留已部署且健康的 Neon 系统；验收 Compute 已正常退役，测试项目及其数据留作阶段追溯。新增 Node 和完整组合发行对齐按上表进入下一阶段。

权限边界补充：placement.allowedNodeNames 只是放置筛选，开放筛选不能代表全局 Node 写授权。Agent 的 Node GET 与 Scheduler 的 Node GET/PATCH 都由本次可信 dsga.hostIdentities 的完整键集合生成非空 resourceNames；空可信集合直接拒绝。新增 Node 必须先完成可信登记和相应发行更新，不能借空列表扩大全局权限。本次 1、5、16 Host 渲染回归及实际 Kubernetes SubjectAccessReview 均核验该边界；Agent 始终无 Node PATCH 权限。
