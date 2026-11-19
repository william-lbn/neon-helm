# 集群前置：联网部署与离线部署

Neon Helm **不包含** cert-manager、本地存储、Multus、Whereabouts、metrics-server。
`stack.json` 把它们列为 prerequisites。必须在 `node tools/stack.mjs apply` 之前装好。

本文件只说明 **怎么装前置**。不要把上游 Chart `.tgz` 提交进本仓库（`.gitignore` 已忽略 `*.tgz`）。
本仓库也不存放内网 Harbor 地址、节点名或凭据。

安装前检查：

```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
kubectl get nodes
kubectl get storageclass
kubectl get crd certificates.cert-manager.io \
  network-attachment-definitions.k8s.cni.cncf.io \
  ippools.whereabouts.cni.cncf.io
```

四项都 Ready / 存在后，再进入 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 1. 装什么

| 组件 | 作用 | 建议来源 | 建议版本 |
|---|---|---|---|
| cert-manager | NeonVM webhook 证书 | Jetstack 官方 Chart | `v1.19.6` |
| local-path-provisioner | 本地盘动态供给 | Rancher / containeroo Chart | Chart `0.0.38`，镜像 `v0.0.37` |
| metrics-server | HPA / autoscaler 指标 | RKE2 `rke2-metrics-server` 或 kubernetes-sigs Chart | RKE2 `3.12.004` / app `0.7.1` |
| Multus | NeonVM 第二张网卡 | RKE2 `rke2-multus` 或上游 Multus Chart | RKE2 `v4.1.205` / app `4.1.2` |
| Whereabouts | 第二张网卡 IPAM | **RKE2 Multus 子 Chart**，不要单独再装一份冲突的 Chart | 随 Multus，app `v0.8.0` |

节点还需要：

- 每台候选 Compute 节点有 `/dev/kvm`、`/dev/vhost-net`
- 本地盘目录（示例 `/data/neon-local`），权限允许 local-path 写
- 默认 StorageClass，`WaitForFirstConsumer`，生产建议 `Retain`

这些是集群平台组件，不要写进 Neon Chart 模板。

## 2. 镜像钉法（联网和离线都适用）

**不要**把上游 Quay / Docker Hub 的 `@sha256:...` 直接写到内网 values 里，再对镜像做 `docker pull && docker tag && docker push`。
Docker 重新 push 会生成 **新的 Manifest Digest**。集群按源 Digest 拉 Harbor 会 `ImagePullBackOff`。

推荐分层：

| 层 | 写什么 | 作用 |
|---|---|---|
| 人类可读版本 | Chart `version` + 镜像 `tag`（如 `v1.19.6`、`v0.7.1-build20241008`） | 对账、升级、文档 |
| 内网不可变钉 | **你们仓库里的** `repository@sha256:...` 或 `repository:tag@sha256:...` | 真正给 Kubernetes 用 |

操作规则：

1. 上游身份用官方 **tag + 源 Digest** 记录在离线清单里，便于以后核对“我们拷的是哪一版”。
2. 拷进内网仓库时优先用 **digest 保留拷贝**：
   ```bash
   skopeo copy --all \
     docker://quay.io/jetstack/cert-manager-controller@sha256:<源digest> \
     docker://<内网仓库>/jetstack-cert-manager-controller:<版本tag>
   ```
   `crane copy` / `oras copy` 同类。不要用会改 Manifest 的 `docker tag` + `docker push`。
3. 拷完后 **读 Harbor 实际 Digest**，values 只钉这个 Digest（或 `tag@sha256:HarborDigest`）。
4. 若已经用 Docker 推过、Digest 已变：不要回填源 Digest。改 values 使用 Harbor 的 tag 或 Harbor Digest，并在清单里同时记下源 Digest 与 Harbor Digest。

cert-manager Chart 的 `image.digest` 一旦填写，就会渲染成 `仓库@sha256:...`。
内网必须填 **Harbor 的 Digest**；只填 tag 时不要再填错误的源 Digest。

## 3. 联网部署

集群能访问官方 Helm 仓库和镜像仓库时用这一节。内网镜像仓库可在 values 里改 `repository`/`tag`。

### 3.1 拉 Chart（不要提交 tgz）

```bash
mkdir -p "$HOME/neon-prereqs/charts"/{cert-manager,local-path-provisioner,metrics-server,multus}
helm repo add jetstack https://charts.jetstack.io
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm repo add local-path https://charts.containeroo.ch
helm repo update

helm pull jetstack/cert-manager --version v1.19.6 \
  -d "$HOME/neon-prereqs/charts/cert-manager"
helm pull local-path/local-path-provisioner --version 0.0.38 \
  -d "$HOME/neon-prereqs/charts/local-path-provisioner"
helm pull metrics-server/metrics-server --version 3.14.0 \
  -d "$HOME/neon-prereqs/charts/metrics-server"
```

