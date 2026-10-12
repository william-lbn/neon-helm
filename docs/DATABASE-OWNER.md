# Managed database Owner deployment and test

Unified 0.1.22 selects control source
`e2dc5875e56659632310cc6ba0986d8490aff6ca`, OpenAPI 0.15.0. The new Console
form and `PATCH .../databases/{database}` use the existing leased catalog Worker
pipeline. No new service, privilege grant, Kubernetes permission or Neon fork
patch is required. Migration 024 extends the existing database intent state with
`updating`; normal API migration and the existing metadata backup procedure apply.

Use the [exact API/model/recovery/UI contract](https://github.com/william-lbn/control-plane/blob/e2dc5875e56659632310cc6ba0986d8490aff6ca/docs/DATABASE-OWNER.md).
The scope is a ready API-owned non-system database transferred between ready
managed non-system roles on its original branch. The API checks metadata/version
before SQL, captures the original database OID and branch marker, then atomically
rechecks parents, both roles, competing Operations and expected version. The Worker
uses actual PostgreSQL privilege enforcement, CAS updates every Compute config,
verifies original routes and commits final metadata only after re-observation.

Console/API roles inherit native `neon_superuser` administrative read/write-all
permissions. This transfer does not promise least-privilege isolation. Tests
compare real pre/post table ownership and ACLs rather than inventing a write
denial for an already privileged role. Restricted application roles remain a
separate SQL/service-identity concern. Table/schema owners and ACLs are not
reassigned by database ownership transfer.

The protected Linux `database-owner.spec.ts` workflow requires an owned
`NEON_E2E_CATALOG_OWNER_FIXTURE` containing project/branch/Writer IDs and protected
Console login credentials. It creates two managed roles and a retained database
through the UI, tests actual owner/data/ACLs and idempotent admission, then Writer
cold wake and a newly created Reader plus Reader cold wake. It normally retires
only the owned Reader and Compute runtime, retaining data, role credentials and
all records outside public Git. Do not replay CREATE after an unknown outcome;
inspect the saved original Operation/fixture.

**Actual owner-transfer UI acceptance passed by original-fixture continuation.**
See the [exact functional/cleanup checkpoints and retained failures](ACCEPTANCE-2026-10-12-DATABASE-OWNER.md).
System/default-owner databases, rename, unknown external DDL, full lifecycle GC,
distributed fencing and production qualification remain independent.

## Upgrade and rollback boundary

Drain catalog Operations and prevent new customer mutations during the API/Worker
rollout. Both must run the compatible 0.15 source before enabling this path for
users: older Workers do not implement `update_database_owner`. The UI test starts
only after both verified workloads are ready. Mixed-version admission and
distributed Worker fencing are not qualified by this single-instance result.

Migration 024 is forward-only. Before considering older code, verify no pending
owner Operations and no database intent left `updating`. Do not reverse the
migration or restore old metadata over newer user data. Use a separately qualified
forward fix or isolated full restore, preserving backups, prior values, Secrets
and all Operation records.
