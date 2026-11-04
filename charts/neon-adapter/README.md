# neon-adapter

Part of [Neon Helm](../../README.md). Version 0.1.0.

Read the [deployment](../../docs/DEPLOYMENT.md), [upgrade](../../docs/UPGRADE.md)
and [production gates](../../docs/PRODUCTION-GATES.md) before use. The explicit
lab profile is in [profiles/lab/neon-adapter.json](../../profiles/lab/neon-adapter.json).

All supported settings are documented inline in values.yaml and validated by
values.schema.json. Defaults intentionally require operator-supplied image locks
and Secret references. Do not use --skip-schema-validation.

Helm release names and namespaces come from stack/stack.json. Preserve their
identities during migration. CI lints, renders and packages this chart on Linux.

## managed实例的精确只读校验

`managedRuntimeRead.computes` 默认空列表，旧路由不增加权限。平台明确登记原Compute时，须成对给出 `serviceName: cp-16hex` 与 `configSecretName: 同名-config`；重复、跨实例配对及通配均拒绝。只给本namespace指定配置Secret和SQL Service的get，保留原Role其它规则；不读取业务凭据Secret、controlSigningSeed、Node，也不授list或写权限。此权限用于新版本managed路由核验真实VM/config/Service绑定，不代表原Native初始化、Proxy SQL或内存资格已经通过。实际路由注册仍须先取得原NativeProbe成功，缺失或Unknown必须拒绝。
