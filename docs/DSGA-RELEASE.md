# DSGA 四仓候选版本与 Helm 制品

本入口供 `william-lbn/neon` 的统一分发流水线调用。Neon 构建并验证固定源码下的镜像，Helm 消费同一次运行的 `distribution-manifest.json`，通过全部离线门槛后打包；最后由 Neon 发布同一个候选 Release。Helm 的打包工作只需要 `contents: read` 和 `actions: read`，不需要能够写入其它仓库的 PAT。

## 1. 版本与发布入口

| 项目 | 合约 |
| --- | --- |
| 复用工作流 | `.github/workflows/dsga-package.yml` |
| `helm_sha` | 本仓库完整 40 位提交 SHA，与 manifest 的 `source_lock.helm_commit` 一致 |
| `release_version` | `0.2.0-dsga.<GitHub run_id>.<run_attempt>.amd64`，无 `v` 前缀 |
| `distribution_artifact` | 当前调用运行内的精确 artifact 名；其根目录包含 `distribution-manifest.json` |
| 输出 artifact | `dsga-helm-<release_version>` |
| 发布位置 | `william-lbn/neon` 的同名候选 Release，由调用方发布 |
| 本仓普通 Chart 版本 | `0.1.32`；生成候选包时只在临时 staging 内替换为统一候选版本 |

复用 workflow 的 `uses:` 必须锁完整提交 SHA。`helm_sha` 是包内源码身份，不能用分支名代替。输入中的版本还必须属于当前 GitHub `run_id/run_attempt`。重新发布应使用 **Re-run all jobs** 或发起新的运行：只重跑失败 job 时，GitHub 可能沿用旧 prepare 输出，工作流会拒绝跨 attempt 的版本组合。

当前 DSGA Chart 中的 `targetArchitecture`、节点 placement 和已纳入验证的运行环境是 amd64。统一候选分发明确拒绝 arm64，不把已有独立 arm64 镜像构建等同于这些 Chart 的部署资格。

## 2. 分发清单的校验

`schema_version=2`、`channel=dsga`，`version` 与 `chart_version` 必须相等。清单需要以下身份：

- Neon 的 `neon_commit` 与 `verification_commit`。
- `source_lock.autoscaling_repository/commit`。
- `source_lock.postgres_repository/postgres`，其中 PG14–18 各有完整 SHA。
- `source_lock.helm_repository/commit`。
- 每个 runtime 镜像的名称、标签、摘要、来源仓库和源码 SHA。

验证器要求目前合约中的 **49 个镜像全部到齐**：Neon 聚合及构建工具 2 个、core binaries 18 个、compute sidecar 4 个、Autoscaling/NeonVM/Qualifier 11 个、PG14–17 各 3 个、PG18 2 个。任何缺失、额外冒充的组件、错仓库、错 SHA、版本混用或没有 `sha256` 摘要的记录都会拒绝。

PG14–17 的 `postgres_profiles` 为 `full`；PG18 为 `dsga-core`，仅包含 `compute-node-v18` 与 `vm-compute-node-v18`，不声明 `neon-test-extensions-v18`。若镜像记录提供 architecture 或 execution 信息，它们也必须与清单的架构、当前版本中的 run/attempt 一致。

JSON 重复键被拒绝，防止审阅者看到的值与实际解析值不同。打包前还检查 checkout 的 HEAD、干净工作树和输出目录不存在；不会把旧包混入一次新发行。

## 3. 产物和同源范围

输出目录是平面目录，便于调用方直接附加到 Release：

- 全部 15 个 Chart 的 `.tgz`，版本统一。
- 原样保留的 `distribution-manifest.json`。
- `dsga-release-lock.json`，包含四仓 SHA、镜像摘要映射和能力限制；每个 Chart 的 `files/` 中也嵌入同一份锁。
- `pg17-<chart>.values.json` 和 `pg18-<chart>.values.json`，各六份，只来自当前 manifest。
- `helm-package-receipt.json`、指向 Neon Release 的 `index.yaml`、中文说明和 `HELM-SHA256SUMS`。

本次 manifest 直接覆盖的运行 Chart 是 `neon-core`、`neon-managed-pageserver`、`neon-compute`、`neonvm`、`neon-autoscaler`、`dsga-platform-qualifier`。这些 Chart 的镜像默认值和覆盖文件都使用 `repository@sha256:...`，不依赖可移动的 `latest` 标签。

