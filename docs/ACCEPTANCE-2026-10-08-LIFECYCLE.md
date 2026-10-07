# 保留删除、恢复、双 Reader 与统一 Helm 0.1.4 交付 — 2026-10-08

## 1. 结论与范围

Go API/独立 Worker、PostgreSQL 和 React/TypeScript Console 的项目/叶分支保护、
保留删除、七天项目恢复、两个真实 Reader 独立扩缩、Data API 删除协调及凭据
永久撤销已完成代码、正式镜像和真实 Linux UI 验收。六套 UI 共 **83 checks**
通过；每套结束均观察 VM/Runner 0。测试 UTC 日期为 2026-10-07，交付日为北京时间
2026-10-08。这不是官网全功能完成或生产准入认证；第 6 节逐项列明剩余工作。

所有产品镜像使用公开 Docker Hub digest，六个控制镜像来自同一源码。
没有修改本轮 Neon/autoscaling/postgres fork 源码或数据面版本。产品控制后端为 Go，
Console 和公开浏览器测试为 TypeScript；私有 Python SSH/证据工具不发布。

## 2. 源码、镜像和部署锁

| 项目 | 版本与证据 |
| --- | --- |
| 控制软件源码 | `6e778bbc631f6fa30a7543dc274789beb70afb0f`；Signed-off-by；[源码提交](https://github.com/william-lbn/control-plane/commit/6e778bbc631f6fa30a7543dc274789beb70afb0f) |
| GitHub CI | [37647844344](https://github.com/william-lbn/control-plane/actions/runs/37647844344)；四项质量门槛与六镜像发布全部成功 |
| Go | 327 pass / 0 fail / 0 skip；格式、vet、race、真实 PG/RLS、OpenAPI 合同 |
| Web | 13 tests、严格 TS、格式、Vite 与 Canonical Chart 门槛通过 |
| API/迁移 | OpenAPI 0.8.0，50 paths / 69 operations；schema 15；014 不变，015 前向修复准入 |
| 公开镜像 | [六镜像锁](../locks/control-plane-6e778bb.json)；Linux 匿名 OCI/config/source label 验证；三节点 18 次预拉取 |
| Neon fork | `1f30cd02092dc151f5d00aef97e7c629105b454b` |
| autoscaling fork | `c0052f5f2d38fce6c70e448f3f1ee2ee239a0a93` |
| Postgres 16 fork | `a42351fcd41ea01edede1daed65f651e838988fc` |
| 数据面镜像 | `2026.09.30-162021-1f30cd02092d-r36742713551-a1`，不可变 digest，详见 SOURCE-PROVENANCE.md |
| Helm | 10 个 Chart 均 0.1.4，8 个默认 release，控制组件 runtime 0.8.1 |
| Chart 质量 | 10 Node tests / 0 skips，10 渲染/schema 负例，10 包；Linux Job helm-quality-1791389159 |
| 现场审计 | 8 releases / 27 image refs / 8 PVC；完整旧 values、PVC/Secret 身份及清单一致，初始 Compute 0 |

Canonical 控制组件 Chart 在控制仓库为 0.6.1；统一分发 Chart 在本仓库为 0.1.4。
两者包版本分别管理，共享同一软件与合同；具体上线代码以锁和不可变发布标签为准。

## 3. 正式镜像从 UI 开始的 Linux 回归

| Suite | 结果 | Linux Job | 保留项目 |
| --- | --- | --- | --- |
| 历史恢复 | PASS / 11 checks | publication-ui-20261007160824 | prj_2f65e6ec8580c161 |
| 原生产品/监控/Worker 故障 | PASS / 14 checks | publication-ui-20261007161014 | prj_064d48a1be97aa05 |
| Data API/RLS/idle/冷醒 | PASS / 21 checks | publication-ui-20261007161141 | prj_d7e9f06395cb2db1 |
| Console 邀请注册 | PASS / 6 checks | publication-ui-20261007161533 | — |
| 应用凭据/分支权限 | PASS / 8 checks | publication-ui-20261007161551 | prj_064d48a1be97aa05 |
| 保护/保留删除/双 Reader/恢复重试 | PASS / 23 checks | publication-ui-20261007161609 | prj_1c1ad0f5f7fb5063 |

正式镜像回归没有 Windows 编译或浏览器 CI。每次使用独立 fixture/evidence，
浏览器没有 Kubernetes ServiceAccount；只串行运行一套，进入下一套前检查 I/O
PSI 和可用内存。SQL 请求通过 Neon Proxy，未直接访问 Compute；真实存储、WAL、
PostgREST 和 RLS 参与测试。截图遮罩密码，不保留 trace/video/HAR 或 Token 明文。

原生 UI 包含 Worker 停止期间队列保持、恢复后同一 Operation 完成和 leader epoch
增长。历史恢复与 Data API 注入两次 GET 503 观察失败，确认没有重复写请求。
恢复故障场景由独立公开 Node operator 对本测试已 queued 的恢复注入 terminal status：
原 Operation `op_00a785ffa18dc2746b6f603b` 在 UI 弹窗重试后成功，Worker epoch
55→56。这是受控状态注入，不认证真实存储
outage、跨实例外部栅栏或 HA。手工/自动复测合同见本仓库 TESTING.md 与
[控制面测试手册](https://github.com/william-lbn/control-plane/blob/6e778bbc631f6fa30a7543dc274789beb70afb0f/docs/TESTING.md)。

## 4. 生命周期和恢复的已验证语义

* 名称确认、If-Match、幂等 Key、Admin/Editor 权限、根分支/子依赖/保护拒绝。
* 活跃叶和项目删除关闭访问、协调服务、回收原 UID Compute；保留 tombstone 和审计。
* 两个 Reader 有独立 Endpoint/Selector；真实只读、拒绝写、独立 1→0→1，读取主节点 WAL。
* 七天项目恢复保留原 Writer/Reader IDs、Selector、密码和数据；先保持休眠，再分别冷醒。
* 已单独删除的分支不复活；Data API 恢复后 disabled；旧 Backend Token 仍撤销并返回 401。
* 显式重新启用 Data API 使用保留配置并读取真实 RLS 数据，最终正常停用和 Compute 0。
* 原失败创建/恢复允许重试原 Operation；数据库 parent 锁拒绝 tombstone 上的不相关新工作。

完整合同与人工步骤见
[RETAINED-DELETION.md](https://github.com/william-lbn/control-plane/blob/6e778bbc631f6fa30a7543dc274789beb70afb0f/docs/RETAINED-DELETION.md)。
物理 Timeline/WAL/object GC 为 held；保留删除不等于安全物理 purge。

## 5. 失败、备份和资源纪律

此前未 bounded 的导出遗留闲置 pg_dump，阻挡 migration 014。核验锁和新完整备份后，
按 PID+backend_start 精确终止该只读导出；失败、锁证据与原测试记录均保留。
本版 maintenance 工具对远端导出设置 150 秒、10 秒 kill grace、60 秒闲置事务期限
和唯一 PGAPPNAME；失败保留 exclusive mode-0600 partial，并阻止 rollout。
正式升级备份 40,481,776 bytes，SHA256 `41216e5867356c281a5d60432b759b8a9e1fa92afcb82d6cecc45e904eb5d3c1`；
`restoreTested:false`，不是完整 DR 演练。10 Node tests 包含超时 partial 与 32 MiB 以上流式导出。

候选 UI 观察曾因三 API Server 的 I/O 延迟中断。使用原 Job/Pod UID 只读继续观察，
没有重发创建/删除；原失败 report 保留。一次受控 operator 标签校验错误在 scale/SQL
前退出，原 Worker 仍 Ready；修正 selector/UID 校验后新 attempt 通过。详见控制仓库
候选验收记录。测试之外出现过 I/O PSI 超过阈值，保留失败采样并等待新采样通过；
三 VM 共用宿主磁盘，不能把内存充足当作存储延迟已解决或独立故障域。

已归档退休 17 个本轮已完成 Job；后续最终退休回执另记。所有历史 SQL/对象/WAL、
PVC、Secrets、Operation、fixture、成功/失败文件保留。只能按归属与 UID/版本退休
已完成运行资源；不删除历史报告。复测使用新 attempt 或明确原故障恢复，不盲目重放。

## 6. 未完成与独立准入门槛

| 项目 | 实际缺口与原因 |
| --- | --- |
| Managed Auth / Functions / 产品 Object Storage | 尚无完整服务 Driver/runtime/API/UI；不是只剩 E2E。需实现分支语义、权限、资源隔离和真实服务；MinIO 数据面桶不是产品存储 |
| AI Gateway 推理 | 仅应用凭据/授权检查；上游配置 UI、模型路由/推理/流式/预算仍需代码。真实模型凭据未提供，供应商验收后置；不能把本助手作为推理服务 |
| 完整 PITR | 已通过历史恢复到新分支；原地 reset、cutover/rollback、Backend 一致性、长保留/GC竞争需开发/独立验收 |
| 完整删除 | 保护、保留删除/恢复已通过；物理 GC、TTL、失败创建清理、独立 Endpoint 删除尚缺 |
| 精细资源 | 小数 CPU、完整内存归还和 Guest/Runner/QEMU 全链路配额未完成现场验收，部分需原生资源模型/代码演进 |
| 多 Reader 完整矩阵 | 本版手动独立缩零/冷醒/WAL/只读已通过；多 Reader 自动 idle、长事务、密码轮换和资源热伸缩另设门槛 |
| 多租户完整准入 | 当前授权与邀请注册有代码/集成/UI切片；完整对抗、身份验证、企业身份/邮件和并发矩阵仍须验收；Console 账号不是 Managed Auth |
| 跨实例缩零栅栏 | 数据库锁/lease/epoch及旧操作拒绝有实现；外部 Proxy 连接账本、多个 Adapter/Worker竞争与 SQL admission fence 未认证 |
| HA/DR | singleton metadata/MinIO/Pageserver、local-path、同宿主磁盘；需完整恢复、RPO/RTO、冗余和独立故障域，备份捕获不代替恢复 |
| 可信 TLS | 实验室 IP/内部凭据保留已有例外；全链路可信 CA/IP/DNS、verify-full、轮换和失败负例未完成 |

详细接口/模型/开发退出条件由控制仓库 FULL-PRODUCT-IMPLEMENTATION.md、
PRODUCT-COMPLETION-PLAN.md、OpenAPI 和本仓库 PRODUCTION-GATES.md 共同约束。
没有把上述服务开关或生产状态虚标为可用。

## 7. 使用与复测入口

控制台：[Linux Console](http://192.168.146.100:30788/)，Swagger `/api/docs`。
按 DEPLOYMENT.md/UPGRADE.md 完整 stack 顺序安装；不要仅安装其中一个 Chart。
版本发布后按标准 Helm 仓库消费十个包：

```bash
helm repo add neon https://github.com/william-lbn/neon-helm/releases/download/v0.1.4
helm repo update
helm pull neon/neon-control-plane --version 0.1.4
```

保存发布 commit/digest、每次 Operation、原 PVC/Secret UID 和新 attempt；失败先查看
原操作与日志。最终匿名源代码/manifest审计、发布 package/hash 消费和资源退休结果
在对应交付回执中独立记录。公开文档不包含凭据或私有原始 cluster export。

## 8. 正式发布、匿名消费和最终现场回执

上述软件/Chart 行为固定在控制软件 `6e778bbc631f6fa30a7543dc274789beb70afb0f`
及 Chart 源码 `944697235487da261c2a2521a62685a78aafc59a`。
后续 main 的本报告/README 同步只有文档变化；不改变运行软件或不可变发布标签。

| Gate | 最终结果 |
| --- | --- |
| 不可变标签 | v0.1.4，annotated object `eb2cf84e03cca9985dd533ad2d8c12fd063bdd22`，指向上述 Chart commit；无 force/retag |
| 主分支 CI | [37651563861](https://github.com/william-lbn/neon-helm/actions/runs/37651563861)，全部通过 |
| 发布 CI | [37651684136](https://github.com/william-lbn/neon-helm/actions/runs/37651684136)，质量与正式发布均通过 |
| 正式产物 | [v0.1.4](https://github.com/william-lbn/neon-helm/releases/tag/v0.1.4)，10 Chart 包、index.yaml、SHA256SUMS、源码/镜像 locks |
| 匿名消费者 | Linux 使用隔离 Helm repo 配置下载 10 包；index 与全部包 SHA256 通过；不需要 GitHub/Docker 凭据 |
| 公开源码现场审计 | Linux 匿名 clone 上述 Chart commit，重新渲染比对全部 8 releases / 27 image refs，PVC/Secret 身份保留，VM/Runner 0 |
| 运行语言 | API/Worker/Web Ready；Go adapter /readyz 与 native hook Go receipt 通过；无运行中的 Python Pod |
| 最终资源退休 | 两轮分别 17 和 7，合计 24 个已完成 Job；先归档再按 UID/resourceVersion 删除，数据和证据保留 |
| 节点状态 | 三节点 Ready，无 MemoryPressure/DiskPressure；最终 .100 I/O PSI avg10/60/300 为 0；Compute 0 |

本发布的源代码、镜像、部署、UI、失败修复、包发布和匿名消费证据分别验证，
没有用一次 Pod Ready 替代产品验收。共同磁盘长期延迟和第 6 节生产门槛仍未放行。
