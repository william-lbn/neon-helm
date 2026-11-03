# neon-autoscaler

Part of [Neon Helm](../../README.md). Version 0.1.0.

Read the [deployment](../../docs/DEPLOYMENT.md), [upgrade](../../docs/UPGRADE.md)
and [production gates](../../docs/PRODUCTION-GATES.md) before use. The explicit
lab profile is in [profiles/lab/neon-autoscaler.json](../../profiles/lab/neon-autoscaler.json).

All supported settings are documented inline in values.yaml and validated by
values.schema.json. Defaults intentionally require operator-supplied image locks
and Secret references. Do not use --skip-schema-validation.

Helm release names and namespaces come from stack/stack.json. Preserve their
identities during migration. CI lints, renders and packages this chart on Linux.

PG17 Host 预算必须把三 worker 上所有普通 Pod（包括 kube-system）的真实硬限入账。
启用 DSGA 时，显式设置 `dsga.scheduler.podProtectionNamespaces` 为
`[kube-system, neon-cert-manager, neonvm-system]`，仅新增各 namespace 的 pods get/patch
Role 与绑定；neon 原 Role 不变，不额外授予 delete/update/exec/secret/node 权限。
RBAC 按 namespace 授权，无法按 Pod 所在 Node 过滤，因此不能宣称它单独拒绝116上的Pod。
生产 `reserveHost` 的 HasNode 门只接受117/118/119；`allocation` 重读同UID/Node，
`protectPod` 用原UID/RV条件仅追加保护finalizer并真实GET确认，116不进入该保护路径。
实际回归需保留正负SAR以及116 Pod spec/finalizer前后读回；既有上游Scheduler角色的权限应单独列明。

启动顺序：先部署其它组件和无初始化RV的Agent/Scheduler，Agent三Pod就绪后固定实际Pod清单。
Scheduler需Host ledger才能完成初始事件门，不能要求其先Ready再建账本；所有其它组件稳定后，
冻结原Node RV并以原HostBootstrap一次建账，之后再核Scheduler Ready与完整预算。
未初始化时的原15s启动拒绝保留失败日志，不能当部署通过或绕过Node CAS。

聚焦离线检查：`python3 charts/neon-autoscaler/tests/pod-protection-rbac.py --output /data/新的归档目录`。
该入口不访问集群；实际SAR与Pod读回单独归档。

DSGA 单例 Scheduler 首次启动使用 Recreate，避免固定118上瞬时出现两个2000Mi副本；
legacy仍使用原滚动更新。未建Host ledger时，原Reserve必须先Load/checkProfile，
确认域已存在后才给原Pod追加保护finalizer。首次恢复只可移除本任务已证明孤立的
Scheduler保护，不能移除其它finalizer或未知容量持有；已建账后的维护须按原退休合同结清。
