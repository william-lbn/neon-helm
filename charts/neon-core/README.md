# neon-core

Part of [Neon Helm](../../README.md). Version 0.1.0.

Read the [deployment](../../docs/DEPLOYMENT.md), [upgrade](../../docs/UPGRADE.md)
and [production gates](../../docs/PRODUCTION-GATES.md) before use. The explicit
lab profile is in [profiles/lab/neon-core.json](../../profiles/lab/neon-core.json).

All supported settings are documented inline in values.yaml and validated by
values.schema.json. Defaults intentionally require operator-supplied image locks
and Secret references. Do not use --skip-schema-validation.

Helm release names and namespaces come from stack/stack.json. Preserve their
identities during migration. CI lints, renders and packages this chart on Linux.

## PG18 core SQL candidate

The PG18 distribution uses `compute.buildProfile: dsga-core` with
`compute.mode: public`. Its generated SQL configuration preloads only `neon`
and `pg_stat_statements`, removes settings for absent third-party extensions,
and does not add `ulid` during initialization. The `full` profile preserves the
existing PG14–17 extension configuration. PG18/full and dsga-core with another
major or wrapper mode are rejected.

Release overlays keep Compute disabled until the operator supplies real tenant,
timeline, auth Secret and pinned configuration-init image inputs. This public
SQL path does not qualify the separate managed VM/physical-memory-release path.
See [DSGA release](../../docs/DSGA-RELEASE.md) for the verified scope.