其它 Chart 随 Helm 仓库一起打包，但其控制面等业务镜像没有被这四仓流水线重建：保留原 `appVersion`，并标记 `neon.tech/image-binding=separate-product-not-rebuilt`。新的运行覆盖文件不读取九月底的 `profiles/lab` 镜像锁。既有 lab profile 仅用于离线渲染 fixture，生成器再明确覆盖本次对应的镜像字段。

## 4. 候选版本不授予运行资格

此发行必须显式声明：

```json
{
  "release_tier": "candidate",
  "vm_system_mode": "legacy",
  "qualification": {
    "production_ready": false,
    "physical_memory_release_qualified": false
  }
}
```

上面是能力边界示例，不是可用于打包的完整 manifest。打包工具只接受完整真实记录。

新包保留实验确认、DSGA 自动操作、Compute 与 Qualifier 的安全关闭默认值，不填充假的租户、VM UID、Lease、CA、预算或资格报告。真实部署仍需提供已验证的原始输入和 Kubernetes 1.31.x / 原节点池约束。

PG18 的两个入口需要分别看待：

- **普通 SQL Compute（`neon-core`）**：`pg18-neon-core.values.json` 显式使用 `mode=public`、`buildProfile=dsga-core`。渲染的配置只预加载已交付的 `neon,pg_stat_statements`，删除 `cron.*` / `timescaledb.*` 设置，初始化脚本不再添加 `ulid`。PG18 配 `full`、`dsga-core` 配 PG17 或 wrapper 都会被拒绝。测试实际启用 Compute 渲染，并在本地执行渲染出的初始化脚本检查最终 JSON；这里没有声称已经实跑该容器或完整存储链路。
- **受管 VM（`neon-compute`）**：当前 PG18 Chart 要求 `trusted-runtime-v1`，而本次 VM 制品是 `legacy`。因此对应覆盖文件保持关闭，直接激活 legacy PG18 会被 schema 拒绝，不能冒充已完成的 normal-split 闭包。

普通 SQL 配置可用不授予 VM 物理内存归还资格。PG17/18 的历史真实环境证据也不会被这个打包步骤重新认证或提升为生产资格。

## 5. 离线质量门槛

普通 CI 现监听 `main`、`codex/dsga-neon-helm-v3-20261019`、PR、标签和手动运行。复用打包入口同样运行以下门槛：

```bash
npm ci --ignore-scripts --no-audit --fund=false
npm run check
npm test
npm run helm
npm run helm:dsga
```

工具版本来自现有 `locks/tools.json`。Python 离线校验器使用 Ubuntu 24.04 的 Python 3.12；PyYAML 6.0.3 的 wheel 以 SHA256 固定。`npm run check` 保留私钥/凭据/不适宜产物扫描，仅将已存在的受审 Python 验证脚本逐项列入源码清单，并覆盖全部 15 个 Chart 的版本与必要文件。

`npm run helm` 为新增的资格/权限 Chart 使用 `tests/fixtures/helm` 中明确的离线输入，避免把它们误当成可以直接部署的 lab profile。所有 Chart 继续做 lint、正向渲染、未知配置字段拒绝；既有 34 个安全负例保留。

`npm run helm:dsga` 串接六组已有聚焦校验：Qualifier、Runner RBAC、Pod 保护、完整控制 socket、Pod CPU/内存硬限、PG17/18 版本选择。脚本不访问 Kubernetes API、不签发资格。完整控制 socket 原脚本的历史基线仍是 `0820655a...`；本次 CI 显式传入审计起点 `85ebf7f23521667fad84791b78b5fa36fac24ada`，因为后续功能已经增加了 Agent 的只读 Lease 规则。全部 socket/RBAC 增量断言保留，不把当前 CI 校验说成重验整个历史控制面。PG major 选择使用实际 PG18 改动前的 `62544f48df70a6ae263af5862570d656004d16fb` 模板作基线。

## 6. 本地检查真实候选清单

在这个工作流已提交的、干净的 checkout 中准备真实的已验证 `distribution-manifest.json`。不要用测试目录中的虚构摘要替代真实镜像记录。

```bash
task_helm_sha="$(git rev-parse HEAD)"
task_release_version="$(node -p "require('./artifacts/input/distribution-manifest.json').version")"
node tools/package-dsga-release.mjs \
  --manifest artifacts/input/distribution-manifest.json \
  --version "$task_release_version" \
  --helm-sha "$task_helm_sha" \
  --output artifacts/dsga-release
cd artifacts/dsga-release
sha256sum --check HELM-SHA256SUMS
```

这只生成和验证本地包，不执行部署。远端发布由 Neon 最终 job 在镜像门槛和 Helm 制品全部成功后统一执行。
