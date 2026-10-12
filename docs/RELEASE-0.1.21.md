# 0.1.21 — Explicit retained Functions wake

Control source/runtime `0198f7c8249d4d3755f62b685a0db0c15ff7301c`, OpenAPI
0.14 (97 implemented routes), public Linux CI `38223473074`: all 13 jobs passed.
Seven own OCI images were anonymously verified against that source. Own-fork
Neon/Postgres/autoscaling and the fixed Functions guest image are unchanged.

`POST .../functions/{slug}/resume` and **唤醒保留版本** add an explicit new boot
from the last successful source/environment and original SQL identity. The API
shares guarded deployment admission and Worker reconciliation, checks suspended
state and complete original retirement before backing writes, and rechecks
parents/version/retirement/successful source under metadata locks. The exact body
is `{}`; UI ZIP/env editor contents are not submitted. Fingerprints distinguish
wake from deployment; replay returns the same durable Operation. Audit records
the resume intent. No customer request is automatically executed or replayed.

The [API/data/UI/recovery and focused test contract](https://github.com/william-lbn/control-plane/blob/0198f7c8249d4d3755f62b685a0db0c15ff7301c/docs/FUNCTIONS-WAKE.md)
defines acceptance. The Linux test creates one owned Function on the retained
database, stops it, wakes through the UI, verifies a new boot and retained
bundle/env, checks replay/conflict/stale version behavior, invokes a real SQL
read with the same role and retained row, and normally retires the test runtime.

**New wake live acceptance passed on the exact source/runtime.** See the
[actual Linux UI checkpoints, reproduction and limits](ACCEPTANCE-2026-10-12-FUNCTIONS-WAKE.md).
Prior native and monitoring passes remain
version-specific. This is explicit manual wake, not automatic idle/cold wake or
in-process RAM restoration. Public streaming ingress, triggers, backend cloning,
full metering, issuer rotation, external fencing and HA/DR remain independent.
