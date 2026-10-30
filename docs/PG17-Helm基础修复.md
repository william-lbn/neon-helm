# PG17 Helm 基础修复与下一阶段门槛

本批仅在 Linux 仓库 /data/neon-build/src/neon-helm 的
codex/dsga-neon-helm-v3-20261019 工作分支执行。从 GitHub main
648488adb88125b57a85044a9050762a819994e8 建立分支。没有部署、修改集群、
提交或推送。它是 PG17 内存自动扩缩容的 Helm 基础准备，不构成运行闭环通过。

## 节点边界

用户最终明确允许 worker-117、worker-118、worker-119
（172.24.79.117、118、119），排除 ubuntu/172.24.79.116。
118 同时构建和部署；119 的 control-plane/master/etcd 角色不改变用户允许范围。
不按节点角色猜测是否可以部署。

七个相关 Chart 的 placement.allowedNodeNames 必须恰好为上述集合，允许顺序不同。
values 默认明确列出三节点；schema 和模板双重拒绝空、重复、缺项、116 和未知节点。
profiles/pg17-memory/placement.json 是可共用的唯一节点范围输入，不包含运行镜像、
凭据、UID、资格、内存预算或 DSGA 初始化数据。

每个相关 PodSpec、Job hook 和静态 VM 都同时带有：

- kubernetes.io/os=linux、kubernetes.io/arch=amd64 的 nodeSelector。
- neon.tech/pg17-memory-pool=worker-117-worker-118-worker-119 的 nodeSelector。
- 每个 required nodeAffinity OR 分支中的 hostname In 三节点限制。
- 原有 Linux/架构约束，以及 safekeeper/controller 反亲和。

实际覆盖 neonvm、neon-autoscaler、neon-core、neon-compute、
neon-adapter、neon-managed-pageserver、compute-management-gateway。
neon-core 的可选旧 compute/resizer/proxy/controller 与 product-storage hook
也有隔离，但只在离线 fixture 中开启以检查遗漏，本轮运行不因此启用它们。

AS 02a1b0c 的 affinityForVirtualMachine 会追加独立 Linux/arch OR 分支；
本批不改并行开发中的 AS。VM 的独立 nodeSelector 会原样进入 Runner Pod，
因此实际池标签的排他性是部署前强制门槛。Helm 不拥有或自动修改 Node 标签。

在主任务达到单机门槛、准备部署时，由主代理采集完整集群 NodeList JSON。
标签准备后必须执行：

    python3 tools/check-pg17-helm.py --check-nodes /data/实际路径/nodes-after-pool-label.json

该检查只读取文件，不访问 API，不修改标签。它要求池标签在整个 NodeList 中
恰好匹配三节点、hostname 与节点名一致、Linux/amd64、Ready、未 cordon、
无压力和未配置的硬 taint；其他节点即使带控制面角色也不能匹配该池。
如果 119 有硬 taint，应在下一批据实际值增加精确 toleration 并验证，
本批不会清除 taint 或用通配容忍绕过限制。

fixture NodeList 的测试通过只证明检查器行为；真实节点标签和调度仍未验收。
动态 control-plane renderer 也必须冻结相同 placement 并传入 VM nodeSelector，
不能将 Helm 管理组件已隔离冒称所有动态 Runner 已隔离。

## PG17、镜像与 CRD

静态 neon-compute 新增 compute.pgVersion，默认整数 17，schema 只允许 17。
模板 PG_VERSION 取该参数。历史 profiles/lab/neon-compute.json 的 v16 pin
保留为历史来源，但已显式停用该静态 VM，避免 PG17 参数启动旧 v16 镜像。
这没有把旧 --dev/legacy 模板变成完整 DSGA 模板。

device-plugin 镜像从模板硬编码移到 neonvm 的 images.devicePlugin，
默认保留原 digest，可覆盖为已核验的其他 digest；tag 和空值会被拒绝。
本批没有捏造任何可运行 PG17 镜像锁。离线测试中的 example.invalid
镜像、tenant/timeline ID 和 Secret 引用都只在 artifacts 的 fixture 中，
不能用于部署，也不证明镜像可下载或运行。

