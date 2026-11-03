# 独立 Runner 最小权限

此 chart 默认关闭，只创建本次 Runner 的 ServiceAccount 与 RBAC，不创建 VM、Service、Secret、资格证明或真实 UID，也不接管 runtime-prepare 已创建的对象。实际工作负载固定在 worker-117/118/119，116 没有 Node 读取授权。

默认身份和 Host Lease 列表均为空，单独打开 enabled 会被拒绝。真实 namespace、独立 SA、`cp-<16hex>` VM 与 `<VM>-config` Secret 必须由当次归档 release values 显式给出，不能复用旧实例默认身份。VM 与 Config Secret 都仅精确名字 `get`；Runner 不写 VM journal。它只读自身 Pod、owner/Host Lease、三台 Node，并创建/读取本 namespace 的领域 ConfigMap。Kubernetes 的 CREATE 鉴权没有 URL 资源名，不能用 `resourceNames` 限制将来 body 内的 CM 名字，因此这里明确只开放 namespace 内的 CM create，不宣称逐对象创建隔离。

pre-hold 可以保留 `ownerLease.name`、`stateClaimName` 为空，此时没有 owner Lease 许可或 CM update。hold 取得真实 VM UID 后，用原绑定 `[namespace, name, VMUID, incarnation]` 派生 owner Lease 与唯一 state claim 名，显式更新 values；在 runtime-prepare 原 seal/ready 之前装好权限。state claim 格式为 `dsga-s-` 加 56 位小写十六进制，其来源是 `vmguard/publication.go:140` 的原函数，格式校验不代替实际 UID 来源核验。不得预造 UID、同名接管或把空值当成完整就绪。

唯一 CM update 只授给显式 `stateClaimName`；没有其它 update/patch/delete/list/watch。Config Secret 不包含私钥，不授读取 `<VM>-credentials` 的权限。三个 Host Lease 逐 namespace/精确 name 只读。Node 为 ClusterRole，只含三台 worker 的 get。Controller 原有 managed Pod 已显式挂载其 SA token；SA 自身默认关闭自动挂载供其它 Pod 使用，不更改 Controller。

复现渲染与 RBAC 正负检查（需要已有 Helm 3、Python 3 与 PyYAML）：

```sh
python3 charts/dsga-runner-access/tests/render-rbac.py
helm lint charts/dsga-runner-access --strict
helm template pg17-runner-access charts/dsga-runner-access -n neon -f "$RUNNER_VALUES"
```

`RUNNER_VALUES` 应指向当次真实归档 values 文件；测试脚本自身使用明确的合成身份，不创建实例。

检查仅本 chart 的默认关闭、pre/post-hold 权限、对象范围和非法输入拒绝，不访问集群或执行故障注入。Root 统一保存真实 Lease/UID 来源、Git 提交以及实际 Helm install/upgrade；此处不执行 apply。
