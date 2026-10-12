# Managed database Owner: actual Linux UI acceptance

## Result and immutable release

**Passed as a preview slice by original-fixture continuation.** Deployed source
`e2dc5875e56659632310cc6ba0986d8490aff6ca`, OpenAPI 0.15.0, unified Helm 0.1.22.
Public Linux CI `38246909591` passed 13 jobs and 731 Go/PostgreSQL checks, zero
failures/skips. Seven OCI references were anonymously verified and imported
serially 21 times on three nodes. Ten-chart QA and the eight-stage deployment
passed, preserving full prior values and business Secret/PVC identities. No
Neon/Postgres/autoscaling fork or fixed Functions guest image was changed.

Final Linux browser Job `publication-ui-20261012130243` completed on 2026-10-12
at 21:03:01 Asia/Shanghai (13:03:01 UTC). Runtime remained `e2dc587`; committed
test descendants changed exactly `web/e2e/database-owner.spec.ts`, with ancestry
and diff verified before each immutable source export. This is not presented as
a fresh-install first pass or full production qualification.

## Actual functional checkpoints

The original project/branch/Writer from the native Functions fixture were reused.
Two managed roles (`owner_old_v1`, `owner_new_v1`) and database `owner_transfer_v1`
were created once through the UI and retained. The new owned Reader
`ep_66c918cd98a6a0f0` was normally deleted after verification.

- Original successful role/database Operations and absence of prior SQL writes
  were verified before continuing; creation was not replayed.
- Actual old-owner SQL created and wrote a table. UI Owner change completed via
  the original leased catalog pipeline.
- Same key/body/version returned the original completed Operation; changed body
  was rejected with 409 and new-key stale version with 412.
- New-owner password authenticated through the Proxy; PostgreSQL reported the
  new database owner and allowed new-owner CREATE. Old table data, object owner
  and ACL/privilege observation were unchanged.
- Writer cold wake retained the new owner, data and password.
- A Reader created from the updated catalog and its subsequent cold wake both
  returned recovery mode, new owner and retained data using the same credentials.
- The original Reader deletion Operation succeeded. Final continuation verified
  that Reader absence and an already-suspended Writer without another mutation.
  Collector observations contained no managed Compute VM or Runner Pod.

## Retained failures and precise corrections

1. Initial Job `publication-ui-20261012122632` completed role/database creation,
   then waited on an exact accessible-label match for a select containing option
   text. Logs/audit confirmed SQL had not been dispatched. Its original UID/RV
   was verified and a normal Job deadline ended the pure test wait; no business
   resource was deleted. Actions now have a 30-second bound and the select uses
   its stable label without the incorrect exact-text assumption.
2. Continuation `publication-ui-20261012124413` verified the original empty tables,
   then the existing single-statement workbench rejected a two-statement script
   with SQLSTATE 42601. No table write committed. The test submits individual
   statements; script-mode product support is a separate next feature.
3. `publication-ui-20261012125222` passed all Owner/Writer/Reader functional checks
   and deleted the Reader. Its last cleanup tried to suspend an already-suspended
   Writer whose UI button was correctly disabled. The final continuation inspected
   those completed identities and actual absence without replaying data or CRUD.

Neon administrative Console/API roles inherit read/write-all permissions.
Therefore the test compares real object ownership and ACLs rather than assuming
an artificial write denial. No existing role privileges were reduced to make a
test pass. Original failures, credentials, role/database data and successful
receipts remain in private evidence; public code contains no credential values.

## Reproduce, upgrade and remaining gates

Use the protected Linux `database-owner.spec.ts` workflow and the operator-owned
fixture, as described in [deployment and reproduction](DATABASE-OWNER.md) and the
[exact control contract](https://github.com/william-lbn/control-plane/blob/e2dc5875e56659632310cc6ba0986d8490aff6ca/docs/DATABASE-OWNER.md).
Resume only a documented original checkpoint, proving state/identity before
further writes. Keep role password files outside Git. Archive completed Job logs
before normal UID/RV retirement.

Migration 024 is forward-only; drain catalog Operations and customer mutations
for API/Worker upgrade. Both must support the new Worker action before admission.
Mixed-version rollout, default/system-owned database transfers, rename, arbitrary
external DDL adoption, physical GC, distributed fencing, HA/DR, full TLS and full
official parity remain independent. The broader catalog group is not marked
fully complete by this bounded Owner transfer.