RKE2 集群也可以不用上游 metrics-server/Multus Chart，而用节点上已有的：

- `/var/lib/rancher/rke2/server/manifests/rke2-metrics-server.yaml`
- `/var/lib/rancher/rke2/server/manifests/rke2-multus.yaml`

其中 `spec.chartContent` 是 gzip+base64 的 Chart。解码后得到 `rke2-metrics-server` 与 `rke2-multus`（含子 Chart `rke2-whereabouts`）。
这样与 RKE2 版本一致，内网无需再找 Rancher Chart 仓库。

### 3.2 每台节点准备本地目录

```bash
mkdir -p /data/neon-local
chmod 755 /data/neon-local
```

目录可按站点修改，但必须与 local-path values 里的 `nodePathMap` 一致。

### 3.3 values 要点（站点 overlay，不要进 Git）

cert-manager：

```yaml
crds:
  enabled: true
  keep: true
image:
  repository: quay.io/jetstack/cert-manager-controller   # 或内网仓库
  tag: v1.19.6                                          # 若改用 digest，必须是目标仓库 Digest
cainjector:
  image:
    repository: quay.io/jetstack/cert-manager-cainjector
    tag: v1.19.6
webhook:
  image:
    repository: quay.io/jetstack/cert-manager-webhook
    tag: v1.19.6
startupapicheck:
  image:
    repository: quay.io/jetstack/cert-manager-startupapicheck
    tag: v1.19.6
```

local-path：

```yaml
image:
  repository: docker.io/rancher/local-path-provisioner
  tag: v0.0.37
helperImage:
  repository: docker.io/library/busybox
  tag: "1.36.1"          # 不要用浮动 latest
storageClass:
  create: true
  defaultClass: true
  name: local-path
  defaultVolumeType: hostPath
  reclaimPolicy: Retain
  volumeBindingMode: WaitForFirstConsumer
nodePathMap:
  - node: DEFAULT_PATH_FOR_NON_LISTED_NODES
    paths:
      - /data/neon-local
```

metrics-server（kubelet 证书未统一时，实验室可加 insecure；生产应换成正确 kubelet 证书）：

```yaml
image:
  repository: rancher/hardened-k8s-metrics-server
  tag: v0.7.1-build20241008
args:
  - --cert-dir=/tmp
  - --kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname
  - --kubelet-use-node-status-port
  - --kubelet-insecure-tls
  - --metric-resolution=15s
```

Multus / Whereabouts：

```yaml
image:
  repository: rancher/hardened-multus-cni
  tag: v4.1.2-build20241011
cniplugins:
  image:
    repository: rancher/hardened-cni-plugins
    tag: v1.5.1-build20241009
config:
  cni_conf:
    confDir: /etc/cni/net.d
    binDir: /opt/cni/bin
    kubeconfig: /etc/cni/net.d/multus.d/multus.kubeconfig
    multusConfFile: auto
rke2-whereabouts:
  enabled: true
  image:
    repository: rancher/hardened-whereabouts
    tag: v0.8.0-build20241011
  cniConf:
    confDir: /etc/cni/net.d
    binDir: /opt/cni/bin
```

`confDir` 必须指向 **主 CNI 配置所在目录**。RKE2 + Cilium 常见为 `/etc/cni/net.d`（例如 `05-cilium.conflist`）。
不要挂空的 `/var/lib/rancher/rke2/agent/etc/cni/net.d`，否则 Multus 会报 `cannot find valid master CNI config` 并 CrashLoop。

Whereabouts 的 `ippools.whereabouts.cni.cncf.io` 若 Chart 未自动装上，从子 Chart 的 `crds/` 再 `kubectl apply` 一次。

### 3.4 安装顺序

```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml

helm upgrade --install cert-manager \
  "$HOME/neon-prereqs/charts/cert-manager/cert-manager-v1.19.6.tgz" \
  -n cert-manager --create-namespace \
  -f "$HOME/neon-prereqs/values/cert-manager.yaml" \
  --wait --timeout 10m

helm upgrade --install local-path \
  "$HOME/neon-prereqs/charts/local-path-provisioner/local-path-provisioner-0.0.38.tgz" \
  -n local-path-storage --create-namespace \
  -f "$HOME/neon-prereqs/values/local-path.yaml" \
  --wait --timeout 5m

helm upgrade --install metrics-server \
  "$HOME/neon-prereqs/charts/metrics-server/<metrics-server>.tgz" \
  -n kube-system \
  -f "$HOME/neon-prereqs/values/metrics-server.yaml" \
  --wait --timeout 5m

helm upgrade --install rke2-multus \
  "$HOME/neon-prereqs/charts/multus/rke2-multus.tgz" \
  -n kube-system \
  -f "$HOME/neon-prereqs/values/multus.yaml" \
  --wait --timeout 10m
```

