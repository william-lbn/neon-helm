# Upgrade, ownership and recovery

## 1. Before an existing cluster upgrade

1. Reserve a maintenance window and stop creating projects/Endpoints.
2. Suspend only owned managed Computes through the control API; retain projects,
   timelines, route state and test records. Do not touch unowned legacy VMs.
3. Verify all Operations have finished. Save the release revisions, complete
   `helm get values -a`, manifests, PVC UIDs/bindings and actual image IDs into
   an encrypted/private attempt directory. Do not commit these exports.
4. Back up metadata with `pg_dump`, controller metadata separately, routes,
   credentials, idempotency key, pepper versions and certificate keys. Retain
   WAL/object-store data and record storage snapshots according to the provider.
5. Test restore on an isolated target. A dump existing on disk is not a verified
   restore or a complete data-plane backup.
6. Render and review every change before applying. Reuse exact tenant/timeline,
   Pageserver node IDs, service names, Secret references and storage classes.

The maintenance tool saves metadata and external state privately, quiesces API
and Worker, checks again for admitted work, upgrades in dependency order, then
restores the original API/Worker replica counts even after failure. Do not allow
new writes during this interval. It is a maintenance tool, not an HA coordinator.

## 2. Compatibility overlays

Existing releases map to their protected full values:

| Old release | New chart / overlay file |
|---|---|
| neon-lab | neon-core.json |
| managed-pageserver | neon-managed-pageserver.json |
| neonvm | neonvm.json |
| neon-autoscaler | neon-autoscaler.json |
| neon-control-plane | neon-control-plane.json |
| neon-compute-management-gateway | compute-management-gateway.json |

The current lab keeps `proxy.legacyApiEnabled=true` because its historical
`compute`, `compute-resizer`, `proxy-api` objects remain release-owned. Fresh
installs default to false and create no permanently running test Compute.
Retained static VM `vm-neon-compute` is excluded from the default stack.

### Retire a finished static lab Compute

This optional chart owns a historical test VM; Go's managed `cp-*` Endpoint
suspend action does not manage imported static VMs. Save its full release values,
manifest, config/SSH Secrets, VM identity, logs and catalog IDs privately. Confirm
no client work, stop admissions during a maintenance window, and gracefully stop
PostgreSQL/compute_ctl. Verify WAL flush/shutdown evidence before removing runtime.
Keep tenant/timeline/storage and project records.

With reviewed complete values at `/secure/static-compute-values.json`:

```bash
helm upgrade vm-neon-compute ./charts/neon-compute -n neon --reset-values \
  -f /secure/static-compute-values.json --set compute.enabled=false \
  --history-max 20 --wait --timeout 180s
kubectl -n neon get virtualmachines vm-neon-compute
kubectl -n neon get service vm-neon-compute
```

The first `get` must return NotFound, the second the retained Service. Save a
render before the upgrade. This removes the chart-owned VM and its transient
runner, not the external Secret or Neon data. Repeat deployment from those same
reviewed values with `compute.enabled=true`; do not invent a new tenant/timeline.
An imported Endpoint has no automatic cold-wake guarantee while retired. This
laboratory procedure is not a cross-instance production scale-to-zero fence.

The historical VM controller uses `cache.no-flush=on`. The new chart default
is `off`; an existing deployment must preserve its current setting with
`controller.qemuDiskCacheSettings` and `controller.labAcknowledged=true` until
a separate flush/durability migration is tested. Neither setting proves DR.

## 3. Safe adoption of previously scripted resources

Only the following existing names can be adopted, and only if currently unowned:
`neon-control-v2-db`, `neon-control-adapter`, `neon-control-adapter-code`,
`pageserver-managed-config`, `pageserver-managed-cache`, `neon-proxy-public`.
The kinds are checked against rendered chart resources. Selectors must match;
PVCs must be Bound with identical access modes/class/capacity; ConfigMap content
must match. Helm ownership belonging to another release is rejected.

The tool records the original object and UID, then uses a JSON Patch containing
UID/resourceVersion tests before adding Helm ownership metadata. It never uses
`--take-ownership` or `--force`. Mutable route/credential Secrets, notification
state, Namespaces and CRDs are never adopted by this mechanism.

```bash
node tools/stack.mjs apply --maintenance-window --adopt-unowned \
  --overlay-dir /secure/neon-compatibility --output /secure/neon-upgrade-001
```

Do not rerun into the same attempt directory. Inspect the failure and create a
new attempt. An earlier stage may have succeeded; the next attempt reconciles
it with the same desired values. Adoption metadata changes can be inspected
and restored from the saved object before a release first claims it.

## 4. CRDs, storage and rollback

Helm installs `crds/` before templates, skips existing CRDs and does not upgrade
or delete them automatically. This is the [official Helm CRD lifecycle](https://helm.sh/docs/chart_best_practices/custom_resource_definitions/).
The imported NeonVM schema predates the runtime image revision; preserve that
provenance. Before a schema upgrade, export CRDs and all existing CRs, compare
structural schema/pruning/conversion, prove every CR validates, test a disposable
cluster and explicitly apply only the reviewed schema. Restarting a controller
is not a CRD migration. The normal stack upgrade does not perform it.

All owned PVC templates carry `helm.sh/resource-policy: keep`. `uninstall` is
not a data deletion operation; resources retained after uninstall require a
later ownership recovery plan. This annotation protects Helm deletion only,
not manual deletion or storage failure. Dynamic Compute root disks are ephemeral
runtime; durable database data belongs to WAL/Pageserver/object storage.

Rollback a failed stateless image only after checking schema/config compatibility.
Restore database migrations and external route side effects with a planned
recovery; `helm rollback` cannot reverse them. Retain controller DB, metadata DB,
Safekeeper WAL and object-store consistency as one recovery set. Real HA/DR and
PITR remain separately unqualified; never claim the automatic backups certify
these features.
