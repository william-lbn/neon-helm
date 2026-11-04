# Proxy 现有健康入口与可选 tracing 的明确配置

现场 TCP readiness 每十秒连接 PostgreSQL 入口后直接关闭，产生与探针同周期的 early EOF 警告。本次改用 Proxy 已有、实际 PodIP 可达的 HTTP 7001 /v1/status；保留周期、阈值、镜像和资源，不把健康探针当 SQL 或存储端到端通过。

Proxy 与 Compute 的库会默认启用 OTLP exporter，但本轮 profile 未配置真实接收后端，SDK 默认请求 localhost:4318 持续报错。本次为 Proxy 明确提供可选 tracing 配置，默认关闭 exporter；标准 OTEL_SDK_DISABLED=true 不影响 stderr/file 日志与 Vector metrics。启用时必须配置实际 HTTP(S) OTLP endpoint，缺失或非法形状在模板阶段拒绝；文档与渲染示例不代表已存在接收后端或 tracing 功能通过。Compute 的固定出生环境须通过后续 Guest plan/broker/System/Native 闭包更新，不能在线偷偷注入或借此冒称当前 Compute 已修复。

准确 live values 渲染26个非Hook对象，只有 Proxy Deployment 的 readiness 与新增 exporter 环境有变化；还原这两项后 Proxy 与实际对象结构相同，其余25对象完全相等。既有 MinIO 初始化 hook 与此修改无关，部署使用 --no-hooks 避免重跑。源码、渲染与验证 SHA 见 receipt.json；这里只归档准备与配置合同，部署后日志、实际 SQL 和内存动作必须独立验收。
