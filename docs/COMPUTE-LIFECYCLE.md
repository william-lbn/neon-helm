# Independent Compute deletion and replacement

## Product and source contract

Neon's [Manage computes](https://neon.com/docs/manage/computes#delete-a-compute)
describes a branch with one Writer and multiple Readers. Deleting any Compute
retains branch data; adding a replacement changes its connection details.
Control source `0ba173262d53d9bd634b52347ce417ae83033a85` implements this slice.
Source CI and nine serial Linux browser suites passed (146 checks). Four original
failed Operations have 23 separate recovery checks. Exact Job identities,
retained failures and boundaries are in [this acceptance](ACCEPTANCE-2026-10-10-COMPUTE-LIFECYCLE.md).

The API/Worker lock is `locks/control-plane-0ba1732.json`. Migration 018 is forward
only; no historical migration is edited. Kubernetes resource names, Timeline,
WAL, PVCs, external Secrets and original SQL credentials are retained.

The authoritative model, API, diagrams and manual sequence are in
[`docs/ENDPOINT-DELETION.md`](https://github.com/william-lbn/control-plane/blob/0ba173262d53d9bd634b52347ce417ae83033a85/docs/ENDPOINT-DELETION.md).
`DELETE /api/v1/projects/{project}/endpoints/{endpoint}` requires an exact
Selector, quoted `If-Match` version, stable Idempotency-Key, authorization and
session CSRF. The Worker closes only the target Proxy route, retires its owned
VM with UID/resourceVersion, observes normal Runner disappearance, then records
a held tombstone. Unknown external write outcomes remain failures until observed
or explicitly retried under the original Operation.

Split deployment grants `get,list` of namespace Pods only to the Worker through
`neon-control-worker-observer`; the API retains named Pod `get` only. Label
selectors filter the actual retirement observation and the Go Driver checks
project/Endpoint ownership of every result. Kubernetes RBAC cannot enforce label
selectors on list. No Pod mutation/delete privilege is granted. The explicitly
legacy combined API/Worker profile needs the same read observer on its API role.
CI renders and checks both profiles and the absence of Pod mutation privileges.

## Upgrade and manual acceptance

1. Follow [UPGRADE](UPGRADE.md) with full private overlays and metadata backup.
   Preserve the old image/source lock, PVC/Secret identities and every failed
   attempt. API and Worker must select the same immutable image digest.
2. After migration and rollout, log into Console and create a dedicated project.
   Use 1 CPU/1 GiB per Compute and add two Readers serially. Write a real SQL
   probe row; verify both Readers see it and reject writes.
3. Delete one Reader through Compute UI with its exact Selector. Await the
   original four-stage Operation and normal VM/Runner retirement. The Writer
   and the second Reader must remain usable.
4. An enabled branch Data API, Auth or Object Storage blocks deletion of its
   bound Writer. Explicitly disable these dependencies before deleting Writer.
   Confirm the surviving Reader can still query retained rows.
5. Recreate Writer on that branch using the original branch password. A
   different password must be rejected without silently rotating existing roles.
   Verify a new Selector, retained data and replication to the original Reader.
6. Delete all Computes. The branch must remain present with a data-retained
   empty state. Add another Writer and reconnect to the same data.
7. Test project retained deletion/recovery: previously independently deleted
   Endpoints stay deleted. Finally retire this owned test project, leaving data,
   credentials, operations and evidence intact while releasing runtime capacity.

## Serial Linux browser command

Use exact control source from the image lock and a new private/evidence attempt.
Follow [TESTING](TESTING.md) for Linux dependencies and password-file input:

```bash
export NEON_E2E_PRIVATE_DIR=/secure/e2e/endpoint-delete-001
export NEON_E2E_ARTIFACTS=/var/lib/neon-evidence/endpoint-delete-001
export NEON_E2E_ATTEMPT=endpoint_delete_001
npm run test:e2e -- endpoint-deletion.spec.ts
```

The suite deliberately discards one already accepted HTTP 202 and verifies the
same key/version returns the same Operation. No Playwright retries or concurrent
live suites are allowed. Archive real Pod/Job identities and logs; retire only
owned completed resources with UID/resourceVersion preconditions.

## Independent gates

Scale-to-zero retains its Selector and allows cold wake; deletion closes its
old Selector. Neither is physical garbage collection. External epoch fencing,
connection-ledger HA, failed-creation cleanup, TTL, physical data purge, fractional
CPU, complete memory return and whole-chain trusted TLS remain separate gates.
Functions and provider inference are still unimplemented. A chart upgrade and
successful feature tests do not constitute production certification.
