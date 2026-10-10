# 2026-10-09 Object Storage and unified Helm acceptance

## 1. Accepted scope

The unified 0.1.6 stack deploys a real branch file service from control source
`716244956d949120b319007affc1d31e5674540f`, alongside the existing Neon/NeonVM/
autoscaling and Go API/Worker/adapter/React Console. The new file path is
`neon-object-rest-v1`, **not a public S3 server**. It is a preview release;
Functions execution, AI inference and independent production gates remain open.

The selected distribution is `locks/control-plane-7162449.json`. All seven
control images come from one source, with anonymous registry verification and
matching profile digests. [Control Linux CI 37950048773](https://github.com/william-lbn/control-plane/actions/runs/37950048773)
passed all 12 jobs and published identical OCI manifests to GHCR and Docker Hub.
The 46-image data-plane distribution and its fork revisions are unchanged.

Ten chart versions are 0.1.6; the eight-release stack ordering is unchanged.
The API/Worker native chart is 0.8.0 and OpenAPI is 0.10.0, 58 paths / 86 operations.
The lab acknowledges experimental Kubernetes/scheduler compatibility; no
production profile or automatic HA claim is introduced.

## 2. Changes and real deployment

* A strict optional `objectStorage` block references an existing external Secret
  in API/Worker. Configuration is mounted read-only; no credential enters values.
* Core MinIO gains a bounded product initialization hook using a separate
  product account and bucket. Root credentials are confined to bootstrap;
  product policy cannot read database buckets, delete blobs or administer MinIO.
* Both MinIO hooks declare exact Helm release ownership. Failed legacy hook
  retirement requires prior archive and UID/resourceVersion preconditions;
  general adoption rules remain strict.
* Product hook/probe request 128 MiB, limit 512 MiB and set `GOMEMLIMIT=128MiB`.
  Each `mc` command explicitly uses its writable `/tmp/mc` configuration path.
* Web NGINX permits bounded 8 MiB uploads and routes branch download paths.
  Singleton security headers are supplied once by the edge while retaining the
  upstream attachment sandbox CSP.
* Standalone protected credential preparation and read-only real IAM verification
  are public Node tools. They never print or overwrite an existing Secret.

The final public-source Linux deployment receipt is `20261010/unified-125901`: eight stages passed,
full previous values retained, metadata backup preserved, exact image locks and
complete manifest/PVC/Secret audit passed. Existing Proxy CA certificate identity
`lab.neon.local` was retained. Different control/controller PostgreSQL and
Pageserver identities are intentional; unused old proxy-api/compute-resizer are
disabled after dependency checks, not replaced by duplicate always-running pods.
Earlier UI receipts retain source `d4549a8`; new-source results are registered
separately. Original-project historical recovery on `7162449` passed 13 checks,
including the actual Catalog asynchronous form regression, timestamp/LSN,
historical catalog isolation, replay and cold wake. Final VM/runner count was zero.

## 3. Source, runtime and functional gates

| Gate | Observed result |
|---|---|
| Go / PostgreSQL / PostgREST | 367 passed, zero failure/skip; vet/race/format; isolated CI DB |
| Auth quality / SQL TLS | independent PG and actual PostgreSQL STARTTLS positive/negative CI gates passed |
| React/TypeScript | 13 Node checks, strict TS/Vite/format passed; latest storage screen visually inspected |
| Unified Helm | 15 Node checks, 16 rejected unsafe configurations, ten lint/render/package gates passed |
| Registry / nodes | seven anonymous OCI/config/source/license checks; 21 CRI digest pulls across three nodes passed |
| Dedicated product IAM | product bucket list succeeds and database bucket returns explicit AccessDenied |
| Current `7162449` historical recovery | 13 passed, Job `publication-ui-20261009154408`; exact original fixture and delayed Catalog refresh |
| Current `7162449` lifecycle UI | 23 passed, Job `publication-ui-20261010120808`; two Readers, WAL, independent zero/wake, retained delete/recovery and original Operation retry |
| Current `7162449` Data API UI | 20 passed, Job `publication-ui-20261010121250`; real PostgREST/RLS and manual/automatic zero/cold wake |
| Current `7162449` Managed Auth UI | 23 passed, Job `publication-ui-20261010121730`; registration/session/JWT/RLS, clone isolation and automatic zero/login wake |
| Current `7162449` Console invitations | six passed, Job `publication-ui-20261010130324` after final public-source deployment; invited registration, organization isolation, Viewer and immediate revocation |
| Current `7162449` Object Storage UI | 19 passed, Job `publication-ui-20261010122440`; bytes/hash/CAS, native clone isolation, cold wake, ACL and retained recovery |
| Current `7162449` native UI | 14 passed, Job `publication-ui-20261010122723`; initial retirement observer failed, later same-UID read-only observation verified all VM/Runner removal |
| Current `7162449` application credentials | eight passed, Job `publication-ui-20261010124541`; scope, redacted replay, rotation and revocation, no inference claim |

The detailed current matrix, identifiers and implementation boundaries are in
[the control delivery](https://github.com/william-lbn/control-plane/blob/main/docs/DELIVERY-2026-10-09-OBJECT-STORAGE.md).
Each suite starts at actual Linux Chromium Console login and supplements its UI
actions with real protocol/permission negatives. Tests are serial, retries=0;
the eight current-source slices total 126 functional checks. Job identifiers use
UTC; resumed user-facing acceptance ran on 2026-10-10 Asia/Shanghai.
each successful suite confirms managed VM and runner removal. Private fixtures,
tokens/passwords and detailed incident logs remain outside public Git/artifacts.

## 4. Failures retained and remedies

1. Initial product MinIO hook was OOMKilled at 128 MiB although each host had
   approximately 9–10 GiB available. Correct the bounded process allowance, not
   host capacity claims or a shared resource concurrency increase.
2. A failed upgrade left unowned terminal hooks, so preflight refused adoption.
   Both hook templates now declare release identity; archives preceded exact
   terminal UID/RV retirement. No data bucket/Secret/PVC was removed.
3. First Object Storage UI failed after 14 checks because `nosniff` appeared twice.
   Edge header ownership was corrected without weakening the assertion. Original
   failed Job `publication-ui-20261009131515` and fixture remain in evidence.
   Its explicit original-project recovery passed four checks; later current-source
   19-check acceptance is a separate receipt.
4. Current Data API regression encountered a new hardware I/O stall after its
   first 15 checks. Original Job and read-only collector failure remain separate
   from recovery. Dedicated etcd log samples recorded fsync maxima approximately
   12.136 / 21.915 / 12.140 seconds on the three nodes, with approximately 9 GiB
   available memory. This is neither production stability approval nor evidence
   of memory exhaustion. No service restart/fsync relaxation/forced VM deletion
   was performed; recovery waits for pressure to clear and uses the original
   project before a new complete regression attempt.

Observed hardware stalls are an acknowledged lab restriction at the user's
direction. They do not prevent serial functional testing when pressure clears,
and they cannot be erased or promoted to a production SLO pass.

The two original Data API failures each have five explicit recovery checks on
their exact retained projects. A later complete current-source Data API run
passed all 20 checks. Original historical recovery exposed a separate Catalog
form race, fixed in source and verified in the original project (13 checks).
The current native browser passed 14 checks; its first final-retirement observer
failed during node2 API refusal and slow fsync. Exact-UID CRI later confirmed no
original Runner container; subsequent same-Job/Pod-UID read-only observation
confirmed all VM/Runner records were normally removed. No forced Pod deletion,
RKE2 restart or observer timeout increase was used. Both failed observations
remain distinct from the later pass; delayed resource retirement has no SLO approval.

## 5. Manual reproduction and retention

Read [OBJECT-STORAGE.md](OBJECT-STORAGE.md) for dedicated credentials, init policy,
IAM and actual UI steps. Read [TESTING.md](TESTING.md) for Linux CI, eight functional
slices and original-UID recovery observation. Read [DEPLOYMENT.md](DEPLOYMENT.md)
and [UPGRADE.md](UPGRADE.md) before installing/upgrading existing data.

Create a bounded project via UI, grant controlled schema CREATE in SQL, enable
storage, create a private bucket, upload and download/hash. Native-clone a branch,
overwrite/delete its file and confirm the parent. Suspend the writer: metadata
polling leaves it zero; file/directory reads wake it. Verify old links close after
disable/re-enable. Explicitly test public_read. Retained project deletion closes
public entry; recovery plus explicit service re-enable restores the original file.

Only proven owned finished fixtures are normally retained-deleted to free logical
project quota; recovery deadline and held tombstone are recorded. Enabled Endpoint
desired=active can coexist with observed=suspended; actual VM/runner absence
proves resource zero. All SQL/WAL/blobs/PVC/Secrets/password fixtures and every
success/failure record remain. Terminal Jobs are archived then retired by UID/RV.

## 6. Independent production requirements

See [PRODUCTION-GATES.md](PRODUCTION-GATES.md): external S3/SigV4, multipart/CORS,
unified application storage scopes, isolated gateway, physical quota and
reference-safe GC/DR remain separate from REST v1. Functions need actual Node.js
24 microVM isolation and execution UI; AI inference needs provider configuration
and real request/streaming acceptance. Neither exists merely because credentials
or an image name are present. Cross-instance external fencing, full HA/DR,
fractional CPU/full memory return, complete tenant security and trusted end-to-end
TLS are unqualified. Shared physical NVMe supplies no independent failure domain.

## 7. Immutable publication receipts

* [Immutable release v0.1.6](https://github.com/william-lbn/neon-helm/releases/tag/v0.1.6)
  selects chart source `ae2e9013172ccb6e50dd30f547d37f1106a7f3d4`.
* [Main Linux CI 38053540900](https://github.com/william-lbn/neon-helm/actions/runs/38053540900)
  and [tag CI/release 38053672551](https://github.com/william-lbn/neon-helm/actions/runs/38053672551)
  succeeded; ten packages, index, SHA256SUMS and source locks are published.
* Linux anonymous standard `helm repo add/update/pull` retrieved all ten 0.1.6
  packages; every package and index checksum passed. No GitHub/registry credential
  was required. Receipt: `storage-public-helm-consumer-attempt1`.
* Linux anonymous clone at that exact chart SHA passed source checks and the
  complete live manifest/hooks/PVC/Secret/images/zero audit. Receipt:
  `storage-public-helm-audit-attempt2`; all eight releases match.
* The first public audit correctly found one Web config-checksum annotation
  mismatch caused by private Windows CRLF source bytes versus Git LF bytes.
  Parsed ConfigMap content was identical; no application/data-plane code or
  behavior was changed. The verified anonymous Git source was used for the full
  standard upgrade, then the independent audit passed. Original failed audit
  and redacted field hashes remain in evidence. Deploy from trusted Linux Git
  or the released packages; do not substitute a Windows-created dirty source tar.
* Post-upgrade Linux Chromium invitation/registration/permission/revocation
  checks passed again (six checks), with no Compute activated.

Documentation-only follow-up commits do not move this tag or change selected
control source `7162449`. Initial failures and historical rollback locks remain.