三个 CRD 从 Linux Git 对象准确读取：
william-lbn/autoscaling@02a1b0c90e58e3dfed2bb9f2c7c44e98a207ca28。
记录在 locks/pg17-helm-crd-source.json，包括原 blob SHA256 和规范 spec SHA256。
包括完整 dsgaBootstrap、held/release 和 CEL 约束，不是手工拼接几个字段。
只保留原 Helm Chart 的 cert-manager CA 注入 annotation 与 conversion webhook；
其余 spec 与准确源码逐项相等。

Helm upgrade 不会自动升级 crds/。本批没有自动升级、接管、删除 CRD。
后续须先检查真实集群 CRD UID、storedVersions、现有对象及 webhook 就绪，
再做 server-side dry-run/CEL 编译和原对象兼容验证，明确采用变更。
离线 lint/template 不替代 API Server 验证。

后续真实镜像必须锁定 Neon、PG17、AS、必要 gateway 的准确 Git SHA/子模块和
OCI digest。旧 lab source/image lock 不代表本轮代码。离线搬运需要在目标节点
正确 containerd socket 的 k8s.io namespace 中验证与 Chart 一致的 repoDigest，
不能只检查 docker tag 或 tar 传输成功。

## 离线门槛

Linux 现有 Python3、PyYAML 6.0.1、Helm 3.12.1 可直接运行，无须 Node/npm：

    python3 tools/check-pg17-helm.py --kube-version 1.31.2

package.json 增加 helm:pg17 入口，只调用上述工具。原源码检查器仅为该准确路径增加 Python 允许项，未放宽其他文件。测试使用独立空 kubeconfig，
只执行 helm lint/template，不调用 kubectl、不部署。输出到独立时间戳
artifacts/pg17-helm/ 目录，保留每次真实结果、stdout/stderr、严格 YAML
解析结果、离线 fixture 和工作区 source-inputs.json/SHA256。
失败结果保留，不覆盖为通过；不记录凭据。

| 编号 | 本批检查 |
| --- | --- |
| PG17-U-H01 | 七 Chart 非法 allowlist、缺失配置、未知字段的 schema 拒绝 |
| PG17-U-H02 | 移除临时 Chart 副本 schema 后，模板仍拒绝 116/越界节点 |
| PG17-U-H03 | 静态 VM 只允许整数 PG17 |
| PG17-U-H04 | device-plugin digest 覆盖接线及 tag 拒绝 |
| PG17-U-H05 | NodeList 检查器负路径、119 角色允许、Controller 宽 OR 仍被独立池 selector 限制；仅 fixture |
| PG17-U-H06 | 三 CRD 的准确 Git 来源、spec、CEL、原 webhook/CA 注入比对 |
| PG17-S-H01 | 七个相关 Chart 的严格离线 lint |
| PG17-S-H02 | 基本 PodSpec/VM/MinIO hook 的 selector、每个 affinity 分支和反亲和 |
| PG17-S-H03 | 仅离线开启旧可选分支和 product hook 以穷尽节点隔离检查 |
| PG17-S-H04 | 真实完整 NodeList 的池标签/Ready/taint 验收；尚待主代理执行 |

所有 YAML 使用拒绝重复 key 的 parser，避免后定义 affinity/selector 静默覆盖。
PG17-S-H03 开启旧功能是纯离线覆盖，不是产品范围扩大或相应业务功能验收。

## 下一批仍未完成的接线

- 真实 DSGA 创建/held 初始化、原 VM/Config UID、资格和资源预算来源。
- Agent 的 K8S_POD_UID、可信 dsga 配置、CA、专用 audience token、automaticMemory。
- Scheduler 的真实 dsgaHost Node/Lease/profile/system_bytes 与各 actor 最小 RBAC。
- 独立管理网关的 8444 listener、中心独占证书私钥与允许 Agent 身份。
- control-plane renderer 的 Sysfs CPU mode（当前 QMP 与新 AS 强制模式不兼容）、
  冻结 placement、原创建流程和实际 Runner 验收。
- 真实镜像/内核/cgroup/Guest/Host 能力，扩缩容、失败关闭、恢复、预算和 SQL 一致性。
- server-side CRD/CEL、真实三节点范围以及最终 PG17 内存伸缩 Kubernetes 回归。

不运行 stack 全量 apply，不启动 Web/AI/Functions/Auth/RO/HA 等无关组件。
