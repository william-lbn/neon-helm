# neonvm

Part of [Neon Helm](../../README.md). Version 0.1.0.

Read the [deployment](../../docs/DEPLOYMENT.md), [upgrade](../../docs/UPGRADE.md)
and [production gates](../../docs/PRODUCTION-GATES.md) before use. The explicit
lab profile is in [profiles/lab/neonvm.json](../../profiles/lab/neonvm.json).

All supported settings are documented inline in values.yaml and validated by
values.schema.json. Defaults intentionally require operator-supplied image locks
and Secret references. Do not use --skip-schema-validation.

Helm release names and namespaces come from stack/stack.json. Preserve their
identities during migration. CI lints, renders and packages this chart on Linux.
