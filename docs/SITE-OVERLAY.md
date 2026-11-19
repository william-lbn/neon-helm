# 站点 overlay 与数据面部署

Neon Helm 的 Chart 是通用的。站点差异只放在 overlay 里，不要改模板去写死主机名、仓库或 StorageClass。

相关文档：

- 集群前置（cert-manager / 本地盘 / Multus / metrics-server）：[CLUSTER-PREREQUISITES.md](CLUSTER-PREREQUISITES.md)
- 密钥、render / preflight / apply：[DEPLOYMENT.md](DEPLOYMENT.md)
- 已有集群升级：[UPGRADE.md](UPGRADE.md)

本文件说明：overlay 怎么写、镜像怎么钉、如何只装到控制面之前，以及现有实验集群升级时不要混用 overlay。

## 1. 三层配置

```text
charts/                 通用模板，进 Git
profiles/lab/*.json     公开默认值；Digest 钉公开仓库；不含密码
/secure/neon-overlay/   本集群 overlay，不要提交
```

overlay 文件名必须等于 Chart 名，例如 `neon-core.json`、`neonvm.json`。
`tools/stack.mjs` 把 lab profile 与 overlay **深合并**；**数组整段替换**。

因此 `placement.allowedNodeNames` 必须在 overlay 里写出完整列表，不能只改其中一个名字。

## 2. Git 与分支

维护分支：`codex/dsga-neon-helm-v3-20261019`

从能访问 GitHub 的机器（例如已登记 SSH 公钥的实验室节点）检出：

```bash
git clone --branch codex/dsga-neon-helm-v3-20261019 \
  git@github.com:william-lbn/neon-helm.git
cd neon-helm
```

推送必须用 SSH 远程。HTTPS 远程不会使用本机 SSH 公钥：

```bash
git push git@github.com:william-lbn/neon-helm.git HEAD:codex/dsga-neon-helm-v3-20261019
```

不要提交 Chart `.tgz`、Harbor 地址、节点名、kubeconfig 或 Secret。

## 3. 节点列表（通用 Chart，站点 overlay）

Chart 默认仍是实验室主机名 `worker-117` / `worker-118` / `worker-119`，避免旧 overlay 静默失效。
新集群必须在每个相关 Chart 的 overlay 里替换为**真实 hostname**：

```json
{
  "placement": {
    "allowedNodeNames": ["node1", "node2", "node3", "node4", "node5"]
  }
}
```

规则：

- 至少一个合法 Kubernetes hostname，禁止重复。
- 模板会生成节点池标签 `neon.tech/pg17-memory-pool: <按字母序用 - 拼接的主机名>`。
- **必须先给这些节点打上同一标签**，否则 Pod 无法调度。
- 可选角色钉节点只能用 `kubernetes.io/hostname`，且必须属于上述列表：
  - `minio.nodeSelector`
  - `storageController.nodeSelector`
  - `controller.nodeSelector`（NeonVM）
  - `scheduler.nodeSelector`（autoscaler）
  - `neon-metadata` 的 `nodeSelector`

示例（存储盘固定在 `node2`）：

```json
{
  "placement": {
    "allowedNodeNames": ["node1", "node2", "node3", "node4", "node5"]
  },
  "minio": {
    "nodeSelector": {"kubernetes.io/hostname": "node2"},
    "persistence": {"storageClassName": "local-path", "size": "20Gi"}
  },
  "storageController": {
    "nodeSelector": {"kubernetes.io/hostname": "node2"},
    "persistence": {"storageClassName": "local-path", "size": "5Gi"}
  }
}
```

给节点打标签（主机名与拼接结果必须和 overlay 一致）：

```bash
POOL=node1-node2-node3-node4-node5
for n in node1 node2 node3 node4 node5; do
  kubectl label node "$n" "neon.tech/pg17-memory-pool=$POOL" --overwrite
done
```

现有 117/118/119 实验集群升级时，overlay 继续写原来的三个 worker，不要改成新集群主机名。

## 4. 镜像：钉内网仓库的实际 Digest

Chart 校验要求完整引用：

```text
<registry>/<repository>@sha256:<64 hex>
```

**禁止**把上游 Quay / Docker Hub / 源仓库的 Digest 写进内网 overlay，再对镜像做 `docker pull && docker tag && docker push`。
Docker 重新 push 会生成新的 Manifest Digest，kubelet 按源 Digest 拉 Harbor 会 `ImagePullBackOff`。

正确做法：

