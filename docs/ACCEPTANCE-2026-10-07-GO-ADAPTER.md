# Go 运行链路与 Neon Helm 0.1.3 验收 — 2026-10-07

## 1. 交付结论与语言边界

新产品控制面是 **Go API/Worker + PostgreSQL + React/TypeScript UI**。
此前并非所有运行组件都已迁移：现场存在 Python adapter、旧 proxy-api 和
compute-resizer。本次将 Proxy/Storage adapter 改为 Go，并在完整配置归档后
停用两个未参与原生产品路径的旧服务。最终核查：没有运行中的 Python Pod，
adapter 返回 `runtime=go`，三节点和 API/Worker/Web Ready，测试 Compute/Runner 为 0。

私有 SSH、采证、历史验证工具仍可使用 Python；它们不属于业务后端、不进入
公共 control-plane 仓库或业务镜像。核心 Neon/PostgreSQL/Autoscaling 继续使用
其原生 Rust/C/Go 代码。neon-core 中两个默认禁用的旧实验室兼容工具保留供旧版
使用；原 Python adapter 源码从当前 Chart 删除，历史 v0.1.2 与私有归档可追溯。

**本次是可复测的预览发行，未获得完整生产准入，也未实现官网所有 Backend 服务。**
Go 迁移不能代替分布式栅栏、HA/DR、安全审计或完整功能验收。

## 2. 固定源码、镜像和部署

