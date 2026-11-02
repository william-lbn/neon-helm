# 独立平台资格发布器

本 chart 默认关闭，默认不生成任何 Kubernetes 对象。镜像、原 VM/Node 绑定、私有输入和 Agent 资源读取 socket 均不提供可运行的样例值。它只接通现有 `dsga-platform-qualifier --config <原文件>`；镜像 ENTRYPOINT 必须直接执行该二进制，由发行镜像负责人提供真实 digest。

发布成功不代表平台认证完成。root 保护的启动配置固定原报告 SHA，Linux 验收与持续硬约束两份 artifact 必须独立取证并匹配原 SHA；当前原系统 Pod/Host 包络缺口未闭合时不能用测试文件生成资格。此 chart 不生成报告、资格 ConfigMap、Node 预算、VM 或 Agent 配置，也不改 CNI、systemd、网络或发行锁。

## 部署前置

1. 选择原 worker-117、worker-118 或 worker-119，按已观察 Node UID 固定 `binding`。ubuntu/172.24.79.116 不在允许名单。Job 必须由 `autoscale-scheduler` 进入现有 Host allocator，只有 nodeSelector，没有 nodeName；所有容器均有正 hard memory limit。Host 初始建账与实际 Pod 硬限额缺失仍会拒绝，不能用 Job 绕过。
2. 独立签发主体在所选节点预建原私有输入目录，root UID 0 所有、目录0700、文件0600或更严格。祖先不可被非管理者替换且无 symlink。Job 只读挂原目录，不使用 DirectoryOrCreate、复制、chown 或 fsGroup。`inputs.mountDirectory` 必须对应原配置中 report/artifact 的绝对路径；Helm 不重写私有配置。
3. Agent 必须实际启用独立 `resourceReadSocketPath`，并通过预建 root 私有 hostPath 映射到它自己的 mountDirectory/name。原完整 `controlSocketPath` 不得共享。发布器私有 Config 的既有 `control_socket_path` 字段指向这个独立资源读取 socket；不增加 CLI flag 或公共 DTO。
4. 必须从实际 Agent ConfigMap/DaemonSet 或 live 投影核对 hostPath→mountPath、socket 名称及 sourceManifestSHA256，不能猜 `/run` 路径。原 neon-autoscaler 的显式接线为 `dsga.agent.resourceReadSocket.{enabled,hostDirectory,mountDirectory,name}`，默认关闭；必须先完成该接线并观察实际 socket，单凭本 chart 的 values 不能视为此前置已满足。
5. 资源读取 socket 必须真实存在、root/可信服务 UID 所有、模式0600、父目录私有。输入、资源 socket 和 API token 的挂载目录不得相同或嵌套。发布器会固定原 dev/inode并在读取前复核；VM、Node、Lease、Root、Secret、Runner、Host 身份也在运行时重新GET核验。Helm UID注解不是运行时来源。

`tests/check_render.py --verify-private-inputs --values <真实values文件> --agent-manifest <原Agent清单> --namespace <原VM namespace>` 只读验证本节点原私有目录/config SHA、报告及两artifact SHA、配置与 values 绑定、实际资源读取 socket 挂载。它不运行发布器、不访问集群、不认证报告内容。该命令须在所选原 worker 上执行；不得把离线渲染 fixture 当作这一步通过。

## 权限边界

发布器使用单独 ServiceAccount。VM、原Node、VM/Host Lease、原Runner来源CM和 VM-config Secret 只有指定名称的GET；现Host完整清单API需要跨namespace pods LIST。RBAC本身不能把该LIST限制为某个Node fieldSelector，固定程序仍按所选Node读有界清单。因此它是受信平台工作负载，不应将其SA赋予租户。

资格CM的CREATE只有本release namespace权限，没有update/patch/delete，也无VM/Node写、TokenReview、exec或Root控制凭据。**Kubernetes RBAC的CREATE不能用resourceNames限制到某个CM名称或标签。** 本namespace中其它CM的创建仍是这一SA的剩余权限；如平台需要更窄对象准入，必须另有实际生效的admission控制，不能靠模板注释声称已隔离。

hostPath只读不等于Unix socket API只读。这里只挂独立资源读取端点；服务端必须在dispatch前只允许owner发现和resource_state，其它管理action返回403。完整管理socket不能作为替代输入。发布器固定digest程序也只调用这两个读取动作。

## 使用与恢复

先用默认关闭配置 lint/render。只有真实镜像、原报告/目录、实际资源读取端点、原VM/Node/Runner/Host Lease信息全部齐备，才能填入显式 values，再运行私有输入前检和定向渲染断言。`runnerConfigMapNames`须包含从原Birth/State观察得到的Birth、State、Exit、StoppedPod精确名称；不授予ConfigMap LIST。报告派生的资格CM GET名由原report SHA确定。

Job backoffLimit=0、restartPolicy=Never，不自动重试未知CREATE；没有自动TTL清理。原CM已创建但回复丢失时，保持受保护对象及原日志，不能反复helm upgrade、换报告、换名称或删finalizer取绿。显式恢复的原UID只由可信私有配置的resume_claim_uid选择，须重新核验所有原事实。先归档Job结果及原未知，再由管理者决定下一步。

定向离线检查：`python3 charts/dsga-platform-qualifier/tests/check_render.py --output-dir <独立验收目录>`。测试只在临时文件中构造不可部署的offline输入，验证禁用、严格启用门、RBAC、调度、硬限及拒绝边界；它不签发资格、不运行kubectl或helm install，不把模型摘要当真实Source。
