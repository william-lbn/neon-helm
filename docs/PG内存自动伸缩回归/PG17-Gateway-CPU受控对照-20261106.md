# PG17 当前三 worker 环境的 Gateway CPU 覆盖

本覆盖只用于当前 `neon/neon-compute-management-gateway` release，集群节点为 worker-117、worker-118、worker-119。它把 Gateway CPU limit 从 `500m` 调为 `2`；chart 的通用默认值仍保留 `500m`，其它部署环境需显式选择，不能自动套用。

## 本轮实际变更

- 自有 Helm 分支：`codex/dsga-neon-helm-v3-20261019`；对照基线提交 `13d77016180f5d331e49619c807ee0ab6080b575`，chart `compute-management-gateway-0.1.31`。
- 当前 release 的完整 9 对象离线对照只出现 `/spec/template/spec/containers/0/resources/limits/cpu` 一个变化：`500m → 2`。
- 同一镜像 `127.0.0.1:5001/neon-candidate/compute-gateway@sha256:b0bd6c1f3a939f332bfd4788548a93aa82cbd2ab73abeaa55c191dbc309117ff`。Memory limit `192Mi`、requests `100m/64Mi`、单副本、策略、权限、TLS、QPS、TTL 和所有其它 manifest 字段保持。
- Root 实际 Helm exit 0，耗时 7.254651 秒；Deployment generation 7→8。新 Gateway Pod UID `08acf349-0f8b-471e-a3e0-8f8e57530713` 位于 worker-119，Ready、restart 0，kubelet 从 CRI 回报同一 b0bd 镜像。
- 同一 Compute VM93、Pod00bb、CID460，以及 Agent/Scheduler、资格 Source 与自动策略在前后保护检查中保持。未重建镜像，也未改 Compute 资源或重新放置 Compute。

## 实测与解释

| 指标 | 500m 基线 | 2 CPU 对照 |
|---|---:|---:|
| Gateway CFS 观测时长 | 11.476 秒 | 40.362 秒 |
| Gateway 平均 CPU | 约 0.383 核 | 约 0.33154 核 |
| CFS 被节流周期 | 86/95 | 0 |
| 同一 11 RPC 自然周期样本数 | 62 | 28 |
| 周期中位耗时 | 28.753652 秒 | 10.444294 秒 |
| Compute 内部 span 中位合计 | 5.940913 秒 | 7.161945 秒 |
| 内部 span 之外的中位耗时 | 22.610281 秒 | 3.051256 秒 |

新 2 CPU 自然周期范围为 8.686675–11.497722 秒。Compute 内部没有变快，改善主要发生在内部 span 之外；这些事实支持 Gateway 短周期 CPU 节流放大串行请求间隔的判断。它们不证明所有历史失败均由 CPU 导致，也不是“网络已无延迟”的证明。Pod UID/CID因正常滚动发生变化，表中是同镜像单配置对照与自然观察。

本项属于管理服务配置与吞吐验证，不能替代 PG17 四项内存 E2E：Grow、安全 normal 降限的 Shrink、Regrow、真实策略自动触发；同会话 SQL 数据校验、WAL/资源/实际状态回读仍须由各自真实执行收口。

## 显式使用与回退

先审核目标 release 的实际 values/完整 manifest，仅在这个环境使用覆盖；私有 values 在 RAM 中读取，不归档到 Git。

```sh
KUBECONFIG=/root/.kube/config helm upgrade neon-compute-management-gateway \
  ./charts/compute-management-gateway -n neon --reuse-values \
  -f ./profiles/pg17-k8s-117-118-119/compute-management-gateway-cpu.yaml \
  --wait --timeout 180s
```

升级后核同一 Deployment、单个新 Ready Pod、CPU `2`、Memory `192Mi`、原 requests、实际镜像以及 Compute/Source 保护指纹。需要回退时，只把同一 release 的 `resources.limits.cpu` 明确设回 `500m` 并重复这些保护检查；不通过删除 Pod、修改 TTL/QPS 或回滚无关对象来掩盖结果。

## 本轮来源

- CPU 单字段、values 仅 RAM 预检：`/data/neon-k8s-pg17/runs/Gateway-b0bd-CPU-limit-only-RAM-DISABLED-20261105T161458Z-c744ed/RAM-preflight.PUBLIC.json`，SHA256 `8d5414789e8676791f4bad64af37ec7492a7780f91e5ccd0078da2c3c8705863`。
- Root 实际部署：同目录 `Root-actual-result.PUBLIC.json`，SHA256 `cbab6f45f8a2c675b840e0c78dafd875147b735154b9f352074cd0113117f46c`。
- 同镜像性能对照：`/data/neon-k8s-pg17/runs/same93-Gateway-2CPU-post-readonly-20261105T164031Z-bb96f9/same-image-500m-to-2CPU-readonly-comparison.json`，SHA256 `cfcf12f44efbb3ceb44f8b5c07235488ff53116e13721d0386e27c6e14378ba4`。
- 2 CPU 实际 CFS：同对照目录 `Gateway-new-2CPU-actual-cfs-delta.json`，SHA256 `1510458ec4cb988502b158fb22e9c2833a78cf02b1957fb4d9479718f04ed757`。

公共覆盖只包含一个 CPU 数值，不包含发布凭据、整份 release values、TLS 私钥或业务 Runtime。
