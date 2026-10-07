# Historical branch recovery and Neon Helm 0.1.2 — 2026-10-07

## 1. Delivered scope and conclusion

This increment implements PostgreSQL historical recovery **to a new branch**,
from a retained timestamp or WAL LSN, in the Go API/independent Worker and React
Console. Native Pageserver history bounds and LSN leases protect the resolved
restore point. The source branch is retained. Today's role/database intent is
not projected into historical database state. Migration 013 persists provenance.

The locked control source is `ac94dfa2f8e00592bc0cc86fc2343494296fcdeb`.
It contains restore implementation `1680489` and the subsequent VM generation
observation fix. The latter completes suspension when an owned cold wake creates
a successor with the same VM name, without deleting that successor. This does
not establish distributed suspend/wake admission fencing.

This is a verified self-hosted preview increment, **not full official Neon
functionality or production admission**. In-place restore, Time Travel Assist,
historical retention management and coordinated Backend recovery remain separate
deliverables. Official contracts are [Create branch](https://api-docs.neon.tech/reference/createprojectbranch)
and [Restore branch](https://api-docs.neon.tech/reference/restoreprojectbranch).
The current implementation supplies the first contract's historical creation
semantics; it does not claim the second contract's connection cutover behavior.

## 2. Source, images and deployment

| Item | Actual identity or boundary |
| --- | --- |
| Control source | `ac94dfa2f8e00592bc0cc86fc2343494296fcdeb` |
| Control GitHub Linux CI | [37606274457](https://github.com/william-lbn/control-plane/actions/runs/37606274457): all nine jobs passed |
| Go gate | 233 tests passed, zero failed/skipped; real PostgreSQL/PostgREST integration, race/vet, contracts and migrations |
| Web gate | 13 unit tests, formatting, type check, Vite and Swagger passed |
| Public control images | Five Linux/amd64 images anonymously verified against manifest/config/source labels; [exact digest lock](../locks/control-plane-ac94dfa.json) |
| Node image availability | 15 checks passed: all five digests pulled on all three nodes |
| Neon/Autoscaling/PostgreSQL forks | Runtime source unchanged; existing 46-image distribution and source lock retained |
| Chart version | All ten packages and stack version 0.1.2 |
| Linux local chart gate | Ten charts, six tool contracts, six schema/unsafe-setting rejection cases; `helm-quality-1791368826` |
| Unified deployment | Eight ordered release stages passed, protected attempt `unified-102757` |
| Migration and external state | API/Worker quiesced; full saved values, metadata dump and external Secret archives retained before upgrade |
| Live identity/manifest audit | Eight PVC identities/bindings and external Secret identity/data preserved; installed manifests/hooks and runtime images match |

The `api.pitrEnabled` setting defaults to false. It is shared by API/Worker and
cannot be enabled while creation is disabled. The lab profile explicitly enables
it following real storage/UI acceptance. It exposes only the narrow
`pitr_new_branch` capability. OpenAPI **0.7.0** documents 46 paths/63 operations.
The runtime adapter targets the current managed, unsharded Pageserver placement;
relocated/sharded storage remains a qualification gate.

## 3. Fresh published-image UI gates

Linux Chromium uses the published control digests, current TypeScript tests,
separate API/Worker and real Neon Proxy/PostgreSQL. Suites run serially, each with
separate protected password fixtures and immutable evidence. No test trace,
video, HAR or secret body is published. A successful result includes disappearance
of both managed VM and Runner Pods after UI suspension.

| Suite | Actual status | Identity and observations |
| --- | --- | --- |
| Historical restore | PASS: 11 checks, zero VM/Runner Pods | `publication-ui-20261007103411`, project `prj_91932c6be34d3dad` |
| Native project/branch/Endpoint and Worker recovery | PASS: 14 checks, zero VM/Runner Pods | `publication-ui-20261007103710`, project `prj_6a36360ae1130007`; accepted Operation `op_61c01398ca242005f3203f92` survives Worker outage; leader epoch 39→40; two failed reads, one project POST |
| Data API/RLS and manual/automatic zero | PASS: 21 checks, zero VM/Runner Pods | `publication-ui-20261007103858`, project `prj_b9c7727d4dfef116`; native PostgREST/RLS, subject separation, invalid/privileged JWT rejection, forged write denial, disable/re-enable and manual/idle zero/first-request wake; two failed reads, one enable POST |
| Console invitations and access revocation | PASS: six checks, no Compute created | `publication-ui-20261007104307`; invited registration, existing-account acceptance, secret replay redaction, Viewer/cross-organization denial, revoke and immediate access loss |
| Application credentials | PASS; no Compute created | `publication-ui-20261007104457`, project `prj_6a36360ae1130007`; lineage/self/model checks, one-time secret/replay redaction, rotation/revocation, reload and test-owned credential retirement; inference explicitly not tested |

The historical suite records a timestamp and committed LSN, then creates later
data, a table, role and database. Recovery contains the historical row and omits
the later objects. It verifies branch-only writes never modify the source,
explicit LSN recovery, replay of the original key/Operation/branch/LSN, and
rejection outside retained history without accepting another branch.

Reading the recovery window does not wake the source Compute. Two controlled
503 observation reads produce exactly one restore POST. After immediate suspend
and Proxy cold wake, branch data persists and the **original suspend Operation
succeeds**, `op_6d8a7c4b05664a6d51322238`. Timestamp and explicit LSN branches are
`br_2fbd8de596a1e3b3` and `br_388a0cd79b17029b`. Masked UI screenshots were inspected.

All five release-specific published-image browser suites passed. The original
batch receipt remains failed because its first credential fixture was refused;
the separate corrected credential receipt establishes that suite's success.
Final public Helm release/consumer checks will be recorded from their own receipts.
Earlier successful versions cannot substitute for these gates.

## 4. Failures, correction and storage incident

Failed attempts remain failed, with their original Jobs/logs/Operations/fixtures:

1. A candidate test incorrectly selected the protected platform `cloud_admin`
   database owner. The test now creates its own managed role and uses that owner.
   Candidate restore then passed; no Neon fork source change was required.
2. A native regression encountered an independent cluster storage stall. Guest
   I/O PSI some reached approximately 55–71%, full 40–64%, while available RAM
   exceeded 9 GiB per node and memory PSI stayed zero. Disk write await was
   approximately 0.2–2.5 seconds. The three guests share physical storage; the
   initiating host/storage cause is **unattributed**, not permanently repaired.
   No fsync/disks/etcd safety was weakened. The original accepted Operation later
   succeeded with the same resource IDs, while the browser attempt stayed failed.
3. The first published `1680489` restore test exposed a real Worker race: checking
   only for a missing VM name could miss the transient 404 and wait on a new
   cold-wake generation. `ac94dfa` checks original UID deletion. Unknown identity,
   wrong ownership, read failure or the old UID persisting is not accepted as
   success. Unit tests exercise that matrix; the fresh live test checks its
   successful original suspend Operation.
4. A private Web helper initially attempted to write Vite temporary config to a
   read-only image. The helper mounts a bounded emptyDir for that temporary path.
   The next Linux gate passed; this was test orchestration, not a product defect.
5. A credential regression first selected the restore-prefixed test project,
   which the public suite correctly refused before mutation: its fixture must
   have a `ci-` project name. The private runner now selects its successful native
   `ci-ui-` fixture. That failed attempt is preserved independently of the new run.

Only each confirmed owned failed-test Compute was suspended through the API,
after evidence collection. Projects, timelines, SQL data, credentials, rollback
images, private attempts and all eight Bound PVCs were kept.

The new public [node pressure gate](../tools/check-node-pressure.sh) refuses the
next test if I/O PSI or memory pressure exceeds the documented limits. It reads
Linux pressure/memory state; it neither changes system settings nor proves host
storage capacity under all loads. See [resource runbook](RESOURCE-RUNBOOK.md).
No concurrent compiler/image build ran during the fresh real browser suites.

## 5. Isolated metadata restore

`helm-restore-1791368473` restored the pre-upgrade metadata dump into disposable
emptyDir PostgreSQL, leaving live metadata unchanged. It verified 35 projects,
86 branches, 91 Endpoints, 447 Operations, 13 migrations, 12 invitations, ten
invitation constraints and 26 tables. Both historical branch provenance records
were valid; invalid restore provenance count was zero.

This proves that metadata dump's restore, **not a full Neon data-plane or DR
recovery**. Controller metadata, WAL, object storage, route/credential state and
the full service recovery set require their own consistency and RPO/RTO gates.

## 6. Reproduce and continue

Follow [deployment](DEPLOYMENT.md), [upgrade](UPGRADE.md),
[source provenance](SOURCE-PROVENANCE.md) and [Linux UI testing](TESTING.md).
The control repository contains the precise API/model/lease contract and manual
steps in [HISTORICAL-BRANCH-RESTORE.md](https://github.com/william-lbn/control-plane/blob/ac94dfa2f8e00592bc0cc86fc2343494296fcdeb/docs/HISTORICAL-BRANCH-RESTORE.md).
Suspend owned test Endpoints only after querying retained data; preserve all
private evidence/fixtures. Do not blindly rerun a partially changed fixture.

| Remaining capability | Why it is not marked complete |
| --- | --- |
| Full deletion/GC | Dependency protection, service shutdown, tombstones, safe retention/GC and recovery races need implementation |
| Fractional CPU/full RAM return/multiple Reader qualification | Driver/guest/cgroup reconciliation and release-specific load/fault evidence remain separate |
| Distributed zero fencing | Compatibility Adapter still has one replica; this UID observation fix is not a distributed admission ledger |
| Trusted TLS | Console/Proxy/storage/metadata transport trust and rotation still contain lab exceptions |
| Managed Auth/Functions/customer Object Storage | Product runtimes, branch semantics, APIs/UI and lifecycle remain unimplemented; core S3 is only database storage |
| AI inference | Credential policy exists, but provider routing/streaming/accounting runtime and a configured real provider are absent |
| Full HA/DR | Singleton/local-path/shared physical storage and untested full-stack recovery do not qualify independent fault domains |
| Complete PITR | In-place cutover, backup branch, Time Travel Assist, history settings and coordinated Backend recovery remain unfinished |

The ordered implementation plan is [PRODUCT-COMPLETION-PLAN.md](https://github.com/william-lbn/control-plane/blob/ac94dfa2f8e00592bc0cc86fc2343494296fcdeb/docs/PRODUCT-COMPLETION-PLAN.md).
Every subsequent capability must supply code, migration, OpenAPI, UI, locked
images/Helm and actual positive/negative Linux acceptance before being enabled.
See [production gates](PRODUCTION-GATES.md) for the qualification boundary.

Two-reader/vertical-resource/fault qualification, complete catalog permissions
and a clean-cluster installation are not rerun by these suites. Prior evidence
is retained as historical and cannot qualify this release's untested scenarios.
