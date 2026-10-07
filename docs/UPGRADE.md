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

Installations upgrading from before 0.1.3 must preserve the historical
`proxy.legacyApiEnabled=true` overlay until ownership and route checks in
section 6 have passed. The accepted current lab uses `false`; its completed
legacy proxy/resizer workloads have been retired after retaining their records.
Fresh installs also default to false and create no permanently running test
Compute. Retained static VM `vm-neon-compute` is excluded from the default stack.

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

## 5. Historical branch migration and recovery

Version 0.1.2 requires the control product's forward migration 013. It adds
historical provenance on `branches`; existing branches default to `current`.
Quiesce API/Worker using the stack maintenance flow and retain the metadata
dump and external Secret state. Do not reverse the migration with Helm rollback.

Do not run a pre-restore Worker against pending historical operations: the
older reconciler cannot enforce their fixed LSN lease/step contract. Drain or
recover accepted operations with compatible code before changing versions.
Keep exact source/digests and observe original Operation IDs after a failure.
The `api.pitrEnabled` flag is shared by API and Worker; the production default
remains false. Enable the narrow new-branch capability only after native
retention API compatibility and release-specific real UI acceptance.

Compute suspension is identified by the deleted VM UID. An owned same-name
cold-wake successor proves the old generation is gone; it must survive the
old operation. Never force-delete the new UID to make a pending operation
finish. This correction is distinct from full distributed admission fencing.

## 6. Python adapter to compiled Go (0.1.3)

Save all eight complete Helm values and manifests, external route/receipt state,
Secret/PVC identities and SQL baseline in the protected attempt directory. Keep
0.1.2 rollback packages. The new image is `control-adapter` from the source locked
in `locks/adapter.json`; never use a general Python image with the new template.
Keep `fullnameOverride`, Service name/selector, routes and notification resource
names. The new container UID/GID and projected-Secret fsGroup are 65532.

Upgrade as a maintenance operation: new adapter uses Recreate and one replica.
Its readiness reads external state; install prerequisites from DEPLOYMENT.md
before a fresh cluster install. RBAC includes GET on the exact Controller
`http:storage-controller:1234` Service proxy for authoritative placement checks.
Projected proxy/hook token keys are distinct, read each request and preserved.
The old adapter code ConfigMap is removed by Helm; mutable receipt ConfigMap,
routes Secret, database PVCs and objects are never chart-managed replacements.

If retiring unused legacy Python proxy/resizer, first verify the live Proxy's
authEndpoint already points to `neon-control-adapter:8080/cplane/`, the retained
legacy Deployment compute has zero replicas, and no operator workflow depends
on those services. Set `proxy.legacyApiEnabled=false` and
`computeResize.enabled=false` in the **complete preserved core overlay**. Do not
replace it with the clean-install profile: existing tenant/config/storage values
must survive. Archive removed manifests/logs and retain prior values for rollback.

The Go version compares native receipt payloads canonically, preserving idempotent
replay of Python-era records without resetting hashes or history. It refuses
unsupported storage layouts/reconfigurations. After rollout verify runtime=go,
no active legacy Python Pods, native Proxy SQL/cold wake, UI project/branch/Reader,
historical restore, Data API, invitations and authorization. Retain all failed
attempts. Process-local wake locks are not distributed suspend/wake fencing.

## 7. Large metadata backup and failed-attempt preservation

The maintenance tool streams pg_dump stdout directly into a mode-0600 exclusive
`metadata-before.partial.private.sql`, outside source in the protected attempt.
It fsyncs and closes the file; only a successful, nonempty dump is hashed in
bounded chunks and renamed `metadata-before.private.sql`. Failed/timeout output
remains partial evidence and blocks the upgrade before stopping controllers.
Never treat a partial file as a complete backup or overwrite an earlier attempt.

This fixes a real pre-rollout failure where metadata exceeded Node's 32 MiB
capture buffer (about 35 MB on the lab). Linux regression tests cover output
above that boundary, failed exit preservation and exclusive destination behavior.
A successful dump receipt records bytes/SHA256 and `restoreTested:false`;
backup capture does not certify full DR or a restore rehearsal.

Both sides of the export now have deadlines: the remote `pg_dump` is wrapped
in GNU `timeout` (150 seconds, followed by a 10-second kill grace), while the
local kubectl deadline is 180 seconds. The pinned PostgreSQL image must provide
GNU `timeout`; absence fails the backup before rollout. Each export has a unique
`PGAPPNAME` in its receipt and a PostgreSQL `idle_in_transaction_session_timeout`
of 60 seconds. A lost client cannot retain an idle export transaction indefinitely.
Slow exports fail with a retained partial file; never label them a valid backup.

If a migration waits, inspect `pg_stat_activity`, `pg_blocking_pids` and
`pg_locks` before changing anything. On 2026-10-07 a previous failed export left
an idle `pg_dump` holding metadata table locks for over two hours; this blocked
migration 014 even though all nodes were Ready and I/O PSI was zero. Retirement
was limited to the identified idle export by PID **and backend_start**, after
preserving lock evidence and verifying a new complete backup. Do not terminate
unidentified sessions or business transactions. Record failed Helm status,
then retry the reviewed upgrade; do not reset metadata or drop migrations.

## 8. Retained deletion and recovery (0.1.4)

Control-plane migrations 014–015 are forward-only and loaded by the compiled
API. Keep migration 014 immutable; 015 replaces the admission function to permit
retry of the original failed creation/recovery without allowing unrelated work
on deleted resources. Chart version 0.1.4 pins the six control images to one
verified source commit; component chart appVersion identifies runtime 0.8.1.

After backup and reviewed rollout, verify 15 applied control migrations,
independent API/Worker/Web readiness, preserved PVC/Secret UIDs and zero
unexpected Compute. Run the lifecycle UI suite on a fresh owned fixture: root
and child protection, active leaf retirement, two real read replicas, project
retirement/recovery, original SQL credentials/data, Data API disabled after
recovery and old Backend tokens permanently revoked. Preserve every Operation
and failure report; only retire completed runtime resources.

Project recovery restores the original live resource identities within seven
days and keeps Computes suspended. Previously deleted branches remain deleted.
Native timelines, WAL, objects, Secrets and evidence remain retained; physical
GC is held. Do not implement purge or reduce retention as an upgrade shortcut.
Recovery of a failed operation uses the original Operation retry endpoint and
UI control, rather than another delete/create request. The explicit operator
fault procedure lives in the pinned control source's docs/TESTING.md.

Helm rollback does not downgrade PostgreSQL migrations or restore a full storage
backup. Older control images do not implement these lifecycle/retry contracts;
prefer a reviewed forward repair. Data restoration requires a separately tested
recovery plan. These checks do not certify HA, distributed fencing or full DR.
