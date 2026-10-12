# Function history restoration: actual Linux UI acceptance

## Result and exact versions

**Passed by original-fixture continuation.** Control runtime source
`1d4854ec44189643a1bdec558053f7bb266fd7a0`, OpenAPI 0.17.0 / 100 routes,
unified Helm 0.1.25. Public Linux CI `38314431980` passed all 13 jobs and 745
Go/PostgreSQL checks, zero failures/skips. Twenty focused isolated PG/API checks,
Linux frontend tests/build, seven anonymous OCI/source checks, 21 serial node
imports, ten-chart QA and eight-stage deployment passed. Business Secret/PVC
identities/full prior values were preserved. No Neon/Postgres/autoscaling fork,
Kubernetes permission or fixed guest image was changed.

Final Chromium Job `publication-ui-20261012225133` completed on 2026-10-13
06:52:05 Asia/Shanghai (2026-10-12 22:52:05 UTC). Committed browser/SDK source
`b4d6e27b70c4b20f60127f62734856fa88badc47` differs from the runtime source only
in `web/e2e/functions-rollback.spec.ts` and `examples/functions/postgres/index.mjs`.
Ancestry and exact paths were verified; the updated SDK was packaged on Linux
as customer Function code, without changing the Go API, Console runtime or guest
base image. This is not a fresh first-pass or full production result.

## Actual nine checkpoint groups

The original Function `fnc_6c99dd3d91b4dbe7` (`roll`) in the accepted native
project/branch/database was retained through every continuation.

1. Original successful create/deploy Operations and exact definition/source were
   verified before any continuation. No second definition was created.
2. The original unready guest was normally retired and the corrected SDK deployed
   on the same definition, preserving SQL identity and original data.
3. UI invoked the original SQL code and performed one application write.
4. A real PostgreSQL idle-session disconnect was deliberately induced only in the
   application's session. Node survived, a subsequent explicit read reconnected,
   the same role/data remained, and the write count stayed two.
5. UI deployed a distinct code digest with another environment; actual invocation
   returned replacement behavior.
6. After normal stop, UI restored the original SDK version from history, ignoring
   unsaved form values. A new instance/generation executed original code/environment
   with the same SQL identity, two rows and immutable source lineage.
7. Exact original rollback replay returned its original Operation; changed source,
   cross-route key and fresh-key stale version rejected with 409/412.
8. Final continuation verified all nine preceding successful Operations, completed
   restore lineage and original final stop before deletion; writes were not replayed.
9. Unknown source rejected; normal definition deletion and Writer suspension completed.
   Collector observations contained no managed Compute VM or Runner Pod.

Corrected SDK source deployment `fdp_f39df18bf7e080c8`, replacement
`fdp_61dbefc72a17fdaa` and all old/new history remain. `app.function_probe` in
`fn_native` retains two rows, including the one `rollback-kept` write. Original
credentials/code/env and exact Operations remain outside public Git.

## Retained failures and corrections

- Two private launcher attempts failed before browser Job or business writes:
  archive selection omitted the example packer, then fixture admission omitted
  the new suite. Their source/receipts remain; only transport setup changed.
- Job `publication-ui-20261012221927` created/deployed the Function once, then its
  test parsed Base64 response bytes as plain JSON during a read. No test write ran.
  The committed test now checks `body_encoding` and decodes it.
- Read-only continuation `publication-ui-20261012222321` found the original Node
  unready. Original UID/CID were verified and a shared read of its disk recovered
  the application log. This running-disk diagnostic was **not** treated as a backup.
  Protected log classification proved PostgreSQL `57P05` (idle-session timeout)
  plus an unhandled pool `error` event; raw logs/credentials were not printed or
  published. Log SHA256:
  `ab96a798c49602919f1a33ee277d60f72d26ece9b02ed3db27c8e7cbc0097f5f`.
- The example now handles idle pool errors without logging the error/client or
  retrying SQL. An explicit test-only application session probe (`1s`) verified
  real disconnect/reconnect behavior. Server/Endpoint defaults and Neon code stayed
  unchanged; this app counter is not trusted platform idle/billing telemetry.
- Job `publication-ui-20261012224420` passed seven functional groups and final stop,
  then used the wrong delete-button name. Only the final retirement checkpoint was
  continued with the correct UI control; no previous write/deployment was rerun.

## Reproduce and remaining gates

See [deployment/reproduction](FUNCTIONS-ROLLBACK.md), the
[control contract](https://github.com/william-lbn/control-plane/blob/1d4854ec44189643a1bdec558053f7bb266fd7a0/docs/FUNCTIONS-ROLLBACK.md)
and [corrected SDK](https://github.com/william-lbn/control-plane/blob/b4d6e27b70c4b20f60127f62734856fa88badc47/examples/functions/postgres/index.mjs).
Normal use leaves `APP_IDLE_SESSION_PROBE` unset. For a fresh acceptance use an
unused operator-owned scope; do not replay this retained write. Historical resume
fixtures are tied to reviewed identities/checkpoints rather than arbitrary retries.

This does not qualify automatic Functions sleep/wake, public HTTP/SSE/WS, seamless
switching, cloning/triggers, full logs/metering, external fencing, HA/DR, issuer
rotation, mixed-version rollout or whole-chain trusted TLS.
