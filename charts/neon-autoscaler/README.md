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


### PG17本机完整Owner管理UDS（默认关闭）

`dsga.agent.controlSocket`只接通已有Agent `controlSocketPath`与localcontrol原协议，
不新增HTTP监听器、SDK或Owner。需要确定顺序的实际7→8→7→8回归时可显式配置：

```yaml
dsga:
  agent:
    controlSocket:
      enabled: true
      hostDirectory: /run/neon-dsga-pg17-control
      mountDirectory: /run/neon-dsga-pg17-control
      name: control.sock
```

三个worker须由原部署者预建该独立目录`root:root 0700`；实际Agent必须以原安全主体可写，
已有localcontrol服务创建socket `0600`并继续核SO_PEERCRED/原Owner。chart只用`hostPath.type=Directory`，
不创建目录、不chown，不应把它与普通租户或资格发布器共享。路径只允许规范的
`/run/neon-dsga-*`私有子目录；full与resourceReadSocket的host/mount目录不能相同或互为祖先。
`resourceReadSocket`保持独立只读API，仍只能`resource_state`，绝不能把它当Begin或恢复入口。

默认off不增加配置键或挂载，原完整manifest语义保持。仅此接线相关的可复验渲染在
`tests/full-control-uds.py`；运行`python3 charts/neon-autoscaler/tests/full-control-uds.py --output <新的归档目录>`。
测试只有本地render/schema/lint及默认AST比较，不创建Node/Lease/资格或执行集群操作。
手动Owner Begin三轮只验证原执行链；真实SQL压力/空闲触发AutomaticMemory仍须独立实际验收。


### 普通Pod停止来源的精确只读授权（默认关闭）

dsga.scheduler.ordinaryStopSourceNames 默认空列表，不生成额外权限。运维者在固定
kube-system 命名空间发布本轮不可变来源CM并读回真实UID及内容摘要后，显式填写这些
ConfigMap精确名称。非空列表仅新增该命名空间的Role与RoleBinding：原Scheduler账号
kube-system/autoscale-scheduler只能get这些名称，不增加list/watch/create/update/patch/delete。
名称列表最多256项，拒绝空名、重复、通配符及非法ConfigMap DNS名；其它Agent、
Deployment策略、Plugin配置、Host账本均不改变。

信任边界是固定运维命名空间的写权限与显式来源发布流程。名称、SHA、Node ownerRef及
blockOwnerDeletion本身不是Node签名或来源认证；本集群实际干跑没有拒绝Runner设置该ownerRef。
消费者仍须核验完整来源内容、不可变性、实际Node/Pod绑定及原退休fence/CAS。
只加读取权限不表示允许结清Unknown；缺少有效来源或原终态事实时仍拒绝。
本专项沿原tests/pod-protection-rbac.py离线检查；真实具名SAR和来源CM发布另行归档，
不把渲染成功当作实际授权或停止证明。
