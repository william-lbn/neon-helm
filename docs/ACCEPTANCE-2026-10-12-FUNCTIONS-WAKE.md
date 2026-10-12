# Explicit Functions wake: actual Linux UI acceptance

## 1. Result and exact release

**Passed as a preview slice.** Runtime and test source are both
`0198f7c8249d4d3755f62b685a0db0c15ff7301c`, OpenAPI 0.14.0, unified Helm 0.1.21.
Linux browser Job `publication-ui-20261012113626` completed on 2026-10-12 at
19:38:00 Asia/Shanghai (11:38:00 UTC). This was the first actual run of this new
wake suite, on the deliberately retained database from the native slice.

Public Linux CI `38223473074`: 13 successful jobs, 723 Go/PostgreSQL passing
checks, zero failures/skips. Seven OCI images were anonymously verified against
the exact source and imported serially 21 times across three nodes. Ten-chart
quality and the eight-stage unified deployment passed; full prior values and
business Secret/PVC identity were preserved. Own-fork data-plane images and the
fixed Functions guest image were unchanged.

## 2. Actual checkpoints

The owned Function `fnc_c85d03c6289038da`, slug `wake`, ran on the original
project `prj_6f3c51bd15b772e3`, branch `br_6f3c51bd15b772e3`, Writer
`ep_6f3c51bd15b772e3`. The focused UI suite recorded five checkpoint groups:

1. Create/deploy one owned Function; record successful immutable source/env and
   authenticated original guest boot.
2. Stop the original guest and Writer, then click **唤醒保留版本**. The request
   body is exactly `{}` despite unsaved environment editor changes. Observe a
   different boot instance/deployment and newer generation with unchanged bundle
   digest and environment names.
3. Replay the captured wake key/body/version after completion: return the same
   Operation, without another instance/generation. Reuse that key on the code
   deployment route: 409 conflict. New-key stale version: 412 rejection.
4. A separate actual Function invocation reads real Neon SQL through the Proxy.
   It returns the original Function SQL role, retained row count one and original
   environment value `wake-retained`, rather than the unsaved UI value.
5. Normally stop/delete the owned Function and suspend the Writer. The collector
   observes no managed Compute VM or Runner Pod. Original data and all evidence
   remain; nothing is physically purged.

## 3. Reproduce and qualification limits

Use the protected Linux `functions-wake.spec.ts` workflow choice and retained
owner fixture described in the [exact API, data, recovery and UI contract](https://github.com/william-lbn/control-plane/blob/0198f7c8249d4d3755f62b685a0db0c15ff7301c/docs/FUNCTIONS-WAKE.md).
Test credentials stay in operator-controlled files outside Git; the sample is
packaged on Linux. Private SSH/Python transport is not part of the product.

The durable Worker action is `deploy_function`; audit action `resume_function`
records this distinct user intent. It starts a new boot from retained source,
not the original in-memory process. Automatic idle/cold wake, public HTTP/SSE/WS,
triggers, backend cloning, logs/metering, issuer rotation, distributed fencing,
HA/DR and full official parity remain independent gates.

Private immutable receipts are in `20261011-functions`: `functions-wake-focused-202610121830`,
`functions-wake-web-202610121840`, source proof/push, public CI/registry/node imports,
Helm quality/deployment and `functions-wake-ui-202610121948`. Their folder labels
identify the delivery attempts; the actual Job and receipt timestamps above are
authoritative.