验收：

```bash
kubectl -n cert-manager get deploy
kubectl -n local-path-storage get deploy
kubectl -n kube-system get deploy,ds | grep -Ei 'metrics-server|multus|whereabouts'
kubectl get sc
kubectl get crd certificates.cert-manager.io \
  network-attachment-definitions.k8s.cni.cncf.io \
  ippools.whereabouts.cni.cncf.io
kubectl get pods -A | grep -Ev 'Running|Completed'
```

`rke2-multus` 与 `rke2-multus-rke2-whereabouts` 应在全部 Linux 节点 Ready。
StorageClass `local-path` 应为 default（若这是该集群唯一本地类）。

## 4. 不能联网时部署

目标集群不能访问 Docker Hub / Quay / GitHub 时，分两台机器做。

### 4.1 在能联网的机器上准备包

1. 按第 3.1 节拉 Chart tgz（仍不要提交到 Git）。
2. 按第 2 节把镜像 **digest 保留拷贝** 到内网仓库；或 `docker save` 成 tar：
   ```bash
   docker pull <上游>:<tag>
   docker save -o cert-manager-controller.tar <上游>:<tag>
   ```
3. 把下列内容拷到目标 master 的同一目录（示例 `$HOME/neon-prereqs`）：
   - `charts/<组件>/*.tgz`
   - `values/*.yaml`（已改成内网仓库，**Digest 用内网仓库的**）
   - 可选 `images/*.tar`
   - 本文件的离线核对清单

不要把 kubeconfig、Harbor 密码、`.docker/config.json` 放进 Git 或共享目录明文。

### 4.2 在离线集群上导入镜像

优先让 kubelet 从内网 Harbor 拉。若暂时没有 Harbor，再在 **每一台节点** 导入：

```bash
ctr -n k8s.io images import images/cert-manager-controller.tar
# 或 nerdctl --namespace k8s.io load -i ...
```

只在一台节点 import **不够**。DaemonSet（Multus / Whereabouts）每个节点都要能解析到镜像。

### 4.3 离线 helm install

与第 3.4 节相同，Chart 用本地 tgz，values 指向内网仓库或已 import 的镜像名。
`helm upgrade --install` 不需要访问 Helm 仓库。

## 5. 注意事项

1. **前置不属于 Neon Chart。** 不要把 cert-manager / Multus 塞进 `neon-core`。后续 Neon 升级不应卸载这些 Release。
2. **现网 overlay 不能拿到新集群用。** 旧实验集群的节点名、StorageClass、镜像仓库只属于那一套 overlay。新环境另写 values。
3. **Multus 必须看到主 CNI。** 先在节点上确认 `ls /etc/cni/net.d` 有 Cilium/Calico 配置，再填 `confDir`。
4. **Whereabouts 不要装两份。** RKE2 Multus 子 Chart 已经带一份；再装上游 whereabouts 容易抢 CRD。
5. **local-path 不是跨节点共享盘。** RWO PVC 会跟 Pod 落在同一节点。MinIO、controller-db 要固定节点时，用 WaitForFirstConsumer + Local PV 的 nodeAffinity，或单独的 StorageClass；不要改 Neon Chart 模板去写死 hostname。
6. **helper / pause / cni-plugins 也要进内网仓库。** Multus 的 init 容器 `hardened-cni-plugins`、local-path 的 `helperImage` 漏掉时，主容器镜像正确也会 `Init:ImagePullBackOff`。
7. **cert-manager CRD 先于 webhook Ready。** `crds.enabled=true`。NeonVM 证书要等 webhook 三个 Deployment Ready。
8. **metrics-server `--kubelet-insecure-tls` 只适合实验室。** 生产应配置 kubelet 证书。
9. **不要提交 Chart 包和站点 values。** Git 只保留本说明；tgz、Harbor 地址、节点列表放在受控目录。
10. **装完前置再跑 Neon `stack.mjs`。** `preflight` 会查这三项 CRD 和 StorageClass；缺了会直接失败，且不会替你安装。

## 6. 与 Neon 产品 Helm 的边界

```text
本文件：cert-manager / local-path / metrics-server / Multus / Whereabouts
        （集群前置，独立 Helm Release）

docs/DEPLOYMENT.md：neonvm → autoscaler → metadata → adapter
                    → neon-core → managed-pageserver → gateway
                    → control-plane
```

前置失败时不要改 Neon Chart。先看镜像能否从内网仓库拉取、Multus 是否找到主 CNI、StorageClass 是否存在。
