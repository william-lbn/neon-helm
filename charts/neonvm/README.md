# neonvm

Part of [Neon Helm](../../README.md). Version 0.1.0.

Read the [deployment](../../docs/DEPLOYMENT.md), [upgrade](../../docs/UPGRADE.md)
and [production gates](../../docs/PRODUCTION-GATES.md) before use. The explicit
lab profile is in [profiles/lab/neonvm.json](../../profiles/lab/neonvm.json).

All supported settings are documented inline in values.yaml and validated by
values.schema.json. Defaults intentionally require operator-supplied image locks
and Secret references. Do not use --skip-schema-validation.

Helm release names and namespaces come from stack/stack.json. Preserve their
identities during migration. CI lints, renders and packages this chart on Linux.

### 受管内存的正常退役权限

`controller.managedMemoryRetirement.enabled` 默认 `false`，不会生成新增权限。受管部署须显式启用，并将 `namespaces` 设为实际 VM 命名空间（本轮仅 `neon`）。这些权限让原 Controller 执行既有退役函数，不直接移除 VM/Pod/来源保护。

新增的 Node `get` 仅授予 `placement.allowedNodeNames` 三个 worker；116 的单对象 `get` 仍拒绝。原 `finalizeManagedMemory` 还必须分页 `list` 全部节点，检查旧 VM 在所有节点均无持有；不带 name 选择器的 `list` 无法按 `resourceNames` 限制，因此该只读列表会包含116，不能声称116不可读。没有新增 Node 写权限。

每个显式 VM 命名空间仅新增 ConfigMap `get/list/patch/delete`。原源码继续核唯一 VM owner 名称/UID、来源版本及保护类型，并在 patch/delete 使用真实 UID/RV；没有新增 Secret、Pod 或 Lease 权限。默认关闭时其余对象与 PodSpec 不变。相关定向渲染入口为 `python3 docs/validation/controller-retirement-rbac-focused.py --repo . --output /data/独立归档目录`。
