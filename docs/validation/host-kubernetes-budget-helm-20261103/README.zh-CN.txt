接入AS a7显式Host Kubernetes容量预算，旧未配置策略模式保留。
Helm仅校验版本/身份/system保留/Profile摘要和Uint64字符串输入，不复制现场Node读取与防超卖计费业务算法；由AS生产入口继续严格核验。
实际12唯一输入case/12次helm渲染全通过，包含旧模式、超过2^53精确字符串及10非法拒绝。
重跑：python3 docs/validation/host-kubernetes-budget-helm-20261103/check.py --output 新空目录
镜像来自118构建，SSH离线OCI导入各节点k8s.io；本票不代表实际部署或Host内核物理认证。
