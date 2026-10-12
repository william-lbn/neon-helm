# Functions: deployment boundaries and verification

## Current native execution preview

Release candidate 0.1.21 selects control source
`0198f7c8249d4d3755f62b685a0db0c15ff7301c`. Native Go API/Worker and React UI
now implement definition creation, ZIP/environment deployment, private TLS
artifact delivery, restricted SQL credentials, authenticated JSON Console
invocation, explicit manual stop/redeploy and retained deletion. Execution
defaults to disabled. Installing the chart alone does not qualify the product.

Follow the detailed [native operator/API/SQL guide](https://github.com/william-lbn/control-plane/blob/0198f7c8249d4d3755f62b685a0db0c15ff7301c/docs/FUNCTIONS-NATIVE-PREVIEW.md)
and [OpenAPI 0.14](https://github.com/william-lbn/control-plane/blob/0198f7c8249d4d3755f62b685a0db0c15ff7301c/contracts/openapi-v1.json).
Provision immutable common config/MAC/public CA and separate Worker-only issuer
Secrets, then opt into `profiles/examples/functions-preview.json`. Never project
the Proxy private key. Helm rejects missing configuration, absent backing storage,
combined Worker mode and multiple API/Worker instances before external fencing.

New mutation suffixes after the branch-scoped `/functions` collection:

| Method/path | Purpose |
|---|---|
| POST `/` | Metadata definition with idempotent create Operation |
| POST `/{slug}/deployments` | ZIP/environment plus key/version, queued native execution |
| POST `/{slug}/console-invoke` | Bounded authenticated non-executable JSON envelope |
| POST `/{slug}/suspend` | Explicitly acknowledged original-instance retirement |
| DELETE `/{slug}` | Retire original instance, disable owned SQL login; retain data/history |
| GET `/{slug}/runtime` | Explicit original-identity supervisor observation; no SQL wake/invocation |
| POST `/{slug}/resume` | Explicit new boot from successfully retained source/env; key/version and `{}` |

Active updates require explicit stop; config-only deployments retain completed
code and original SQL identity/data. Environment input is a patch: omitted/empty
dictionary preserves it; empty string removes the named variable. Deleted slugs
can be reused only with a new identity. Customer HTML never executes on the
Console origin, and unknown outcomes are not automatically replayed.

Actual execution acceptance remains separate from source/CI/Ready Pods. The
Linux `functions-native.spec.ts` must verify real UI -> Worker -> guest -> Proxy
-> Neon SQL read/write, schema rejection, safe HTML, application errors, stop,
redeploy and NOLOGIN/retained deletion. Its [0.1.17 failed guest/source recovery](RELEASE-0.1.17.md)
preserves the initial HTTP UI interruption and avoids repeating project/grant
creation. Keep all original failures/checkpoints and normally retire only exact
owned runtime resources. Do not mark pending live acceptance as passed.

Public raw HTTP/SSE/WebSockets, automatic idle zero/wake, triggers, complete
function branch/PITR inheritance, issuer renewal (current guest leaf lifetime two
hours), external fencing, HA/DR and full production transport remain independent
gates. Current-database grants do not prove exclusive access across instance-wide
PostgreSQL roles and PUBLIC CONNECT defaults.

## Historical 0.1.12 foundation contract

The control-plane source selected by release 0.1.12 exposes branch-scoped,
authorized read-only Function definitions and deployment history. Its Console
has a Functions page. Migration 019 installs definition, deployment and
instance metadata constraints. The invocation ledger and route publication
remain to be implemented. Migration 020 adds immutable private backing
receipts for exact environment Secret UID/MAC/key version and deployment scope.
Migration 021 adds immutable instance bootstrap Secret identity receipts. Neither
migration adds a deployment/invocation route or enables execution.
Execution remains disabled: installing this
release does not create a Function VM or make a public invocation URL available.

The selected source includes private Service/VM recovery and atomic PostgreSQL
publication methods. Their historical 0.1.11 foundation quality passed 593 checks;
that same archived source passed three actual MinIO/Kubernetes checks, including a lost Service reply and
own-fork CRD dry-run. Dry-run did not persist or start a VM. These internal
methods are not registered as Worker execution actions or public deploy/invoke
routes; SQL/manifest, artifact TLS, ingress/ledger and execution UI remain
separate integration gates. This chart keeps execution disabled.

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
ordered maintenance and rollback. Preserve migrations 019/020/021 metadata and immutable
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

Native Driver, Console deployment/invocation, real restricted SQL, acknowledged
stop/redeployment/deletion and normal Runner retirement passed the
[0.1.19 native slice](ACCEPTANCE-2026-10-12-FUNCTIONS.md). Original-identity
monitoring and no SQL wake passed the
[0.1.20 observation slice](ACCEPTANCE-2026-10-12-FUNCTIONS-MONITORING.md).

1. Explicit retained-version wake API/UI passed its exact
   [0.1.21 receipt](ACCEPTANCE-2026-10-12-FUNCTIONS-WAKE.md); this does not qualify
   automatic request-triggered cold wake.
2. Automatic idle eviction/cold wake needs background semantics, request admission
   and durable drain/fencing. Counters alone never authorize deletion.
3. Independent public HTTP origin, streaming SSE/WebSocket ingress, application
   authorization, whole-chain trusted TLS and invocation ledger remain missing.
4. Deployment inheritance, rollback/PITR coordination and atomic Backend restore
   remain separate from database-only historical branches.
5. Triggers, logs/metering/budgets, issuer rotation and distributed HA/DR still
   require implementation and independent qualification.

See the authoritative control source
[Backing contracts and evidence](https://github.com/william-lbn/control-plane/blob/932f5adbd9db5babce1ad05aa280cc34e452e193/docs/FUNCTIONS-BACKING.md),
[Bootstrap contracts and evidence](https://github.com/william-lbn/control-plane/blob/932f5adbd9db5babce1ad05aa280cc34e452e193/docs/FUNCTIONS-BOOTSTRAP.md),
[Runtime recovery and atomic publication](https://github.com/william-lbn/control-plane/blob/932f5adbd9db5babce1ad05aa280cc34e452e193/docs/FUNCTIONS-PUBLICATION.md),
[Functions implementation](https://github.com/william-lbn/control-plane/blob/main/docs/FUNCTIONS-IMPLEMENTATION.md)
and [model](https://github.com/william-lbn/control-plane/blob/main/docs/FUNCTIONS-MODEL.md).
HA/DR, shared-storage stability and whole-chain TLS retain their independent
[production gates](PRODUCTION-GATES.md).
