# 0.1.15: Functions HTTP Console repair and original-fixture continuation

Control source `f1cd9597f228d3b951821d0a72251e4394b05b2e` repairs the Functions
authoring page to reuse the existing CSPRNG request-key helper. HTTP laboratory
origins expose `crypto.getRandomValues` but not secure-context-only
`crypto.randomUUID`; the previous direct calls prevented mutation dispatch.
Production transport requirements remain unchanged.

Original real Linux UI Job `publication-ui-20261012011916` created project
`prj_6f3c51bd15b772e3`, its Writer and explicit owner SQL grants, then blocked
before any Function was created. Read-only Linux browser diagnosis independently
confirmed the missing API. Original Job/Pod/logs/checkpoint/private fixture were
archived; only its owned UI Job was normally retired with UID/RV preconditions.
The original database/data/credentials remain. Its single Compute was normally
suspended through the real UI before the next rollout, releasing its VM.

The updated `functions-native.spec.ts` accepts only an explicit protected
pre-Function checkpoint. It reuses the original project/Writer/password and
checks original SQL state before proceeding. It does not repeat project/database
creation or grants. Function creation response observation is bounded to avoid a
client-side failure silently waiting for the entire test deadline. Independent
post-delete SQL assertions verify NOLOGIN and retained rows.

All 13 GitHub CI jobs for `38193063461` succeeded, including actual Go/PG and
TypeScript. Fresh runtime image digests, Helm gates and actual UI continuation
receipts are separate release checks. Keep the original interruption and any
later failure; successful continuation is not an all-first-pass claim.

The architecture/limits/operator prerequisites in [0.1.14](RELEASE-0.1.14.md)
still apply. Functions remain an explicit preview: no claim of public raw
HTTP/SSE/WebSockets, automatic idle zero/wake, triggers, complete branch/PITR
inheritance, external fencing, HA/DR or full production transport qualification.