| 项目 | 本次记录 |
| --- | --- |
| 控制面源码 | `fba924ff096003d77610069ddd34d2d23a8962d0`；Signed-off-by 提交 |
| 正式控制面 CI | [37621190556](https://github.com/william-lbn/control-plane/actions/runs/37621190556)，4 项质量任务 + 6 项镜像发布全部成功 |
| 业务镜像 | api、web、gateway、dataapi、postgrest、adapter 同一源码；[六镜像锁](../locks/control-plane-fba924f.json) |
| Go adapter 镜像 | `docker.io/williamluckyli/control-adapter@sha256:9cf26a37bfe376423e98fdfa5229178866dff58a0dbb5ce425af8c1205eb5b28` |
| 匿名供应链检查 | Linux 检查 6 个 manifest/config/source/license；三节点串行拉取 18 次，均按 digest 验证 |
| Chart | 10 个独立 Chart，统一版本 0.1.3，8 个默认 release |
| 部署 | inspect → preflight → apply → verify → audit；完整现有 values 深合并，维护窗口排空 API/Worker |
| 持久身份 | 8 个 PVC 的 UID/volume 保持；外部 Secret UID/凭据保持；现场 27 个模板镜像引用匹配 |
| 元数据备份 | 35,073,852 bytes，流式保存，SHA256 `451456f81a6973569f718d7bd30a94844a5327c758642ae4b0ccfb7b1bacd723`；`restoreTested:false` |
| 上游 fork | Neon `1f30cd02092d`、Autoscaling `c0052f5f2d38`、PostgreSQL `a42351fcd41e` 与 46 镜像锁不变；本次未改上游源码 |

版本 Chart 的正式 GitHub CI、版本标签发布、匿名标准 Helm 消费和公共源码现场
审计回执在完成后追加至本报告；不能把本地打包通过当作已发布证明。

### Go 适配器实现

* 独立 Go 二进制与非 root scratch 镜像；保留 Service 名、selector 和入口合同。
* 分别挂载 Proxy/Controller Hook Secret 文件，按请求读取；就绪探针核查依赖，
  进程探针和固定标签指标独立。UID/GID/fsGroup 65532，文件权限十进制 288。
* 只允许所属 namespace 的 Service 地址；校验 VM 模板/实际 UID、项目/Endpoint
  归属，受限并发、按 Endpoint 串行、未知写入结果不盲重放、路由关闭后拒绝。
* attach 经原生 Controller 查询验证无分片 node 2；Service proxy RBAC 限一个服务。
  现场三个新租户收到 `go_json_v1` receipt，旧 Python receipt 保留。
* 通知采用 CAS 和精确 uint64；旧代次忽略、同代次不同内容失败，未实现的
  Pageserver/Safekeeper 重配置返回拒绝。不会伪装已经更新 Compute spec。

完整协议、安全边界、配置、时序图和 Go 故障矩阵见
[Go Adapter 合同](https://github.com/william-lbn/control-plane/blob/fba924ff096003d77610069ddd34d2d23a8962d0/docs/GO-PROXY-ADAPTER.md)。

## 3. Linux 质量与真实浏览器结果

| 门槛 | 结果与范围 |
| --- | --- |
| Go | 本地 Linux 与正式 Linux CI 都是 304 通过、0 失败、0 跳过；race、vet、gofmt、真实 PostgreSQL/PostgREST |
| Web | 正式 CI 的格式、回归、TypeScript 类型和 Vite 构建通过；UI 技术仍为 React/TypeScript |
| Helm | 10 Chart lint/render/schema/package，通过 9 个工具测试和 10 项危险配置拒绝检查 |
| 历史恢复 UI | 11 检查；timestamp/LSN 新分支、历史数据/表/角色/数据库隔离、保留边界、幂等及冷醒 |
| 原生产品 UI | 14 检查；项目/分支/Writer、真实 Proxy SQL、继承与隔离、手动缩零/冷醒、监控、操作记录 |
| Worker 故障 | 停 Worker 后 UI 接受一次请求并保留 Operation；恢复新 Pod，领导 epoch 41→42，同一 Operation 成功 |
| Data API UI | 21 检查；真实 Neon、RLS 两主体、无效 JWT、写入隔离、幂等、启停/轮换、手动与自动 1→0→1 |
| Console 邀请 UI | 6 检查；受邀注册/已有用户接受、跨组织拒绝、邀请撤销和现有会话权限撤销 |
| 应用凭据 UI | 8 检查；范围/分支/模型授权、一次展示、轮换、撤销、重载；不代表真实 AI 推理 |
| 汇总 | 五套 Chromium UI，共 60 检查通过；串行运行，每套前检查节点压力，每套后确认 VM 和 Runner 删除完成 |

真实 UI 测试操作产品页面与实际 PostgreSQL。403/401 与轮询暂时 503 的处理不同：
权限失败停止观察；暂时读故障恢复后不重复提交创建/启用请求。测试没有用 API
直接预建项目冒充 UI 创建。浏览器凭据、Cookie、JWT、数据库密码不进公开证据；
不启用 trace、video 或 HAR，保留受保护 fixture、结果和遮罩截图。

本版本的五套回归不包含全新多 Reader 压力/故障矩阵、分布式长短连接栅栏或
多实例 HA 演练；这些已有/后续功能必须依其独立门槛验收，不能由此表推导全功能通过。

### 本次可追溯测试号

| 套件 | Linux Job | 结果文件 SHA256 |
| --- | --- | --- |
| restore | `publication-ui-20261007124918` | `df7224956cc3d748d7d78687bf8c082c8845382174034a5c405a3d9866c379b2` |
| native | `publication-ui-20261007125138` | `650a6a17ab5be8b63213d1cdcdcc59cc8b184c1d8af012eeb9afe018b1e94476` |
| dataapi | `publication-ui-20261007125320` | `4254e1d5208e19334fdc03e03050dcd20d4e74fa7f4820f65e9bd93ff027d270` |
| invitations | `publication-ui-20261007125657` | `cd079ae8f53da6133d0186e59e02da9bed27626c460effe1a36cc74a86062536` |
| credentials | `publication-ui-20261007125715` | `37d3dfdf38ecda46d3da3477bc22d60d1f910edbf7983c51c8ad103daae1ddcb` |

维护者完整记录位于受保护工作区 `control-plane/production/evidence/20261007-product/`：
`adapter-ui-restore-attempt1`、`adapter-ui-regression-batch-attempt1`、
`adapter-unified-deploy-attempt2`、`adapter-registry-attempt1` 等。
Linux 原始 UI/fixture 保留在 `/var/lib/neon-control/linux-delivery/runs/<Job>/`，
完整升级快照位于 `/var/lib/neon-control/product/20261007/unified-124647/`。
这些私有记录不在公共 Git；克隆者应按 TESTING.md 用新 attempt 产生自己的证据。

## 4. 实际修复、失败保留与资源释放

1. Helm 首次质量检查发现 `0440` 的 YAML 1.1/1.2 数字解释差异。改为明确的
   十进制 288，实际组可读权限一致；失败 attempt1 保留，修复后 attempt2/3 通过。
2. 部署 attempt1 在 pg_dump 阶段以 `ENOBUFS` 停止，未切换业务镜像。
   只读诊断发现备份 34,984,034 bytes，超出 Node 32 MiB stdout 缓冲；不是本次
   节点内存耗尽。修复为独占私有文件流式写入、fsync、非空校验、分块 SHA、
   成功后 rename；失败部分文件保留，不能当完整备份。三个 Linux 回归测试通过，
   新部署 attempt2 成功。此修复属于 Helm 工具，未修改 Neon/Autoscaling fork。
3. 升级前归档旧 adapter/proxy-api/resizer 的完整 manifests、Pod UID 和日志，
   确认 Proxy 指向动态 adapter 且旧 compute=0 后，再修改完整保留的 core values。
4. 仅退休 9 个属于本轮、已终态的测试 Job；归档 manifest/Pod/log/receipt 后以
   UID 和 resourceVersion 删除，等待其 Pod 消失。此前已删除的 20 项仅跳过。
5. 用户/测试目录、数据库数据、PVC、WAL、对象、外部 Secrets、所有失败与通过
   记录保留；当前测试 compute=0，基础组件保留资源。共用物理 NVMe 的故障域
   限制仍存在，不能因本次压力通过宣称长期 I/O 稳定性已认证。

## 5. 手动复测与后续准入

从 [UPGRADE.md](UPGRADE.md) 第 6/7 节执行完整配置归档和 Go 切换；全新环境按
[DEPLOYMENT.md](DEPLOYMENT.md) 初始化外部状态并使用锁定镜像。Linux 复测命令、
凭据文件权限、五套测试顺序、停止资源与保留记录的步骤见 [TESTING.md](TESTING.md)。
仅通过一次冷醒或 Pod Ready 不代表完整验收。保留原 Operation ID，未知写入
结果先观察；失败后修复根因，使用新 attempt，不覆盖旧记录或重置业务状态。

还需实现/独立验收：完整项目/分支删除和 GC、小数 CPU、完整内存缩回、
跨实例连接账本/栅栏、HA/DR、全链路可信 TLS、长期监控/告警、Managed Auth、
Functions、产品 Object Storage、AI Gateway 真实推理，以及原地恢复和 Backend
一致性恢复。外部账号/SMTP/模型凭据后置，本地能力按控制仓库实施计划逐项推进。
当前只开放已经通过相应能力门槛的功能，未将规划或拒绝响应标为可用服务。
