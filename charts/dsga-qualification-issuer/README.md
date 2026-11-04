# 原生产资格 Issuer 的独立身份

此 chart 只创建一个专用 ServiceAccount 及其精确 Role/Binding、ClusterRole/Binding，不创建 Pod、Job、镜像、资格或任何原运行对象。`subject.namespace/name` 必须显式给出且等于 Helm release namespace/name；禁止借用 Agent 或 Runner。所有对象名默认 null，缺项无法渲染。

本 namespace 的读取固定到本 VM、原 config Secret、原 Runner Pod、OwnerLease、HostLease，以及五个 ConfigMap：预期资格、原 Birth、State、Exit、StoppedPod。后两者即使尚不存在也必须有精确 get 权限，原消费者须区分404与403并保留停止门。Birth/State后缀须一致，Exit/StoppedPod名由原生产函数与完整Birth派生，不在 chart 发明哈希。HostLease须和 nodeName精确对应；本轮 report 的HostLease在neon，与VM同namespace，不授错误的kube-system权限。

两个不可按 resourceNames 进一步收窄的原 API 动作明确保留：ConfigMap create 仅限 release namespace（无 update/patch/delete/list）；跨 namespace Pod list 由原Inspector固定 fieldSelector `spec.nodeName=<该worker>`，Kubernetes RBAC本身无法约束该selector。本 chart不谎称在服务端将list限制到单节点，也不授Pod watch或Node写。

原资格CM使用 `blockOwnerDeletion: true`。Kubernetes OwnerReferencesPermissionEnforcement 对其owner检查 `update virtualmachines/finalizers`，故单独给本 namespace、本VM名这一项精准授权。Issuer实际不更新VM finalizers；没有VM update/patch/delete，也没有其它VM的finalizers。不得清除blockOwnerDeletion或改原保护门来绕准入。

专用SA默认不自动挂载token。Root在实际权限核验后以TokenRequest取得短600秒token，在原117Agent私有临时目录使用瞬态scoped kubeconfig执行原本地UDS Issuer；终态清理临时token文件。admin凭据留118，不经SSH转发UDS或改信任边界。本 chart不执行这些操作，也不签资格/SQL/内存E通过。
