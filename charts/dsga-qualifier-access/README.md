# 原生产 Collector 的精确只读接线

本 chart 为复用原 Agent ServiceAccount 的正式资格 Collector 增加两个明确的读取权限：Helm release 所在 namespace 的一个原 Compute config Secret，以及一个部署 worker Node。它不创建 ServiceAccount、Secret、VM、资格、Pod 或任何其它业务对象。

`subject.namespace`、`subject.name`、`configSecretName`、`nodeName` 均须显式设置，默认 null 会在 schema/template 阶段拒绝。Secret 名只允许 `cp-16位小写hex-config` 形式；Node 只允许 worker-117/118/119。subject 的跨 namespace 引用是显式原 ServiceAccount，不是 namespace 全体。

所有 rules 只有 `get` 与一个精确 resourceNames；没有 list、watch、创建、写入或通配。RoleBinding/ClusterRoleBinding 只绑定该 ServiceAccount，不授 Runner 或其它主体。角色名称由 release namespace/name 稳定派生，摘要保留完整身份以避免截断碰撞。

本轮由 Root 使用 release `neon-pg17-qualifier-access`、namespace `neon`，实际 values 另存 private run；chart 不携带生产凭据或默认主体。先本地 lint/template 静态审查四个 RBAC 对象，Root 精确提交/审查后才独立部署，并实际核验指定 Secret/Node 的 get 正例与其它范围拒绝。渲染通过不能冒称权限已授予或资格已通过。
