# 0.1.22 — Managed database Owner transfer

Source `e2dc5875e56659632310cc6ba0986d8490aff6ca`, OpenAPI 0.15.0 with 98
implemented routes. Public Linux CI `38246909591` passed all 13 jobs and 731
Go/PostgreSQL checks, zero failures/skips. Seven OCI references were anonymously
verified against that source; own-fork Neon/Postgres/autoscaling and the fixed
Functions guest image are unchanged.

The [owner-transfer contract and reproduction](DATABASE-OWNER.md) adds a real
PostgreSQL owner operation, string catalog versions, original OID/marker guards,
transactional admission/audit, Worker reconciliation, lost-acknowledgement CAS
and a Console form. It preserves original data, object ACLs and credentials,
and updates all Writer/Reader cold configurations. Non-superuser SQL is tested
independently; no privilege bypass or extra Kubernetes RBAC is introduced.

**New owner-transfer actual UI acceptance passed by original-fixture continuation.**
See the [exact result, test corrections and remaining gates](ACCEPTANCE-2026-10-12-DATABASE-OWNER.md).
Native Functions,
monitoring and explicit retained wake retain their version-specific receipts.
The new focused UI test verifies original/final owners and actual object ACLs,
replay/conflict/stale requests, data and passwords across Writer/Reader cold wake,
and normal owned resource retirement. Default/system-owner transfer, rename,
arbitrary external DDL, distributed fencing and full production parity remain
separate gates.
