# neon-compute

Part of [Neon Helm](../../README.md). Version 0.1.0.

Read the [deployment](../../docs/DEPLOYMENT.md), [upgrade](../../docs/UPGRADE.md)
and [production gates](../../docs/PRODUCTION-GATES.md) before use. The explicit
lab profile is in [profiles/lab/neon-compute.json](../../profiles/lab/neon-compute.json).

All supported settings are documented inline in values.yaml and validated by
values.schema.json. Defaults intentionally require operator-supplied image locks
and Secret references. Do not use --skip-schema-validation.

Helm release names and namespaces come from stack/stack.json. Preserve their
identities during migration. CI lints, renders and packages this chart on Linux.

PG17 trusted-runtime-v1 必须显式配置 `compute.runtime.podResources.limits.cpu` 与
`limits.memory`，例如本轮 Runner 的 CPU `"4"`、内存 `"10Gi"`；requests 由同一部署预算确定。
Controller 将原资源的 CPU/内存 requests/limits 独立复制给内置 root/kernel init，
顺序初始化峰值不会超过同一 Pod 上限，KVM/GPU 设备仅给 Runner。
首版 DSGA 明确拒绝非空 ExtraInitContainers，防止额外初始化绕过固定 Pod 预算；legacy 输出保持原行为。
这属于 Kubernetes 容量预算，不构成整台宿主机内核的物理上界证明。
Guest 最小 7Gi、最大 8Gi 时，Host 固定额外 3Gi 可覆盖 cap10Gi：7+3=10、8+3=11Gi；
必须核实际 Runner Pod 限额及 memcg 后，才能报告此预算已生效。

聚焦渲染检查：`python3 charts/neon-compute/tests/pod-resources.py --output /data/新的归档目录`。
只核本次资源接线、旧 legacy 输出与缺失/非法限额拒绝，不访问集群。
