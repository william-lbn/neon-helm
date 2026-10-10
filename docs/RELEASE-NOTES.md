# Neon Helm releases

## 0.1.7 candidate

All ten charts select control source `0ba1732` from successful Linux CI
38058862506. Go API/Worker and React Console add independent Compute retirement,
forward migration 018, OpenAPI 0.10.1 (58 paths / 87 operations), retained branch
credentials and Writer recreation while surviving Readers keep their identity.
The new browser slice covers lost-202 idempotency, explicit service dependency
admission, normal Runner garbage collection and project recovery excluding
previously deleted Endpoints. Runtime acceptance is pending; source and CI
success alone do not qualify this feature. See [Compute lifecycle](COMPUTE-LIFECYCLE.md).

Seven image digests and their public source/CI provenance are immutable in
`locks/control-plane-0ba1732.json`. Existing source locks remain available for
rollback. Neon, autoscaling and PostgreSQL data-plane source/images are unchanged.
The superseded `85229d4` candidate exposed a multi-statement test fixture defect
and retained query password on an error. SQL setup now issues separate prepared
requests, successful/rejected submission clears its password, and public CI checks
all nine advertised live suites against their protected shell admission.

## 0.1.6

Branch Object Storage REST v1 adds a real Go manifest/immutable-blob Driver,
React bucket/file UI, migration 017 and 13 new operations (OpenAPI 0.10.0,
58 paths / 86 operations). Native child timelines inherit file directories;
child writes and logical deletion preserve parent bytes. Private/public read,
SHA-256 integrity, conditional writes, signed downloads, manual zero/cold wake
and retained recovery are implemented. External S3 wire compatibility remains
false; multipart, unified application storage scopes and physical GC are absent.

All ten charts are 0.1.6; seven control images lock source `7162449` from successful
Linux CI 37950048773. Dedicated product bucket/account/bootstrap, strict schemas,
real IAM verification and edge download routes are included. Product policy
cannot access database buckets; API/Worker receive no root credentials. Failed
hook OOM and ownership defects were corrected with preserved original records
and exact terminal UID/RV retirement, without weakening general adoption guards.
Catalog completion clears only submitted fields, preserving another form edited
during directory refresh. Exact original-project restore recovery passed 13
checks, including the delayed-refresh regression, timestamp/LSN and cold wake.

The actual eight-stage upgrade preserved complete values, metadata backups,
PVCs/Secrets and certificate identities. Linux 367 Go checks, Web, Auth/TLS,
15 Node/16 negative Helm checks, anonymous registry and 21 all-node pulls passed.
Eight current-source UI slices pass 126 functional checks; Object Storage has
19 checks and the original failed object fixture has four separate recovery
checks. The native slice's initial cleanup observer failed; a later same-UID
read-only observation confirmed normal retirement. See the acceptance report for
the serial UI matrix and original hardware-related failures. Compute/service runtime
is released; data, historical evidence and rollback locks are retained.

No Neon/autoscaling/PostgreSQL fork runtime source was changed. Functions and AI
inference are not implemented; HA/DR, external fencing, trusted whole-chain TLS,
shared-host stability and other production gates remain open.

## 0.1.5

Branch Managed Auth adds the leased Go Driver, immutable generation-scoped
Secrets, maintained Better Auth TypeScript runtime, public branch relay,
restricted PostgreSQL schema/role, React Console and Data API JWT/RLS
integration. OpenAPI 0.9.0 describes 52 paths / 73 operations; migration 016
adds durable Auth state and an enabled-instance quota. Parent Timeline cloning
inherits accounts but resets child sessions/JWKS; disable/re-enable retains
users. HTTP Console remains an explicit laboratory exception.

The unified stack locks seven public images from control source
`2dcd7d2dbac6edac9d7f2190ebf8c67db90ebb97`, selecting GHCR mirrors of the same
CI manifests published to Docker Hub. Source checks reject mixed revisions,
missing public verification and profile/adapter drift. Auth SQL verifies the
explicit Proxy CA and certificate identity; real pg STARTTLS regression
rejects wrong names and unknown CA. Standard public JWK omission of optional
`use` is accepted without permitting private keys or unsafe algorithms.

All ten chart packages share version 0.1.5. The accepted eight-stage upgrade
preserves complete values, external Secrets and PVC bindings. Linux Go/PG,
Auth, Web, Helm, anonymous registry and all-node pull gates passed. The new
Managed Auth UI passes 23 real checks including account/session/JWT branch
isolation, RLS and manual/automatic zero/cold wake. See the versioned acceptance
report for current-image regressions and the retained failed attempts.

Terminal test resources are archived before UID/resourceVersion deletion;
owned services/Computes stop through product APIs. A full logical project quota
is handled by proven owned retained deletion, without raising quota or dropping
data. The observed shared-host etcd fsync stalls remain unresolved production
gates even after successful feature reruns. No forked Neon/autoscaling/PG source
was changed; Functions, product Object Storage, AI inference and the other
independent production gates remain explicitly unqualified/unimplemented.

## 0.1.4

