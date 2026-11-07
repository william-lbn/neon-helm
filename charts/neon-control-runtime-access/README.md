# 控制面自动供应身份

仅部署SA/RBAC，无工作负载、预算、Token Secret或新执行器。用于Mac受限身份连接，以及后续同一控制面发行；平台namespace必须neon-control-*且与业务namespace分开。

API在业务namespace保留新建凭据并只读运行事实；Worker复用原创建Operation建立每VM Runner/Qualifier角色，保留Kubernetes原生防权限提升检查，不授bind/escalate。Qualifier只读117/118/119节点及实际Pod库存；原细粒度VM/配置/资格CM权由Worker绑定。Host lease只读精确三节点对象，平台策略CM只有Worker可写、原Agent另有get-only权限。

Worker具有业务namespace的CM更新权，是为原每VM State角色的合法委派；生产代码不把它用作预算写入口。跨namespace Pod list和kube-system pods/proxy GET的RBAC不能限定fieldSelector/动态Pod名，平台HTTP客户端仍固定原DaemonSet UID、节点、Pod身份、端口与GET。普通用户没有这些SA，不向浏览器传Token。

2026-11-08：21个权限对象渲染与真实server dry-run通过；master节点、错误Host对象及跨namespaceHost拒绝通过。日志在118 /data/neon-control-plane/runs/20261107-控制面重新启动/runtime-access-3b9106d1。此项不代表真实新项目/内存策略验收。
