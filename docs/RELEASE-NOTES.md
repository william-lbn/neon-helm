# Neon Helm releases

## 0.1.30 candidate

Source `374a38b0f1e3b91456c8a9313a19ad3e2921feb3`, OpenAPI 0.22.0. Adds immutable operator SMTP configuration, branch required-email policy, real password recovery, session invalidation and a protected, retained local Mailpit receiver. Receiver is disabled by default, explicitly acknowledged, separately authenticated and internal; its reader credentials never enter API/Worker/Web/Auth mounts. Conditional readiness is verified by stack tools. See [mail contract](AUTH-EMAIL-RECOVERY.md). Runtime UI acceptance and release publication are still required.

[CNI recovery](DELIVERY-2026-10-14-ENVIRONMENT-RECOVERY.md) and the read-only `tools/audit-node-cni.mjs` help distinguish failing host executables from resource pressure. No database or upstream Neon source was changed by that incident repair.

## 0.1.29

Eight control images select source `be04cb41d4be029cd59bb1c291f02e683d26ce46`.
Linux CI `38517735954` passes all 14 jobs and 788 Go/PostgreSQL checks with zero failures/skips.
Scoped S3 core, signed chunk verification, UTF-8/fetch-owner pagination, range/presigned bytes,
rotation/revocation and account password/session UI have actual local acceptance.
[Exact receipt](ACCEPTANCE-2026-10-14-AUTH-S3.md) retains original failures and recovery.
Ten charts/15 tool checks/30 negative values pass. Defaults keep optional public services disabled;
lab cleartext needs explicit acknowledgement. Neon/autoscaling/PostgreSQL fork images are unchanged.
Full S3, email/OAuth/MFA, HA/DR, external fencing and trusted end-to-end TLS remain independent gates.

## 0.1.12

All ten charts select control source
`f0b63f5eed0fc412960b8b7dc7e8cda34abf916f`. Linux CI run `38156200281`
completed all thirteen jobs. Its downloaded Go/PostgreSQL receipt contains
610 passing checks, zero failures and zero skips. Seven public control images
have independently verified anonymous OCI provenance. Node pulls, ordered
upgrade, persistent identity audit and browser acceptance remain separate gates.
The Neon/autoscaling/PostgreSQL distribution is unchanged.

The restricted Functions SQL role now rejects column privilege leaks, grant
options, unsafe table kinds, sequence mutation and enabled write triggers. A
fresh authenticated runtime session must pass the same permission checks,
exact database/role/schema identity and transaction/GUC checks. This is a SQL
foundation: it does not prove physical branch placement, an immutable query
deadline, a customer Function invocation or protection from the database owner.
The deployment/invocation Driver and customer execution remain disabled.

An independent Worker now remains unready and retries initial controller lease
acquisition after transient database unavailability. It starts controllers only
after obtaining the actual lease. Loss of an already acquired leadership session
still drains and exits. This does not certify HA or cross-instance fencing.

Committed browser tests support explicit continuation of original accepted leaf
creation and reader creation Operations, preserving original IDs, rows and
failures. Only four fixed read-only SQL probes in explicit recovery may retry a
503/504 once; creating mutations and unknown SQL writes are never repeated.
The 0.1.11 browser matrix is historical evidence, not acceptance of these images.
Follow [UPGRADE.md](UPGRADE.md) and [TESTING.md](TESTING.md). This release does not
assert production admission or Neon feature parity.

## 0.1.11

All ten charts select control source
`932f5adbd9db5babce1ad05aa280cc34e452e193`. Linux CI run `38141439187`
completed all thirteen jobs. Seven public control images have independently
verified anonymous OCI provenance and twenty-one serial CRI pulls across the
three laboratory nodes. The Neon/autoscaling/PostgreSQL distribution is unchanged.

This increment adds private Functions Service/VM recovery and atomic metadata
publication primitives. Original object names, UIDs, complete runtime
configuration, immutable bootstrap receipts, live operation leases and a fresh
signed readiness observation are checked before publication. Dedicated Linux
Go/PostgreSQL quality passed 593 checks. Three actual MinIO/Kubernetes foundation
checks passed, including private Service recovery and server-side VM admission
dry-run. No Function execution VM was persisted by that acceptance. The Worker
deployment/invocation Driver and customer execution capability remain disabled.

Committed browser tests now support explicit original-fixture continuation for
timestamp restore, endpoint deletion and lifecycle recovery. An unknown SQL
write reply is resolved by reading the exact original rows before any conditional
write. An original failure is retained and a continuation is reported separately.

Linux Helm quality passed fifteen tool tests, ten charts and sixteen negative
cases; ten packages were built. Ordered live upgrade, persistent identity audit,
anonymous release consumption and the new distribution's UI regression are
separate acceptance gates. The prior 0.1.10 matrix is historical evidence and
does not qualify these new images. Follow [UPGRADE.md](UPGRADE.md) and
[TESTING.md](TESTING.md); this release does not assert production admission.

## 0.1.10

