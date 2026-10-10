# Linux verification and repeatable UI acceptance

## 1. Offline CI gate

Run on Linux; ordinary PR CI has no live credentials or cluster access.

```bash
npm ci --ignore-scripts --no-audit --fund=false
bash tools/install-helm.sh "$PWD/.local/bin"
export HELM_BIN="$PWD/.local/bin/helm"
npm run check
npm test
npm run helm
npm run package -- --output artifacts/packages
sha256sum artifacts/packages/*.tgz > artifacts/packages/SHA256SUMS
```

The gates validate dependency order, nonmutating overlays, immutable ownership,
Bound PVC capacity and duplicate YAML rejection; lint/render all ten charts;
reject unknown settings and unsafe lab/quorum/cache configurations; check image
digests, external Secrets and PVC retention. This does not simulate Neon storage
or prove runtime HA. Evidence packages are retained by GitHub CI for 90 days.
The Go adapter gate additionally checks the compiled command, UID/fsGroup,
read-only root, two distinct projected credential files with decimal mode 288,
dependency readiness, exact Controller Service proxy permission, no delete
permission and no mounted Python/source ConfigMap. Invalid wake concurrency,
timeout and Pageserver node bounds are rejected by schema.

## 2. Real cluster deployment gate

Follow DEPLOYMENT.md or UPGRADE.md. Record cluster version, node readiness,
chart Git commit, application source commits/digests, release revisions and
PVC identities before/after. `inspect` is a read-only ownership review:

```bash
node tools/stack.mjs inspect --overlay-dir /secure/neon-overlay --output /secure/neon-inspect-001
node tools/stack.mjs verify --overlay-dir /secure/neon-overlay --output /secure/neon-runtime-001
node tools/audit-live.mjs --overlay-dir /secure/neon-overlay \
  --pvc-before /secure/pvc-before.private.json --state-before /secure/neon-upgrade-001 \
  --expect-zero --require-manifest-match --output /secure/neon-audit-001
```

No drift in durable resource identity is allowed. Check actual runtime image
IDs, not only chart values. Do not treat a Pod being Ready as SQL success.
After a failure preserve the Job, logs, Operation IDs, private fixture and
attempt directory; repair the cause and use a new attempt. Do not erase a
failed record or simply rerun against a fixture that was partially modified.

## 3. Browser acceptance source

The control repository owns product TypeScript Playwright tests. Pin its exact
revision from SOURCE-PROVENANCE.md, then run Linux Chromium serially:

```bash
git clone https://github.com/william-lbn/control-plane.git /opt/neon-control-tests
cd /opt/neon-control-tests
git checkout 2dcd7d2dbac6edac9d7f2190ebf8c67db90ebb97
cd web
npm ci --no-audit --fund=false
npx playwright install --with-deps chromium
export NEON_E2E_BASE_URL=http://192.168.146.100:30788
export NEON_E2E_ADMIN_PASSWORD_FILE=/secure/e2e/admin-password
export NEON_E2E_PRIVATE_DIR=/secure/e2e/native-001
export NEON_E2E_ARTIFACTS=/var/lib/neon-evidence/native-001
export NEON_E2E_ATTEMPT=native_001
export NEON_E2E_EXPECT_SPLIT=true
export NEON_E2E_POLL_FAULT=true
npm run test:e2e -- native-product.spec.ts
```

Copy the Console password from your secret manager into a mode-0600 file,
never into shell history or GitHub logs. Tests use retries=0, workers=1,
masked screenshots and no trace/video/HAR. They create real retained projects,
branches and table data. Preserve the private database password fixture for
manual reconnection. Use a new private/evidence directory and attempt per suite.

### Native UI sequence

1. Login and create project with writer bounds max 1 CPU/1 GiB.
2. Wait for successful Operation and write/query actual PostgreSQL data through
   Proxy from the SQL page.
3. Create data-only child branch; verify no implicit Endpoint consumes capacity.
4. Suspend parent writer through UI; then create child writer and verify inherited
   data and independent writes.
5. Suspend child, query parent to cold-wake it and verify branch isolation.
6. Suspend the final writer; monitoring must show current suspended state and
   unknown current CPU/RAM, while retaining historic samples.
7. With the documented split-Worker fault fixture, pause Worker after admission,
   retain queued Operation, restore it and prove the same Operation succeeds.