Go API/Worker and React Console add protected project/leaf-branch retained
deletion, dependency admission, UID/resourceVersion Compute retirement,
seven-day project recovery and tombstones. OpenAPI 0.8.0 describes 50 paths
and 69 operations; migrations 014–015 preserve existing metadata and data.
Migration 015 keeps failed creation/recovery retryable under the original
Operation, while denying unrelated work on deleted resources. The recovery
dialog supports an explicit same-Operation retry after terminal failure.
Real Linux UI exercises two independent read replicas, read-only enforcement,
WAL visibility, original-selector cold wake, active Data API retirement and
permanent Backend credential revocation. Physical Timeline/WAL/object purge,
distributed connection fencing and production HA/TLS remain separate gates.

All ten chart packages share version 0.1.4. Upgrades preserve complete current
values, PVCs, Secrets and metadata. Backup export has a unique PGAPPNAME and
remote/idle transaction deadlines so abandoned pg_dump cannot indefinitely
block migrations; timeout output remains a private partial file and blocks
rollout. Linux tests cover the timeout and retained partial evidence.

## 0.1.3

The Proxy/Storage adapter is a compiled Go process from the same source revision
as the API/Worker and gateways. It uses a non-root scratch image, projected
rotatable credentials, dependency readiness, bounded wakes and ownership checks.
The chart preserves Service/selector, external routes and notification receipts;
no interpreter/source ConfigMap is mounted. A narrowly scoped Service proxy read
validates native Controller placement. All ten packages share version 0.1.3.

The lab deployment can retire the unused legacy proxy-api and compute-resizer
after preserving complete values and proving Proxy already targets the dynamic
adapter and the legacy compute Deployment has zero replicas. These optional
legacy tools remain disabled compatibility paths in source. This migration is
separate from distributed connection ledgers, external fencing, full placement
reconfiguration, deletion/GC and production HA/TLS. Those gates remain open.

Maintenance pg_dump now streams into an exclusive private partial file, then
hashes/renames only after successful completion. This fixes the observed 32 MiB
output-buffer failure without dropping backups or raising an in-memory limit.
Linux tests cover large output, failed dumps and preservation of prior attempts.

## 0.1.2

Historical PostgreSQL recovery to a **new branch** is implemented in the Go
control API/Worker and React Console. Timestamp/LSN resolution uses the native
Pageserver retention boundary and LSN lease before accepting intent. Worker
retry retains the resolved point and verifies exact timeline ancestry. Current
catalog intents are not projected into historical data. Migration 013 stores
restore provenance. OpenAPI 0.7.0 exposes 46 paths and 63 operations.

The chart adds `api.pitrEnabled` (default false), shared by API and Worker;
enabling it without resource creation is rejected. The locked lab profile opts
in after real Linux restore tests. Ten chart packages share version 0.1.2;
forked Neon/PostgreSQL/autoscaling sources and their 46-image lock are unchanged.
The acceptance report records exact control-image source/digests and fresh
regression results. In-place restore, Time Travel Assist, full Backend recovery,
deletion/GC, HA/DR, fencing, fractional CPU, full RAM downscale and trusted TLS
retain independent implementation or qualification gates.

A real published-image UI test exposed a missed-404 race during suspend/cold
wake. The Worker now observes deletion of the original VM generation: an owned
successor UID is accepted without mutating it, and missing/foreign identities
fail. The Linux Go gate includes this matrix; the live restore suite requires
the original suspend Operation to succeed after the cold wake. This correction
does not claim full cross-instance fencing.

## 0.1.1

The control product is locked to `f90c9370db583e71796c4c6ad44e51c6ea354f43`:
Console invitations, invited registration, existing-account acceptance and
permission revocation, bounded accepted-Operation observation recovery and
Linux UI transient-read fault injection. All five control images have public Docker Hub digests;
API/Worker/Web and native Data API use this one source revision. See the release
acceptance report for Linux CI, real UI and live manifest/provenance checks.

The optional static Compute chart adds `compute.enabled=false`. Only its VM is
removed; Service identity, external config and Neon persistent data are retained.
The default stack still creates no static Compute. A Helm gate verifies
retirement renders zero VMs and retains one Service. This does not implement
project deletion, garbage collection or managed Endpoint fencing.

Empty custom-resource lookup now preserves list semantics after the last VM
is retired. The final zero-resource audit requires removal of both managed
VMs and their runner Pods. Resource retirement/incident guidance preserves
failed attempts, database data, rollback values and external credentials.

## 0.1.0

Initial independent chart repository. Ten charts unify the Neon data plane,
NeonVM/autoscaling, metadata/Adapter and Go API/Worker/TypeScript Console.
Eight default releases have deterministic deployment order; dynamic Computes
and native branch Data API remain control-product owned. Images and sources are
locked; Secret state is external; PVCs are retained; Linux CI checks rendering,
schemas, ownership safety and packaging. See deployment and upgrade runbooks.

This release is a laboratory candidate. See PRODUCTION-GATES.md for unfinished
features and unqualified HA/DR, fencing, PITR, memory/fractional CPU and TLS.
