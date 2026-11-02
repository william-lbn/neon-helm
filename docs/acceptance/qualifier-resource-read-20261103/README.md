# 资格发布器与资源读取通道Helm接线

新增独立dsga-platform-qualifier chart，默认关闭，必须显式选择不可变镜像digest、原VM/Node/Lease/Runner来源及root保护的原输入。一次性Job通过autoscale-scheduler按正hard memory limit入Host账本，nodeSelector限定原worker；不用nodeName绕过分配。不监听宿主网络，不自动创建/chown私有目录，不带认证默认值。

Agent chart新增可选resourceReadSocket配置/Schema/独立Directory hostPath，实际JSON配置路径与mountPath/filename一致。Agent可写创建socket；资格Job只读挂同原目录/inode。只有新Agent的服务端resource_state白名单提供动作限制，readOnly挂载本身不限制Unix管理API。完整管理socket不共享。两个功能默认关闭。

独立SA仅读原VM/Secret/Pod/Node/Lease/Runner CM，资格CM在本namespace create/get；不授予VM/Node更新、Root执行或删除。Kube RBAC不能按resourceNames限制CREATE，也不强制全namespace Pod List的Node fieldSelector，两项真实边界已公开，不能冒称更窄。资格内容及运行时原身份仍由固定CLI/原消费者核验。

验证：新chart30项lint/render/正负断言通过；现Agent通道10项通过，其中2正例逐字段核ConfigMap/真实Directory挂载，8负例核确切拒绝原因，避免因无关schema或兼容配置失败取绿。旧工具参数/fixture失败全部保留不累计覆盖。测试预算及Lease仅为明确render-only输入，不用于认证。

真实Source/报告/Host硬预算尚未具备，私有输入与已部署Agent socket的现场前检没有执行；未创建任何集群对象、没有签发资格、没有移动最终发行镜像锁。尚需Linux G5全部门槛及实际平台来源后，冻结全组件镜像再在117/118/119以本仓库Helm真实回归。命令与前检说明见新chart中文README、tests/check_render.py和tools/test-agent-resource-read-socket.py，摘要见receipt.json。
