# Seven-image Managed Auth and environment acceptance — 2026-10-08

## 1. Release identity and conclusion

This report qualifies the laboratory feature slices explicitly listed below.
It does **not** certify complete Neon SaaS functionality, independent HA/DR,
distributed suspend fencing or trusted transport across every component.

Control runtime source is `2dcd7d2dbac6edac9d7f2190ebf8c67db90ebb97`.
The selected [seven-image lock](../locks/control-plane-2dcd7d2.json) records
the exact OCI references, platform/config digests, public anonymous verification
and source labels. [Control CI 37781056916](https://github.com/william-lbn/control-plane/actions/runs/37781056916)
passed all five quality gates and seven image publications. Docker Hub and
public GHCR are mirrors of that publication; this stack selects GHCR for the
seven control images, while foundation data-plane images retain their Docker
Hub digests. The `f207860` and `64517ab` locks are retained superseded failures,
not current deployment candidates.

The unified stack uses ten 0.1.5 charts and eight ordered releases. Neon,
autoscaling and PG16 source/image pins remain unchanged; no fork data-plane
source modification was required by this increment. See SOURCE-PROVENANCE.md
for exact source provenance and ARCHITECTURE.md for component ownership.

## 2. Quality, rollout and product tests

| Gate | Evidence |
| --- | --- |
| Go + real PostgreSQL | 354 pass, zero fail/skip; gofmt, vet, race, migrations, Auth isolation, RLS and OpenAPI 0.9.0 |
| Auth runtime | 5 Node/library/PG/driver TLS tests plus 1 native TLS check; pinned Better Auth 1.7.7 / pg 8.23.1 / Node 24, audit zero vulnerabilities |
| React Console | 13 tests, strict TypeScript, format and build |
| Canonical charts | Three source charts lint/render and negative gates |
| Unified Helm | 13 Node contracts, all ten lint/render/package gates, 13 rejection cases |
| Public images | Seven anonymous Linux manifest/config/source/platform checks; all 21 node/component pulls matched the exact CRI digests |
| Rollout | Eight ordered Helm stages, complete old values/manifests and bounded streamed metadata backup preserved; PVC/Secret and installed manifest audit passed |
| Managed Auth UI | 23 checks, Job `publication-ui-20261008135401`, Pod UID `7fa4afe8-8d27-4c6c-bfb9-d0c344e8489d`; all owned VM/runner resources zero afterwards |
| Historical restore UI | Job `publication-ui-20261008135909`; actual timestamp/LSN, retained data/catalog isolation and controlled polling outage passed |
| Native UI | 14 checks, `publication-ui-20261008141717`, Worker epoch 67→68 |
| Data API UI | 21 checks, `publication-ui-20261008141843`, real RLS, rotation and automatic zero/cold wake |
| Console invitations | 6 checks, `publication-ui-20261008142302` |
| Application credentials | 8 checks, `publication-ui-20261008142320`; no inference acceptance claim |
| Existing reader recovery | 5 checks, `publication-ui-20261008144145`, original Operation/Endpoint, attempts 2→3 |
| Lifecycle/two readers | 23 checks, `publication-ui-20261008144311`, two readers/WAL/zero, retained deletion/recovery, Data API and revoked credentials |

The seven main current-image suites passed **106 checks**, plus **five**
existing-reader recovery checks. Every suite ended with zero managed VM/runner
resources. The controlled lifecycle recovery injection advanced Worker epoch
71→72 and the modal retried the original Operation; it is not a storage disaster
or HA qualification. Failed attempts remain separate.

Managed Auth covers real UI registration/login/logout, persisted branch users
and sessions, fresh Ed25519 JWT/JWKS, dependency admission, PostgREST/FORCE RLS,
inherited password accounts with new child session/key domains, bidirectional
cross-branch JWT denial, manual and automatic 1→0, CORS preflight without wake,
real login 0→1 and re-enable retaining users. All writes start in the React
Console; protocol and read-only API assertions complement the UI. Runtime
services are stopped after acceptance; SQL and private fixtures are retained.
The [detailed Auth contract](https://github.com/william-lbn/control-plane/blob/2dcd7d2dbac6edac9d7f2190ebf8c67db90ebb97/docs/MANAGED-AUTH.md)
defines exact schemas, interfaces, cookie/JWT policy and manual reproduction.

## 3. Diagnosed failures and recovery

### Actual driver TLS and standards compatibility

The first Auth UI failed on unknown Proxy CA, the second on `pg` overriding
the configured TLS server name with TCP Service DNS. Fixes project only the
public CA and use Node's standard certificate identity check for the explicit
deployment name while keeping certificate-chain rejection enabled. A real
`pg.Client` STARTTLS/startup test rejects wrong names and unknown CA; an actual
runtime SELECT 1 probe preceded the accepted real Neon UI. No `--insecure`,
unknown trust callback or Neon source patch was used.

Better Auth's Ed25519 JWK omits optional `use`. Data API now accepts omission
while rejecting null/empty/non-signature values, private keys and unsupported
algorithms. The negative cross-branch test uses refreshed unexpired JWTs, so
expiration cannot falsely satisfy isolation. Failed UI cleanup is bounded and
retains original operation/ETag/idempotency evidence and user data.

### Registry egress and startup state

Boot-time CNI/readiness events were distinguished from current health. The
post-upgrade all-namespace inventory had **zero active workload faults**.
Current admission snapshots showed 9–10 GiB available memory per node and no
material I/O PSI; the system disk was approximately 490 GiB total / 404 GiB
available. These samples do not certify the shared physical disk or CNI over
long periods, but do not support disk exhaustion as the observed pull cause.

Linux 7890 forwards to Windows 11121, which timed out while local Windows
11119 could serve HTTPS. Direct GHCR metadata succeeded but some CDN layers
stalled. The accepted 21 pulls used a temporary SSH loopback forward through
the already working proxy and `ctr ... images pull --local` with serial
downloads, TLS checks and exact CRI digest verification. Clearing CLI proxy
variables alone does not clear containerd's default daemon transfer proxy.
No RKE2 restart, global host pin, insecure pull or cache purge was performed.
The forward is removed after use; reliable permanent egress remains an input
for a fresh production node. See DEPLOYMENT.md for the diagnostic procedure.

### Logical quota admission

After Auth and restore succeeded, the first native regression attempt returned
`429` before creating any resource. `local` had 50/50 projects and 102/200
Endpoints. Its controlled Worker stop was restored in the failure path.
Four prior **passed, owned, already unprotected** lifecycle fixtures were
retired by exact-name/ETag/idempotent product lifecycle API, not by deleting
metadata or raising quota. Each reached a held tombstone with a recorded
seven-day recovery deadline. Physical GC is disabled; all data and old test
records remain. See RESOURCE-RUNBOOK.md for repeatable quota handling.

### Shared storage stall during native cold wake

The second native attempt, Job `publication-ui-20261008140529`, reached
real SQL/branch creation but returned SQL 503 during the parent's cold SELECT.
In the 14:03–14:17 UTC window, the three etcd files contained 41/41/44 slow
fdatasync entries, with maxima **21.875 / 30.589 / 26.358 seconds** (not p99).
Linux I/O PSI some avg10 reached about 70%; available guest/host memory was
ample and sampled per-process write throughput was small. All three RKE2
processes automatically restarted once; the operator did not restart them.
The evidence identifies a simultaneous storage wait, not its host-level cause.

Admission stopped, the failed fixture/evidence stayed intact, and its resumed
Writer was suspended by the normal product API after pressure recovered.
A fresh complete native UI then passed, Job `publication-ui-20261008141717`,
with controlled Worker epoch 67→68. This does not establish that the initiating
storage/driver/hypervisor issue is repaired. Windows has no normal disk counter
class in this environment and the operator token is not elevated; privileged
ETW was not started. Shared storage stability remains an open production gate.

### Failed reader recovered through the existing UI Operation

Lifecycle Job `publication-ui-20261008142337` passed its first six checks but
failed at the first reader creation during another I/O wait. The main node had
38.66% I/O PSI some avg10 and about 10 GiB available memory. Failed Operation
`op_60bb08075764392ec964c906` and reader `ep_03fd898fb0f2e678` were retained.
After all three node admission samples recovered, a strict recovery fixture
verified failed/retryable state, resource identity and writer/reader types.
The React UI retried the original Operation: attempts 2→3, unchanged IDs,
retained native data, real recovery/read-only SQL, writer cold wake, both
Computes suspended and monitoring visible. The first recovery test read before
login completed and returned 401 without a retry mutation; explicit UI login
completion now precedes the identity checks. Both failed attempts are retained.

The recovered owned fixture was retired through the retained lifecycle API to
release project quota; physical GC stayed held and the seven-day recovery
window was recorded. Complete lifecycle acceptance then uses a new isolated
fixture. Recovery success does not resolve the shared-host storage root cause.

## 4. Resource retirement and manual replay

Prior terminal test cleanup archived 48 Jobs and five standalone probe Pods
before UID/resourceVersion conditional deletion. Newly completed QA/UI jobs
are archived and retired at the final gate. The final all-namespace snapshot
had zero active faults and no Pending/Error/CrashLoopBackOff workloads. One
succeeded RKE2 CNI installer Job remains under its system owner. All three
nodes and API/Worker/Web were Ready; managed VM/runners and current I/O PSI
avg10 were zero. Completed Pods are historical
statuses, not ongoing application crashes; their deletion does not itself
free a running Compute. Actual capacity is released through service disable
and Compute suspend, observing both VM and runner disappearance.

Controller PostgreSQL and control metadata PostgreSQL are separate systems.
Retained Pageserver node 1 and managed node 2 have different identities/data.
Three Safekeepers and per-node Agent/controller roles are intentional. Only
the proven unused legacy `proxy-api` and `compute-resizer` were retired by
Helm. Image-name duplication is not sufficient grounds to delete a service.

Follow DEPLOYMENT.md/UPGRADE.md, retain the complete site overlay and external
Secrets, use the seven-image lock and verify every node before admission.
Existing lab Proxy identity is `lab.neon.local`; fresh cluster certificate
identity follows its bootstrap input. Run the public Linux UI suites serially
with protected admin-password files and new evidence/private directories;
Auth browser Origin must equal `managedAuth.publicOrigin`. See TESTING.md.
Keep failures immutable; continue accepted Operations instead of reissuing
uncertain writes. No Python runtime is included in product images/source.

## 5. Remaining product/production gaps

Functions, customer Object Storage and real AI inference services are not
implemented. Auth SMTP, email ownership verification/reset, OAuth/SSO/MFA,
complete user administration and key rotation remain independent work.
In-place PITR/full Backend consistency, physical GC/TTL/failed-resource and
Endpoint deletion, fractional CPU/full memory return, long-transaction and
short-connection races, distributed external SQL fencing, complete adversarial
authorization, HA/DR, persistent SLO/alerts and whole-stack trusted TLS have
implementation or qualification gaps. PRODUCTION-GATES.md remains authoritative;
no successful lab test converts those rows into production availability.
