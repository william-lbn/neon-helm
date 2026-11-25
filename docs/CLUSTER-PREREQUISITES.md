# 集群前置条件

平台提供 Kubernetes 管理凭据、主 CNI、当前 Controller 必需的网络附件 CRD、共享 cert-manager、Linux/amd64 KVM 节点、实际存储类、内网镜像仓库与节点拉取信任。启用额外网络时另需对应地址池和网络实现。普通 Pod 与 init container 必须具有明确内存硬限。范围和版本资格见[架构与边界](standard/架构与边界.zh-CN.md)。

历史细节可从 Git 历史追溯；当前部署以标准中文入口为准。
