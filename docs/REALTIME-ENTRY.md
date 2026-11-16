# Realtime 的发行入口合同

本次增量接续 Control Plane `fc7eedbbde3f15587cbb276aeb0898612e5d714f`
中 R59r2 已实测的 Realtime 接线。统一 Helm 旧版缺少该路由，客户端会落入
Console SPA；Control Plane 仓库自身 Chart 的 R44/R59r2 结果不覆盖这个发行包。

`realtime.enabled` 默认关闭。启用必须同时提供非零 `subscriptionLimit`、
`sourceLimit`、Backend 凭据和独立 Worker，并使用支持这些开关的已验收
Control Plane 镜像。API 与 Worker 接收同一参数和发行专用 `*-rtcred`
命名空间：API 仅可 get Secret，Worker 可 get/create/delete；不授予 list、
watch 或平台命名空间 Secret 权限。该命名空间由产品生命周期管理，卸载
前须完成原 Realtime source/query 的公开退役。

Console NGINX 将 `/realtime/v1/` 转发到同发行 API，保留 Bearer 和
`Last-Event-ID`，去除 Console Cookie、CSRF 和 Console ticket，隐藏上游
Set-Cookie。SSE 使用 HTTP/1.1、关闭响应缓冲和上游自动重试；中断后由客户端
携带原游标重连。Web Pod 的配置摘要覆盖实际挂载文本，开关变更会触发滚动。

## 正式域名与证书的配置来源

已有入口是 `networking.k8s.io/v1` Ingress，需由运营方提供：

- `ingress.className`：实际已安装且负责该入口的 IngressClass。
- `ingress.host`：Console 正式域名；DNS 必须解析到该控制器的实际入口。
- `ingress.tls[].hosts` 和 `secretName`：匹配域名的证书 Secret，由外部证书
  签发/续期流程供应。图表不创建私钥、不安装控制器，也不签发证书。
- `ingress.annotations`：相应控制器的 SSE 超时和缓冲配置，须沿真实控制器
  实测，不能仅凭内部 NGINX 的 `proxy_buffering off` 宣称外部链路通过。
- `api.cookieSecure=true`，以及 Auth/Functions 等模块各自的精确 public origin
  与独立域名约束。证书、入口和模块 origin 必须与实际运行配置一致。

2026-11-16 只读观察：117–119 集群没有 IngressClass/Ingress，Gateway API
资源类型不可用。本图表没有 Gateway/HTTPRoute 模板；不能将渲染成功、
ClusterIP、端口转发或实验 CA 等同于正式公网入口完成。选择 Gateway API
时还需明确控制器、CRD 版本及独立路由/证书合同。

## 独立验收与待办

`node --test tests/realtime-entry.test.mjs` 验证启停、两进程接线、最小 RBAC、
SSE 路由、配置滚动、Ingress 外部域名/证书引用及错误组合拒绝。

2026-11-16 的 `helm-realtime-entry-r2` 已使用准确的本轮 Helm 渲染文本，
在 119 顺序运行关闭/开启两个配置，实际读回同一原 Pod 的挂载文本和镜像。
每次一个三容器 Pod，内存上限合计 192 MiB，加 Host 开销为 208 MiB。
关闭时实测落入 SPA；开启时经实验 CA/SNI 的 TLS 边缘和原 Service，首事件
在 0.016 秒到达，限速响应在 8.022 秒完成。原游标/Bearer 透传、Console
身份隔离、Set-Cookie 隔离、HTTP/1.1、匿名 401 及错误 SNI 拒绝均通过。
两个原 Pod 和独立 Namespace 均已退役，Host sequence 533 无遗留 hold。

首轮测试的隔离 NetworkPolicy 错用了 `kube-dns` 默认标签，导致上游 DNS
解析失败；失败记录保留且原 Pod 已退役。第二轮只读绑定集群实际 `coredns`
Service 的 UID/selector 后通过，没有放宽网络规则。该合同只覆盖入口传输，
不替代 R44/R59r2 的真实 PG17/18 Writer、授权、撤销、跨副本重连和数据读回。

原始证据保存在 118：
`/data/neon-control-plane/runs/20261113-dsga403-c1/private/helm-realtime-entry-r2`。
48 个证据文件的清单摘要为
`26daa7ef5e7431003d5d7f9bbb31f27bc37b2ee76f4a994d67f54700e764dc65`。
Helm 3.17.3 下，116 项单元测试、15 个图表 lint/render、34 个拒绝组合及
源代码检查通过。首次本地全图表检查使用的旧 Helm 不支持 lint 的
`--kube-version`，已保留失败输出；没有删去该参数规避检查。

正式外部入口仍缺实际控制器、生产域名/DNS、可信证书及轮换、完整外部
负载均衡链路验收。本增量没有声称这些门槛通过，也没有同步 Storage、SSO、
Functions 等其他 Chart 差异。