1. 记录上游身份（仓库 + 源 Digest + 人类可读 tag）。
2. 拷进 Harbor 时优先 digest 保留拷贝（`skopeo copy` / `crane copy`）。
3. 拷完后读取 **Harbor 实际 Manifest Digest**。
4. overlay 只钉：

```text
<harbor>/<project>/<name>@sha256:<HarborDigest>
```

Harbor 的 tag（例如 `sha-044e6aa358bea5ae`）只给人看；Kubernetes / Helm 仍应带 `@sha256:HarborDigest`。
`tag@sha256:...` 也可以，Digest 必须是 Harbor 的。

cert-manager 等前置 Chart 若填写 `image.digest`，同样必须是目标仓库 Digest。见 [CLUSTER-PREREQUISITES.md](CLUSTER-PREREQUISITES.md) 第 2 节。

## 5. 本地存储

Helm 只写 `storageClassName`。节点绑定用 StorageClass + WaitForFirstConsumer，或 Local PV 的 nodeAffinity。

本仓库不创建 StorageClass。先按前置文档安装 `local-path`（或等价本地类），PVC 名称由 Chart 固定，不要改：

| 组件 | PVC |
|---|---|
| MinIO | `minio-data` |
| 存储控制面 DB | `controller-db-data` |
| Pageserver | `pageserver-cache` |
| Safekeeper 1/2/3 | `safekeeper{1,2,3}-data` |
| 元数据 | Chart 默认 `neon-control-v2-db` |
| 托管 Pageserver | `pageserver-managed-cache` |

## 6. 只装数据面（不装控制面）

`stack/stack.json` 默认 8 步，最后一步是 `neon-control-plane`。

停在网关（含 NeonVM、autoscaler、metadata、adapter、core、managed-pageserver、gateway）：

```bash
node tools/stack.mjs plan --until neon-compute-management-gateway
node tools/stack.mjs render --until neon-compute-management-gateway \
  --overlay-dir /secure/neon-overlay --output /secure/neon-render-001
node tools/stack.mjs preflight --until neon-compute-management-gateway \
  --overlay-dir /secure/neon-overlay --output /secure/neon-preflight-001
node tools/stack.mjs apply --maintenance-window --until neon-compute-management-gateway \
  --overlay-dir /secure/neon-overlay --output /secure/neon-install-001
node tools/stack.mjs verify --until neon-compute-management-gateway \
  --overlay-dir /secure/neon-overlay --output /secure/neon-verify-001
```

`--until` 接受 **release 名或 chart 名**。使用 `--until` 时，preflight **不再**要求 `neon-control-plane-credentials` 和 `neon-backend-credential-keys-v1`。
数据面仍需要 object-store、controller-db、proxy TLS、hook token、metadata 密码和 `neon-control-routes`。

本轮不要装：

- `neon-control-plane` / Console / Worker / API
- 静态 `neon-compute`（PG17/PG18 Guest 由控制面 Driver 创建）
- DSGA 资格 Chart（`dsga-qualification-issuer` 等）

新集群的 overlay 不要复制旧集群的 Lease UID、VM UID、tenant/timeline 或 `dsga.enabled: true` 资格表。

## 7. 密钥

仍按 [DEPLOYMENT.md](DEPLOYMENT.md) 在 Helm 之外创建 Secret。新实验室：

```bash
node tools/bootstrap-state.mjs
node tools/prepare-lab-secrets.mjs --output /secure/neon-bootstrap-001 --acknowledge-lab
kubectl -n neon create -f /secure/neon-bootstrap-001/neon-object-store.private.json
# ... 其余 Secret；不要用 apply 覆盖已有集群
```

即使本轮不装控制面，也可以生成全套密钥并先不创建控制面那两份；或全部创建但暂不安装控制面 Chart。

## 8. 现有 118 实验集群

升级 118 时：

1. 不要使用新集群 overlay。
2. `helm get values -a` 导出当前 Release，做成兼容 overlay。
3. `placement.allowedNodeNames` 保持 `worker-117` / `worker-118` / `worker-119`。
4. 镜像保持 118 正在运行的 Digest。
5. 控制面仍是产品线 `neon-control-plane-0.9.89`，不要用本仓较旧的 `0.1.32` 控制面 Chart 覆盖 `neon-control-r4`。

## 9. 验收（数据面）

```bash
kubectl get nodes --show-labels | grep pg17-memory-pool
kubectl get sc
kubectl -n neonvm-system get deploy,ds
kubectl -n neon get deploy,ds,pvc
kubectl get pods -A | grep -Ev 'Running|Completed'
```

MinIO / controller-db 的 PVC 应落到 overlay 指定的存储节点。
不要用 Console 或公开创建项目来验收本轮；那些依赖控制面。
