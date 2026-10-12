# 0.1.25 — Restore retained Function deployments

Source `1d4854ec44189643a1bdec558053f7bb266fd7a0`, OpenAPI 0.17.0 / 100 routes.
Explicit history restoration verifies a completed deployment in the exact
Function/project/branch, its environment UID/MAC/key version and code digest,
then admits a new deployment/generation/boot with immutable source lineage.
Original instances must be normally stopped and retired. Database data is not
rewound, current form inputs are ignored, and customer invocations are not replayed.

Migration 025 adds nullable `source_deployment_id`, scoped FK and immutable
lineage/completed-source guards. Existing deployment Worker actions are reused;
no new Kubernetes privilege, fork or Functions guest image is introduced.
Source-focused isolated Linux PostgreSQL/API checks passed 20 tests; frontend
tests/build passed. Actual live acceptance passed nine original-fixture checkpoint
groups, including a corrected SDK idle-disconnect/reconnect path; see the
[exact source, retained failures and result](ACCEPTANCE-2026-10-13-FUNCTIONS-ROLLBACK.md).

See [deployment, upgrade and reproduction](FUNCTIONS-ROLLBACK.md) and the
[source contract](https://github.com/william-lbn/control-plane/blob/1d4854ec44189643a1bdec558053f7bb266fd7a0/docs/FUNCTIONS-ROLLBACK.md).
This does not provide automatic sleep/wake, public Functions ingress, zero-downtime
switching, backend cloning, full HA/DR, distributed fencing or whole-chain trusted TLS.
