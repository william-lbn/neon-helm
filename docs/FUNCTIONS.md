# Functions: deployment boundaries and verification

## Current contract

The control-plane source selected by release 0.1.11 exposes branch-scoped,
authorized read-only Function definitions and deployment history. Its Console
has a Functions page. Migration 019 installs definition, deployment and
instance metadata constraints. The invocation ledger and route publication
remain to be implemented. Migration 020 adds immutable private backing
receipts for exact environment Secret UID/MAC/key version and deployment scope.
Migration 021 adds immutable instance bootstrap Secret identity receipts. Neither
migration adds a deployment/invocation route or enables execution.
Execution remains disabled: installing this
release does not create a Function VM or make a public invocation URL available.

The selected source adds private Service/VM recovery and atomic PostgreSQL
publication methods. Linux quality passed 593 checks; the same archived source
passed three actual MinIO/Kubernetes checks, including a lost Service reply and
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

1. Connect the accepted immutable artifact/environment/bootstrap primitives and leased
   private backing receipt repository to the real deployment Driver. The real
   MinIO conditional-write collision and Kubernetes unknown-create recovery
   checks passed independently; the actual bootstrap Secret additionally retained
   its original UID, certificate and keys after a lost POST acknowledgement.
   They do not constitute product deployment. Migration 021 stores only the
   private immutable bootstrap receipt, with no execution admission or route.
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
[Backing contracts and evidence](https://github.com/william-lbn/control-plane/blob/932f5adbd9db5babce1ad05aa280cc34e452e193/docs/FUNCTIONS-BACKING.md),
[Bootstrap contracts and evidence](https://github.com/william-lbn/control-plane/blob/932f5adbd9db5babce1ad05aa280cc34e452e193/docs/FUNCTIONS-BOOTSTRAP.md),
[Runtime recovery and atomic publication](https://github.com/william-lbn/control-plane/blob/932f5adbd9db5babce1ad05aa280cc34e452e193/docs/FUNCTIONS-PUBLICATION.md),
[Functions implementation](https://github.com/william-lbn/control-plane/blob/main/docs/FUNCTIONS-IMPLEMENTATION.md)
and [model](https://github.com/william-lbn/control-plane/blob/main/docs/FUNCTIONS-MODEL.md).
HA/DR, shared-storage stability and whole-chain TLS retain their independent
[production gates](PRODUCTION-GATES.md).
