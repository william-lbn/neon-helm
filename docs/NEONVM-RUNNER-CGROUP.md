# NeonVM runner 的真实 CPU 配额

## 配置与版本

controller.runnerCgroupEnabled 默认 false，显式保留历史实验环境的 dummy 配额模式。设 true 后 controller 不传 disable-runner-cgroup，实际 runner 必须具有 VM 所需的可写 host cgroup 挂载。不能只从 /cpu_current 或 Console 的 250m 数字判断内核配额已应用。

2026-10-15 精确核对原部署镜像 revision c0052f5f2d38fce6c70e448f3f1ee2ee239a0a93，发现动态 CPU 回调只改缓存。自有 autoscaling 分支 fix/runner-cgroup-cpu-limits 的本地提交 172092424135c565a7e49cb696201daa8e15c41b 修复了内核应用/确认顺序，保留原四倍 QEMU 预算。Neon Rust 没有修改。修复源码、Linux race 检查、镜像归档和运行采样保存在控制面配套交付记录中。

本批本地 runner digest 为 sha256:b636612c60251a289240d1a08476dd7a8a423d93924ac3fc35aa9030ebda769b。它已校验并导入三个实验节点；尚未发布为匿名可拉取的公共镜像。本仓库公开 profiles 和 locks 不写入临时 neon.local 地址，也没有将旧公开 runner 宣称为已修复版本。正式发布必须先推送 fork 提交、发布带 source revision/证明的镜像，再更新公开 digest 锁并发行统一 Chart。

## 升级步骤

1. 保存实际 Helm release 的命名空间、values/manifest、旧 digest 与 Secrets/PVC UID。现场 release neonvm 位于 default，controller 资源位于 neonvm-system；不要用资源命名空间猜 release 归属。
2. 按正常生命周期停止测试小数 Compute，保留项目、SQL 数据和复测记录。此次升级不修改 CRD，不重启 RKE2/etcd。
3. 使用精确修复镜像 digest 配置 images.runner，并显式设置 controller.runnerCgroupEnabled: true。镜像必须已可由目标节点解析和校验，不使用可变 latest。
4. 对现有 release 执行本仓库标准 lint/template/upgrade 流程，保留升级记录。确认三个 controller Ready、非目标 release 未变、PVC 和 webhook Secret 的 UID/摘要保留。
5. 新建 250–500m / 1–2Gi Reader，核对 runner 没有 skip-cgroup-management，cgroup 挂载可写，并通过 VM UID/Pod ownerReference 确定采样对象。250m 的 cpu.max 应为 100000/100000；500m 为 200000/100000，符合现有 overcommit=4。
6. 从 Console 验证真实 Reader SQL、正常资源缩回、冷醒和最后缩零。观察内存 status 和宿主 memory.current，分别记录；status 回落不能关闭完整物理 RAM 回收门槛。

新的 Go 控制面 Worker 已为小数 Endpoint 校验真实 runner 的 owner、命令和挂载，dummy 模式无法通过新创建的就绪检查。旧整数路径兼容。回退应先正常停用小数 Endpoint，再恢复已归档配置；旧 runner 不具备本批验收能力。

## 当前验收与边界

现场 Helm revision 52→53，三个 controller Ready；其他 18 个 release 清单、10 个全局 PVC UID、webhook Secret UID 与数据摘要保持。真实 UI 250→500→250m 的 QEMU quota 同步变化，只读 SQL/冷醒/最终缩零通过；另一个新 Reader 的 Worker 准入和 SQL 也通过。新 tests/neonvm-runner-cgroup.test.mjs 只检查该开关的默认、启用和错误类型拒绝，未重跑旧业务。

严格 Guest CPU 隔离、争用公平性/计量、物理 RAM 归还、HA/DR、跨实例栅栏及正式公开发行仍是独立门槛。此配置是明确运行能力开关，不是生产认证开关。
