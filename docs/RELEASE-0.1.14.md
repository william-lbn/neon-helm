# 0.1.14: native Functions execution preview

Control source: `975b6468f0ff20be3e1da3cdef5dc9d0e01fc4dc`.
GitHub Linux CI `38189564324`: all 13 jobs succeeded; actual Go/real SCRAM
PostgreSQL result 706 pass, 0 fail, 0 skip. Seven anonymous OCI manifest/config/
platform/source/license checks passed. Image references are locked in
`locks/control-plane-975b646.json`. The 46 own-fork Neon/autoscaling/PG16 images
remain unchanged.

New code connects native Function creation, immutable ZIP/environment deployment,
private TLS artifact distribution, leased Go Worker reconciliation, original
restricted SQL credentials, authenticated JSON Console invocation, explicit manual
instance stop/redeploy and retained deletion. API/Worker/Web remain separate.
Worker-only issuer keys never mount into API/Web. Migration 023 permits retired
slug reuse without reusing identity/credentials. New API/contract/lifecycle checks
passed 27 targeted Linux tests; frontend build and source Helm RBAC checks passed.

## Opt-in configuration

Execution defaults to disabled. Provision immutable operator trust/config Secrets
using the [control-plane operator guide](https://github.com/william-lbn/control-plane/blob/975b6468f0ff20be3e1da3cdef5dc9d0e01fc4dc/docs/FUNCTIONS-NATIVE-PREVIEW.md).
Apply `profiles/examples/functions-preview.json` **only after** those prerequisites
exist. This overlay requires separate single API/Worker processes and product
Object Storage. It creates a private ClusterIP artifact service on TLS port 8790.
Proxy CA projection contains only the public certificate. No private material is
embedded in values, images or chart packages. Explicit SQL owner grants are
required; the Driver never silently revokes shared PUBLIC privileges.

The lab Auth TLS server name is corrected to the actual `lab.neon.local`
certificate identity, matching the previously verified deployment override.

## Acceptance is separate from CI

The actual `functions-native.spec.ts` Linux browser suite must prove Console ->
API/Worker -> original microVM -> Proxy -> real Neon SQL read/write; schema denial;
non-executable customer HTML; preserved application errors; original VM/Runner
retirement; config-only redeploy with retained data/role; and deleted SQL login.
Record actual source, chart, image digests, original failed results and new results.
CI/Ready Pods do not substitute for that receipt. Deployment/live acceptance is
pending until its separate report is added.

Public raw HTTP/SSE/WebSockets, automatic idle zero/wake, triggers, complete
function branch/PITR inheritance, continuous certificate renewal, external
execution fencing, HA/DR and complete production transport remain independent
gates. The current guest leaf lifetime is two hours and requires explicit
retirement/redeployment. This preview does not claim Neon feature parity or
production admission. Original test/data/Secret/backing evidence must be retained;
only exact owned retired runtime resources are normally collected.