8. With `NEON_E2E_POLL_FAULT=true`, require recovery after two observation 503s
   with exactly one project POST; apply the same flag to Data API enable tests.
   Permission errors stop observation immediately; mutation requests are not replayed.

### Console invitation sequence

Use new private/evidence directories and run `console-invitations.spec.ts`.
The actual UI creates an account-bound one-time invitation, registers/logs in
an invitee, rejects another organization, accepts as an existing account without
changing its password, revokes a pending invitation, refreshes/removes a member
and proves existing-session access is denied immediately. It creates no Compute.
See the control repository's `docs/CONSOLE-INVITATIONS.md` for manual steps,
API/model invariants, expiry/demotion races and identity integration boundaries.

### Data API sequence

Use new attempt/private/evidence directories, then:

```bash
npm run test:e2e -- data-api.spec.ts
```

The suite starts from UI project creation, creates real RLS tables/roles, enables
the branch service, verifies two-subject isolation, invalid JWT rejection,
forged/valid writes, idempotency and browser origin retention, disables and
reenables the service. It then keeps Data API running while verifying manual
zero/cold request and automatic idle zero/first-request wake. It disables the
owned test service and suspends the test Compute at the end, retaining records.

### Application credential sequence

Choose an existing authorized test project; this suite creates no Compute:

```bash
export NEON_E2E_CREDENTIAL_PROJECT=prj_REPLACE_WITH_TEST_PROJECT
npm run test:e2e -- backend-credentials.spec.ts
```

It verifies data-only child/sibling branches, one-time secret display, replay
without secret recovery, model/lineage positive and negative checks, rotation,
revocation and refresh. Tokens stay in process memory. This is credential
authorization, not AI provider inference.

### Historical recovery sequence

Enable `api.pitrEnabled:true` for API and Worker only on compatible managed
storage; `api.creationEnabled:true` is required. Use new evidence/private
directories and run `npm run test:e2e -- restore.spec.ts`. The UI sequence writes
a before value, records a committed LSN and UTC timestamp, then writes an after
value and creates a managed role/database. Restore to a new branch, verify the
before value and absence of later table/role/database, cold-wake after suspension,
prove the source remains unchanged, restore the explicit LSN, replay the same
request and reject an expired history point. All owned Computes end at zero.

The authoritative API/model/retention-lease rules and manual steps are in the
control repository's `docs/HISTORICAL-BRANCH-RESTORE.md` at the pinned revision.
This suite does not certify in-place restore or consistency of external Backend
services. Native storage/SQL failures must stay visible in retained evidence.

## 4. Additional independent acceptance

### Retained lifecycle and two Readers

Using a fresh fixture/evidence directory and the pinned control source, run
`npm run test:e2e -- lifecycle.spec.ts`. This slice creates a dedicated project,
data-only parent/leaf branches, one writer and two real read-only Endpoints.
It checks root/child/protected deletion denial, leaf runtime retirement and
same-Operation replay, WAL visibility/read-only rejection, independent zero/wake,
active project retirement, seven-day recovery with original identities and
credentials, and absence of previously deleted branches after recovery.

The second retirement cycle covers active Data API/PostgREST/RLS, public relay
closure, recovery with Data API still disabled, permanently revoked Backend
tokens, explicit service re-enable with retained RLS data, and final service
disable/Compute zero. No native timeline/object purge is enabled.

The explicit `NEON_E2E_LIFECYCLE_RECOVERY_FAULT=true` variant adds recovery
failure and same-Operation retry **inside the UI dialog**. It needs the separate
trusted Linux operator described by the pinned control source's TESTING.md;
browser Pods never receive Kubernetes credentials. The public Node tool CAS
checks Worker UID/resourceVersion, changes only the queued owned recovery's
terminal status, restores the Worker and verifies a successor leader epoch.
This is operator-injected status, not storage outage or HA certification.

Use separate attempts for restore, native, Data API, invitation, credential and
lifecycle suites. A read-only observer may continue the original Job UID after
an API outage; it must not reissue lifecycle mutations or rewrite failed reports.

