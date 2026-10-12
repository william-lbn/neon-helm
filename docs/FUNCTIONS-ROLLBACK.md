# Function deployment history restoration

## Deploy and upgrade

Unified Helm 0.1.25 pins seven control images to source
`1d4854ec44189643a1bdec558053f7bb266fd7a0` and retains the existing fixed guest
image. Enable the same native Functions platform/immutable common and Worker-only
issuer Secrets described in [FUNCTIONS.md](FUNCTIONS.md); do not recreate them.
No external account or model provider input is needed for this feature.

Drain Functions Operations and normally stop their guests before the ordered
maintenance upgrade. Preserve full values, metadata/backing/Secrets/PVC identities
and prior image locks. Migration 025 is forward-only. Wait for both API/Worker
before admission; mixed-version rollout and destructive downgrade are unqualified.
Do not delete historical lineage/backing to make an old version appear compatible.

## API and manual UI test

The [exact source contract](https://github.com/william-lbn/control-plane/blob/1d4854ec44189643a1bdec558053f7bb266fd7a0/docs/FUNCTIONS-ROLLBACK.md)
defines `POST .../functions/{slug}/rollback`, strict `deployment_id`, current
If-Match, Idempotency-Key, authorization, immutable lineage and leased reconciliation.

1. Use an operator-owned Function/database/schema. Deploy version A with an identifiable
   environment value and perform one tracked application write. Retain its deployment,
   original Operation and SQL identity.
2. Normally stop A and verify original guest retirement. Deploy distinct code B with
   another environment value; invoke it and verify the actual changed behavior/digest.
3. Normally stop B. In history select A and click **恢复此版本**. Unsaved form ZIP/env
   must not override A. Follow the original Operation to completion.
4. Verify a new boot/instance/generation, actual A behavior/environment, the same SQL
   identity, retained application write and history `source_deployment_id=A`.
5. Replay the exact original request: same Operation. Changed source/cross-route key
   must reject with 409; a fresh-key old-version request with 412. Unowned/unknown
   completed sources reject without changing the Function.
6. Normally stop/delete the owned definition, preserving records/code/env/data and
   retirement proof. Normally suspend the test Writer and verify VM/Runner absence.

## Protected Linux automation and gates

`functions-rollback.spec.ts` uses `NEON_E2E_FUNCTIONS_MONITOR_FIXTURE`, protected
Console credentials and two Linux-packaged examples. Original is the pinned
PostgreSQL example; replacement is `examples/functions/replacement/index.mjs`.
The Linux workflow packages replacement code from its immutable committed source.
It does not substitute a fake VM or mock SQL for actual invocation. Tests are serial;
no automatic write retry or new fixture after an unknown outcome.

Actual UI acceptance passed by original-fixture continuation; see the
[version-specific receipt](ACCEPTANCE-2026-10-13-FUNCTIONS-ROLLBACK.md). The corrected
example handles idle pool errors without logging credentials or retrying writes.
The `APP_IDLE_SESSION_PROBE=1s` flag is only an opt-in application acceptance probe;
leave it unset in normal deployments. Automatic
zero/wake, public HTTP/SSE/WS, uninterrupted switching, branch clone/restore
coordination, triggers, complete logs/metering, issuer rotation, external fencing,
HA/DR and full trusted TLS remain separate.
