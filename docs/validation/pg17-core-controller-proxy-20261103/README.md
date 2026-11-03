# Core Controller 与 SQLproxy 定向归档

这里包含两个可复跑的离线检查，以及与离线 fixture 明确分开的真实部署小票。

```sh
python3 docs/validation/pg17-core-controller-proxy-20261103/focused-render.py --output /tmp/neon-core-render-新目录
# 可分别运行：--group proxy 或 --group controller
```

需要 Python 3.12+、PyYAML、Helm 和本仓库 Git 历史中的基线 `552f6b8e33997f424e87573391b3f1892d68771a`。脚本从自身位置确定仓库，不依赖 `/data` 的输入、任何私有 values 或凭据文件，不调用 kubectl，不连接集群或下载镜像。输出目录必须不存在。

- **proxy**：外部真实 adapter 模式不要求未使用的 legacy Python 镜像；legacy 模式仍拒绝缺失镜像。负例只渲染，绝不启动 legacy compute。
- **controller**：默认 AST 与已提交基线相同；显式 hostname 只改变 Controller；schema 和模板均拒绝 116 或覆盖 pool/os/arch。模板拒绝检查仅修改输出目录内的负例 chart 副本，生产 schema 保留。

所有 fixture 镜像使用 `offline-render.invalid`，只含 Secret 引用，没有密码、token 或私钥。它们不是生产镜像或运行事实，渲染成功不能代替实际部署验收。

真实基础部署快照在 `实际部署小票.json`，包含 Linux `/data` 原验收路径和 SHA256、逐组件镜像/节点/硬限/就绪，以及 Controller 初次等待 DB 重启 1 次、Proxy 初次证书缺 CN 重启 5 次的原因。最终 Controller 已在 119，原 DB118/PS119/SK逐节点保持。实际 SQLproxy 要求证书 CN，最终使用真实 Service DNS 的 CN 与 SAN。

此票只覆盖本次基础组件/API/TLS接线；没有伪造 tenant、notify 回调、VM 或 PG 地址。完整 PG17 内存自动扩缩容 K8s 端到端和最新完整控制面对接均不能据此判定完成。
