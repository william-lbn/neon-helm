# Functions: deployment boundaries and verification

## Current contract

The control-plane source selected by release 0.1.8 exposes branch-scoped,
authorized read-only Function definitions and deployment history. Its Console
has a Functions page. Migration 019 installs immutable deployment, instance and
invocation metadata constraints. Execution remains disabled: installing this
release does not create a Function VM or make a public invocation URL available.

Three metadata routes are documented in OpenAPI 0.11.0:

| Method | Route suffix after `/api/v1/projects/{project}/branches/{branch}` | Purpose |
| --- | --- | --- |
| GET | `/functions` | Bounded, cursor-paginated definitions |
| GET | `/functions/{slug}` | Definition and exact generation ETag |
| GET | `/functions/{slug}/deployments` | Safe deployment summaries and environment names |

Management authorization is checked against the containing project. These reads
never wake a Compute or retrieve customer environment values, SQL credentials or
artifact storage keys. An empty list is valid; it does not establish execution
readiness. The Console distinguishes metadata from observed runtime status.

## Guest image and SQL foundation

`locks/functions-guest-86a9e07.json` records the separately built, public guest
image. Its default entry passed 32 checks in an actual lab NeonVM: signed
management, trusted guest TLS, Fetch/SSE, secret and device boundaries, IPv4 and
IPv6 egress rejection, old-boot/replay rejection and full process-tree shutdown.
That acceptance used a TCP SQL peer, not a Neon database. The image is not an
installed stack service and does not participate in the seven control-image
source-equality gate.

The Go `internal/functionsql` library separately verifies restricted PostgreSQL
roles, transaction rollback, actual login/DML and permission rejection against a
disposable database. It refuses foreign roles and inherited unsafe privileges;
it does not silently change a customer's PUBLIC privilege policy. A deployment
Driver must still connect this library to branch credentials and the real Proxy.

## Upgrade and reproduction

Follow [UPGRADE.md](UPGRADE.md) for metadata backup, complete private overlays,
ordered maintenance and rollback. Preserve migration 019 metadata and immutable
artifacts when rolling back a binary; a Helm rollback is not a database downgrade.
No Function Secret, WAL, PVC, application row or artifact is deleted by upgrade.
Use the exact seven-image lock, not a moving image tag.

After a successful deployment, follow [TESTING.md](TESTING.md) to run protected
Linux browser tests. Set `NEON_E2E_PROJECT_ID` to an authorized native project,
then include `functions-metadata.spec.ts`. The suite starts with real Console
login, opens Functions, reads actual metadata and exercises invalid cursors,
unknown definitions and branch selection. It creates no mocked active Function
and does not claim deployment, invocation or SQL integration acceptance.

The stack has eight independent installed releases and ten packaged charts.
Functions is intentionally not a ninth permanently running service: the future
Driver owns per-Function NeonVM instances and their immutable deployment scope.

## Remaining execution gates

1. Durable idempotent deployment intent, immutable artifacts and environment
   Secrets, leased Driver recovery and strict ownership/UID observations.
2. Actual branch SQL through the Proxy, restricted role persistence across
   Compute cold wake and independently verified branch/PITR inheritance.
3. Atomic publication only after a candidate is healthy; failed deployment keeps
   the previous version; retirement confirms the old Runner is absent.
4. Console upload/configuration/invocation and real Response/SSE regression,
   version rollback, zero/wake and normal capacity release.
5. Independent public origin, application authorization, trusted TLS, invocation
   ledger and distributed fencing before admitting multiple instances.
6. Independent runtime budgets, background work, WebSocket/event semantics and
   full lifecycle. These are separate from the accepted guest primitives.

See the authoritative control source
[Functions implementation](https://github.com/william-lbn/control-plane/blob/main/docs/FUNCTIONS-IMPLEMENTATION.md)
and [model](https://github.com/william-lbn/control-plane/blob/main/docs/FUNCTIONS-MODEL.md).
HA/DR, shared-storage stability and whole-chain TLS retain their independent
[production gates](PRODUCTION-GATES.md).
