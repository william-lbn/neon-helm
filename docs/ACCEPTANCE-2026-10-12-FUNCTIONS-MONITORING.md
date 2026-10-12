# Functions runtime monitoring: Linux UI acceptance

## Result and identity

**Passed as a preview slice.** Deployed control runtime
`be557e0742ca8d2fb9030aa5f17a6f9936811acb`, OpenAPI 0.13.0, unified Helm
0.1.20. Public Linux CI `38219164757`: 13 successful jobs, 723 Go/PostgreSQL
checks, zero failures/skips. Seven OCI references were anonymously verified;
21 serial imports on three nodes, chart quality and the eight-stage deployment
completed with business Secret/PVC identity preserved.

The first Linux browser Job `publication-ui-20261012075619` passed the real
deployment, authenticated supervisor, activity and stop checks. Its last
assertion incorrectly compared Endpoint **desired** `state` to `suspended`.
The independently inspected original suspend Operations succeeded and no VM
remained. The corrected test checks `observed_state`; an Endpoint may remain
desired `active` so a subsequent connection can wake it.

The continuation Job `publication-ui-20261012080929` completed at
2026-10-12 08:10:01 UTC. It reused the original suspended Function
`fnc_95a5b9b35a44e43f` in project `prj_6f3c51bd15b772e3`, verified its identity
and actual Compute absence, then completed the remaining UI checks. No original
invocation, grants or native write were replayed. Runtime stayed at `be557e0`;
test-only descendant `488a477654021fc6e4da35bed522c12a5b8ade86` changed exactly
`web/e2e/functions-observation.spec.ts`, with ancestry and diff verified.

## Verified behavior

- Unpublished/suspended observations return metadata only and do not infer health.
- Active UI status comes from the original VM/Service/bootstrap UID/spec and
  TLS/HMAC supervisor, with original boot and a late metadata freshness check.
- Repeated management observations do not increment invocation activity.
- One real restricted Neon SQL read returns the retained row and advances activity.
- Stopping clears the previous running health. Observing while the Writer is
  suspended does not create or wake a Compute.
- Owned Function deletion succeeds; the final collector observes no managed
  Compute VM or Runner Pod. Data and failed/successful test records remain.

## Reproduce and limits

Use the protected Linux `functions-observation.spec.ts` workflow suite and owner
fixture documented in the control repository's
[runtime observation contract](https://github.com/william-lbn/control-plane/blob/be557e0742ca8d2fb9030aa5f17a6f9936811acb/docs/FUNCTIONS-RUNTIME-OBSERVATION.md).
An explicit continuation additionally supplies the original stopped Function ID,
recorded checks and Operation IDs; its state/identity/Compute absence are checked
before any remaining mutation. Fixture/password files stay outside public Git.

This does not qualify automatic Function zero/wake, background-task metering,
historical CPU/RAM metrics, billing, HA/DR or full official parity. Those gates
remain independent. Both failed and resumed receipts are retained under private
`20261011-functions` evidence; they contain no published credentials.
