# Neon 通用内网部署

本仓库提供 Neon 的分层 Helm Chart、站点生成器、一次安装入口、只读诊断、业务验收与正式卸载工具。面向 Kubernetes 内网环境，不要求公网 IP、公网域名或公网入口。

默认服务采用 ClusterIP，不预占固定节点端口。当前发行资格要求 Kubernetes 1.36、Linux/amd64 和 KVM；其他小版本与硬件需独立资格。

当前唯一推荐的完整产品入口是[标准部署手册](docs/standard/README.zh-CN.md)。按发布包的源码锁、文件摘要和不可变镜像摘要部署；Chart 版本号、分支名称或 CI 成功不能单独代表端到端验收。

## 分层架构

| 层级 | 微服务与职责 | 生命周期归属 |
| --- | --- | --- |
| 平台前置 | Kubernetes、主 CNI、所需网络附件 CRD、KVM、存储类、证书控制器、内网镜像仓库 | 平台运维提供，产品卸载保留 |
| 虚拟化与调度 | NeonVM Controller、设备插件、Scheduler、节点 Agent | Helm 管理工作负载，原生协议管理 Host 预算 |
| 存储 | 元数据库、Storage Controller、Broker、Safekeeper、受管 Pageserver、对象存储 | Helm 管理服务和持久卷声明，数据擦除单独核验 |
| 控制面与访问 | API、Worker、Web、Compute 管理网关、Proxy/Storage 适配器、SQL Proxy | Helm 管理常驻微服务，Worker 执行业务 Operation |
| 业务运行时 | PG17/PG18 Compute、Runner、资格任务、租户与时间线 | 控制面及原生 Controller 创建，不能用静态 Helm VM 冒充 |

完整依赖关系见[产品架构](docs/standard/架构与边界.zh-CN.md)。标准方案有 9 个常驻 release；仓库还保留可选产品和资格工具 Chart，数量不同不是重复部署。

## 一次部署

取得已核对的标准发行包，填写显式站点输入，执行：

```bash
cd neon-standard
sha256sum -c SHA256SUMS
export PATH="$PWD/bin:$PATH"
bash tools/standard-up.sh /secure/site-input.json /secure/new-site-operation
```

站点输入示例位于 `profiles/standard-site/site-input.example.json`，其中占位值必须替换。模板不含现场地址；生成器不搬运镜像。必须先在目标仓库准备相同摘要的镜像，并在 Kubernetes 节点配置其拉取信任和权限。一次入口在新操作目录分别保存 config 和 install，拒绝覆盖既有操作。需要分步核对时，可分别执行 standard-init.py 和 standard-site.py。

仓库协议、CA、认证、存储类、存储根目录、区域、集群 DNS 后缀、产品/平台命名空间、节点标签筛选和系统预留均由站点输入声明。系统组件保留产品协议的 `kube-system` / `neonvm-system` 命名空间，独立平台空间采用 `neon-control-*`；这些是当前协议约束，不是某个实验环境的节点、IP 或 UID。

## 验证与运维

[部署和业务验收](docs/standard/README.zh-CN.md)覆盖公开控制面创建、真实 SQL、原 Compute 物理内存自动往返、WAL 结清、暂停恢复与退役。[故障与接续](docs/standard/故障与接续.zh-CN.md)说明只读诊断、未知结果及正式卸载。[发行与中文文档管理](docs/standard/发行与文档.zh-CN.md)说明来源和历史资料边界。

2026-11-24 已完成的四轮现场验收见[原始阶段报告](docs/standard/acceptance-20261124.zh-CN.md)，它只证明当次源码、镜像和环境，不能冒称后续改动已实测。本轮新增 Node 接入暂缓；生产 HA、完整 TLS、灾备、其他硬件与规格、可选产品全量验收未包含在现有结论中。

## 开发检查

```bash
npm ci --ignore-scripts --no-audit --fund=false
npm run check
npm run test:standard
npm test
npm run helm
npm run helm:stack
npm run helm:dsga
```

`stack/stack.json` 是保留的静态组合工具合同；当前完整产品部署采用上面的标准入口，不混用两套安装流程。控制面 Chart 来自 `william-lbn/control-plane` 对应维护提交。源码和 CI 检查不能替代实际 Kubernetes 与业务验收。

平台责任、静态 Pod 真实硬限和未开放控制面的失败安装退出，见 [平台前置与部分安装退出](docs/standard/平台前置与部分安装退出.md)。
