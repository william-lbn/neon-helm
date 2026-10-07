# Neon Helm 0.1.1 and Console product acceptance — 2026-10-07

## 1. Scope and conclusion

This increment delivers Console invitations/registration and accepted-Operation
observation recovery, five owner-published control images, ten versioned charts
and the ordered eight-release stack. The Neon/Autoscaling/PG fork runtime source
was not changed. The locked control source is
`f90c9370db583e71796c4c6ad44e51c6ea354f43`.

It is a self-hosted preview acceptance, **not all official Neon functions or
production admission**. Production-oriented chart practices do not implement
unavailable services or establish HA/DR. See the explicit remaining gates below.

## 2. Evidence and release gates

| Gate | Actual status | Identity/boundary |
|---|---|---|
| Control GitHub Linux CI | PASS: all nine jobs | [37575417956](https://github.com/william-lbn/control-plane/actions/runs/37575417956) |
| Go real PG/PostgREST, vet/race, migrations/contracts | PASS: 222 tests, 0 failures/skips | same source CI; invitations/concurrency/role changes included |
| Candidate Web | PASS: 13 unit tests, format/type/Vite/Swagger | protected recovery build attempt 2 |
| Five public image manifests/config/source labels | PASS: anonymous Linux verification | `locks/control-plane-f90c937.json`; Linux/amd64 |
| Three-node image pull | PASS: 15 digest checks | five images on each node, anonymous pull, fixed revision |
| Final chart quality/package | PASS: ten charts, six contracts, five negative cases | `helm-quality-1791350709` |
| Helm public main Linux CI | PASS | `c20f468`; [37577518611](https://github.com/william-lbn/neon-helm/actions/runs/37577518611) |
| Eight-release apply/live manifest audit | PASS | protected `unified-052543`: 29 declared image references, eight PVC bindings, external Secret identity/data and all installed manifests/hooks match |
| Published native UI + Worker/read outage | PASS: 14 checks; zero managed VM/Pods | `publication-ui-20261007052713`; project `prj_70f16b783b534bc1`, same queued Operation succeeds, leader epoch 30→31, exactly one project POST after two 503s |
| Published Data API UI/read outage | PASS: 21 checks; zero managed VM/Pods | `publication-ui-20261007052947`; project `prj_3f4041bd7237ef17`, RLS/invalid JWT/forged writes, same Operation, disable/re-enable, manual/automatic zero and first-request wake |
| Published invitations UI | PASS: six checks; no Compute created | `publication-ui-20261007053408`: invited registration, existing account acceptance, no secret replay, Viewer/cross-org denial, revocation and immediate membership access loss |
| Published Backend credential UI | PASS; no Compute created | `publication-ui-20261007053617`: one-time secret, replay redaction, branch lineage/model checks, rotation/revocation and reload; inference not tested |
| Isolated metadata restore | PASS | `helm-restore-1791350159`: 26 projects, 69 branches, 76 Endpoints, 391 Operations, 12 migrations, 6 invitations/10 constraints, 26 tables |
| Versioned chart release | PASS: quality + release Jobs | [v0.1.1](https://github.com/william-lbn/neon-helm/releases/tag/v0.1.1), source `c20f468`, tag object `35fbb254`; [37578114503](https://github.com/william-lbn/neon-helm/actions/runs/37578114503) |
| Anonymous Helm consumer | PASS | repo add/update, all ten 0.1.1 packages and index SHA256 verified; no credentials required |
| Final runtime cleanup | PASS: another 40 terminal Jobs archived/removed | UID/resourceVersion preconditions; zero managed VM/runner Pods and no static VM; all data/evidence preserved |
| Exact public-source final audit | PASS | anonymous Linux checkout `c20f468c81d5f7cb89657ab6b2661db92d2fbd02`; all installed manifests/hooks, PVC/Secret identities and VM/runner zero gate match |

Unrun production gates below are not completed by this release, a build or a Ready Pod.
The final release report is updated from new immutable receipts, never by
changing a failed attempt into a success. All private dumps/password fixtures,
request/Pod details and masked screenshots remain in protected operator storage.

## 3. Corrected failures and resource retirement

1. The first invitation UI attempt exposed a stale member list. An explicit
   refresh and fresh candidate acceptance corrected it; the failed record stays.
2. After retiring the last static VM, an empty custom-resource lookup produced
   no JSON. Preflight failed before mutation. The tool now preserves empty-list
   semantics; six Linux contracts include named/list/error handling.
3. RKE2/etcd lease loss interrupted a published Data API creation UI test. The
   backend Operation later succeeded, but the old UI stopped observing. Bounded
   read-only recovery and fault injection now follow the accepted ID without
   resubmitting mutation. The failed project/fixture survives and its Compute
   was suspended through the control API.
4. Candidate native browser checks passed, while an immediate resource observer
   saw a terminating runner. The original observer failure remains. Separate
   completion audit showed zero managed VM/Pods. Later observers wait up to
   120 seconds without deleting or force-stopping resources; final public audit
   checks both VM and runner deletion.

Before these tests, 34 terminal Jobs were archived then removed. The historical
static test VM was gracefully stopped after proving no business sessions and
recording checkpoint/flush/shutdown. Optional `compute.enabled=false` retired
its VM/runner and freed 1 CPU/1 GiB. The Service UID, external config/SSH Secrets,
catalog, timelines and all eight Bound PVCs were retained. Restore the same
complete saved Helm values with `compute.enabled=true` (UPGRADE.md); the imported
static Endpoint does not auto-wake while retired. This is not project deletion.

After all four published UI suites, another 40 terminal Jobs and their Pod/log
records were archived in protected storage, then removed with server-side
UID/resourceVersion preconditions. No active Job was removed. This totals
74 terminal test Jobs retired in this work period; project data, fixtures,
private attempt directories, credential state and rollback images were retained.

Git HTTPS tag transport failed twice. The official Git API uploaded the exact
existing annotated object (`35fbb2541d97511ca90e1672eac58752369537cf`) and created
its absent remote reference; SHA, source, tagger/time and message matched locally.
No tag was overwritten. The normal push workflow then built/published the packages.
The version tag remains fixed; this post-publication report update changes docs only.

## 4. Version and manual reproduction

Use SOURCE-PROVENANCE.md for fork/source/digest locks and DEPLOYMENT.md/UPGRADE.md
for external Secret contracts, complete site values, dependency order and
maintenance backup. Run TESTING.md's four Linux Chromium suites serially.
Set `NEON_E2E_POLL_FAULT=true` for native and Data API suites; the controlled
Worker outage additionally proves durable accepted intent and successor epoch.

Keep each private/evidence attempt separate; never expose admin/database/provider
secrets in shell history or public artifacts. After SQL validation, disable the
owned test Data API and suspend test Endpoints. See RESOURCE-RUNBOOK.md for
foundation reservations, asynchronous retirement and incident sampling.
Metadata restore used disposable emptyDir PostgreSQL and did not modify live DB.

## 5. Remaining implementation and qualification

| Capability | Current state and reason |
|---|---|
| Managed Auth | branch authentication service not implemented; Console invitations are separate |
| Functions | no product artifact/runtime/branch/trigger service implementation |
| Product Object Storage | no customer S3/branch object-manifest service; core MinIO stores Neon data only |
| AI inference | scoped credentials exist; provider onboarding/routing/streaming/accounting runtime absent; no real provider credential configured |
| PITR/full deletion | timestamp/LSN restoration, retention/GC/cascade lifecycle not implemented as complete product |
| Fractional CPU/full RAM downscale | integer CPU laboratory path exists; complete guest quota/RAM reclaim acceptance missing |
| Distributed suspend/wake fence | singleton compatibility Adapter and incomplete cross-instance external fencing/connection ledger |
| HA/DR/trusted TLS | current shared disk/local-path/singleton services and HTTP lab exceptions require distinct infrastructure/security/recovery gates |
| Operational completeness | persistent metrics/alerts, full catalog lifecycle, enterprise/email identity and security review unfinished |

This release does not rerun two-read-Compute, full vertical resize, full catalog
permissions or an empty-cluster install. Their older evidence is retained as
historical, not this revision's acceptance. Official capability/API contracts and
the ordered Driver/UI/negative-test roadmap live in the control repository's
FULL-PRODUCT-IMPLEMENTATION.md and PRODUCTION-GATES.md. Continue implementation
by those gates; do not enable capabilities from plans or image names alone.