All ten charts select control source `dda5d34`, with forward migration 021 for
private immutable Functions bootstrap identity receipts. The receipt binds the
actual Secret UID, complete instance scope, content MAC and key version; it does
not contain credentials or authorize execution. Linux Go/PostgreSQL quality
passed 553 checks, and three independent actual MinIO/Kubernetes checks passed.
The deployment/invocation Driver is still disabled.

The Console now rejects truncated JSON/HTML success replies as identifiable
transient read failures. Accepted Operation polling can recover by reading the
same identity; it never repeats the creating mutation. A well formed foreign
Operation still fails. The native browser suite explicitly injects two 503
reads, truncated JSON and HTML, checking exactly one project creation. The Auth
suite can resume the original failed project, existing child and completed
Operation, retaining accounts/data and the original failure.

Linux source tests, registry verification, node pulls, ordered live upgrade and
browser results are separate gates. Historical passing UI counts do not qualify
this distribution. Migration 019 defines only definitions/deployments/instances,
not an invocation ledger or active route table; the Functions document corrects
that earlier overstatement. Neon/autoscaling/PostgreSQL sources remain unchanged.

## 0.1.9

All ten charts select control source `fbff1b0`, built by successful Linux CI
38123437193. The seven public images have verified anonymous Linux manifest,
configuration, platform, license and source provenance; old locks remain intact.
This increment adds forward migration 020, exact immutable Functions backing
receipts, conditional artifact storage and immutable environment recovery
primitives. Execution is still disabled until the actual deployment Driver,
branch SQL and invocation/browser acceptance are complete.

Compute suspend retry now handles an already absent VM only after bounded
observation of all owned Runner Pods and a second absent-VM read. A replacement
VM is preserved and causes the operation to fail safely. This is local recovery
and does not certify distributed scale-to-zero fencing. The original failing
Storage/child-branch UI fixture can be resumed without creating another project
or child branch. Neon/autoscaling/PostgreSQL fork source and images are unchanged.

Linux chart quality, node pulls, ordered live upgrade and UI results must each
be recorded independently. Publication is not live acceptance; historical
failures remain retained and are not relabeled as passing.

## 0.1.8

All ten charts select control source `f256408` from successful Linux CI
38103678537. OpenAPI 0.11.0 has 61 paths / 90 operations. This increment adds
branch-scoped Functions metadata/history APIs and a read-only React page,
forward migration 019 and a separately tested restricted SQL identity library.
Functions execution remains disabled pending the leased deployment Driver and
real SQL, deployment/invocation and browser acceptance.

PostgreSQL int32/int64 metadata is now converted correctly; generation ETags use
exact bigint formatting, including values beyond JavaScript's safe integer
range. Seven control images are locked by public CI provenance and anonymous
Linux registry checks. The separately accepted Function guest image is recorded
without installing it as an active service. Neon, autoscaling and PostgreSQL
data-plane sources/images are unchanged. See [Functions boundaries](FUNCTIONS.md).

This release requires the independent Linux chart, deployment and UI gates in
[TESTING.md](TESTING.md). Successful image publication does not constitute live
acceptance. Prior acceptance records remain version-specific historical evidence.

## 0.1.7

All ten charts select control source `0ba1732` from successful Linux CI
38058862506. Go API/Worker and React Console add independent Compute retirement,
forward migration 018, OpenAPI 0.10.1 (58 paths / 87 operations), retained branch
credentials and Writer recreation while surviving Readers keep their identity.
The new browser slice covers lost-202 idempotency, explicit service dependency
admission, normal Runner garbage collection and project recovery excluding
previously deleted Endpoints. All nine current-source serial Linux UI suites
passed 146 functional checks, with 23 separate original-operation recovery
checks. See [Compute lifecycle](COMPUTE-LIFECYCLE.md) and the [version acceptance](ACCEPTANCE-2026-10-10-COMPUTE-LIFECYCLE.md).

Seven image digests and their public source/CI provenance are immutable in
`locks/control-plane-0ba1732.json`. Existing source locks remain available for
rollback. Neon, autoscaling and PostgreSQL data-plane source/images are unchanged.
The superseded `85229d4` candidate exposed a multi-statement test fixture defect
and retained query password on an error. SQL setup now issues separate prepared
requests, successful/rejected submission clears its password, and public CI checks
all nine advertised live suites against their protected shell admission.
Live testing also exposed missing Worker Pod-list permission (403 after successful
VM retirement). This release adds a namespace-scoped read-only Worker observer
Role/Binding, preserves the split API's get-only Pod access and grants no Pod
mutation. Rendering gates cover both split and legacy combined profiles.

The eight-stage public-source upgrade preserved complete private overlays,
metadata backup, PVC/Secret/CA identities and rollback locks. All seven anonymous
registry checks and 21 actual three-node CRI pulls passed. Completed test Compute
runtime and owned logical quota are released; data and failed evidence remain.
The unknown CREATE DATABASE result required explicit OID/owner/marker-verified
operator repair; automatic adoption guards remain. A later three-node I/O outage
failed the original native Writer test; recovery used the original Operation and
a new full native attempt passed. These failures prevent a stability/SLO claim.
Functions and provider inference remain disabled. HA/DR, external fencing,
trusted whole-chain TLS, physical GC, fractional CPU and complete memory return
retain separate implementation/acceptance gates. No fork runtime source changed.

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