| Scenario | Required real assertions |
|---|---|
| Two read Computes | distinct Selector/VM UID; WAL visibility; writes rejected; independent zero/wake; no additional writer |
| Vertical autoscale | live guest CPU quota/online and RAM, VM observed state, SQL continuity and load/SLO |
| Database/roles | writer and two readers, password rotation success/failure, child inheritance, protected deletion and cold wake |
| Permission matrix | cross-org/project denial, role/key scope/expiry/revoke, membership change and concurrent requests |
| Idle races | active long query/transaction/replication, incoming connection during suspend, old VM generation samples |
| HA/DR/PITR/TLS | independent fault domains and complete recovery/trust evidence; see PRODUCTION-GATES.md |

The published UI slices do not automatically mark these additional rows
passed. Copy source acceptance reports only as historical evidence and rerun
each changed behavior explicitly. Final reports distinguish pass/fail/not run/
not implemented with reasons and resource identities.

## 5. Cleanup and repetition

Stop only resources owned by the current test. Use UI/API suspend for Compute;
disable the owned Data API instance through its product API. Do not delete
project/timeline/role data, PVC, WAL, S3 objects, credentials needed for recovery
or any evidence. Historical tests can be reopened from their fixture, or new
tests can create new project identities with the same scripts. Keep resource
pressure low by running one suite at a time and stopping on infrastructure errors.

Endpoint suspension and Kubernetes garbage collection complete asynchronously.
Wait for the test VM **and runner Pod** to disappear before admitting another
Compute suite; a terminating runner can still consume capacity. The final
`audit-live --expect-zero` gate checks both, and fails on remaining runners.
Bound any observation wait (for example 120 seconds), retain the timeout evidence,
and inspect finalizers/controller/guest shutdown instead of force-deleting it.

## Managed Auth acceptance

Run the public `managed-auth.spec.ts` suite serially using a fresh private/evidence directory. The browser URL must equal `managedAuth.publicOrigin`; the Node runtime requires the public Proxy CA Secret/key and exact certificate identity. Follow [the Auth contract](https://github.com/william-lbn/control-plane/blob/2dcd7d2dbac6edac9d7f2190ebf8c67db90ebb97/docs/MANAGED-AUTH.md) for the explicit database delegation, app registration, branch isolation, JWT/RLS, service dependencies and cold wake. No SMTP/OAuth/provider credentials are required for this basic slice. Preserve failed attempts and all SQL/Secret fixtures; only stop owned runtime workloads. Release-specific real acceptance is recorded separately.

## Object Storage and the current serial matrix

Use the active `stack.controlImagesLock` source revision for the Control Console
and its public TypeScript tests. Follow [OBJECT-STORAGE.md](OBJECT-STORAGE.md)
for the dedicated product credential/bootstrap and bounded real IAM test. A
successful backing product listing and explicit database bucket AccessDenied are
both required; a network timeout is not a permission-denial pass.

```bash
node tools/verify-product-storage-access.mjs --output /secure/evidence/storage-iam-001
export NEON_E2E_BASE_URL=http://YOUR_CONSOLE
export NEON_E2E_ADMIN_PASSWORD_FILE=/secure/e2e/admin-password
export NEON_E2E_PRIVATE_DIR=/secure/e2e/storage-001
export NEON_E2E_ARTIFACTS=/var/lib/neon-evidence/storage-001
# In the matching public control-plane checkout, with Linux Chromium installed:
npm --prefix web run test:e2e -- object-storage.spec.ts
```

Never run an image pull, build or another Compute suite concurrently. After each
suite observe all owned service Operations and VM/runner removal, then start the
next with a unique attempt. Run native-product, backend-credentials, data-api,
restore, lifecycle, console-invitations and managed-auth serially as distinct
receipts. Credentials use an explicitly authorized existing ready test project;
invitations do not start a Compute. Managed Auth's BASE_URL must match its public
Origin. Fault flags and protected recovery contracts are defined by control
TESTING.md, not guessed from chart names.

If a read-only collector loses the API, observe the **original Job/Pod UID** and
retrieve its original report; do not rerun the mutations. An actual failed UI
suite remains failed even after recovery. Retained fixtures can be resumed by
their explicit recovery test only after checking current state and prerequisites.
The Data API recovery rotates its lost ephemeral test issuer via UI while keeping
SQL/RLS data; it does not pretend to reuse an unsaved signing key.

Only exact-name test projects with reviewed ownership/evidence may be normally
retained-deleted to release logical quota. Record recovery deadline and held
tombstone; preserve blobs, WAL, SQL, password files and every original receipt.
This is separate from deleting terminal Job objects with archived UID/RV proof.
