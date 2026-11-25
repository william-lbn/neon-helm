# data-api-gateway

可选独立 Data API 网关，不属于核心数据库验收。属于 [Neon Helm](../../README.md)。

当前完整产品使用[标准部署流程](../../docs/standard/README.zh-CN.md)及显式生成的站点 values；Chart 版本以 Chart.yaml 为准。配置由 values.schema.json 校验，不跳过校验。镜像按摘要锁定，凭据通过 Secret 引用，不在默认值中放现场密码、地址或 UID。

Helm 管理常驻对象；业务运行时及原生预算由对应所有者管理。升级保持原 release 身份，未知结果按[原操作接续](../../docs/standard/故障与接续.zh-CN.md)处理。CI 负责源码、渲染和打包检查，不能替代真实业务验收。
