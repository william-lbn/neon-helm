# 0.1.20 — Authenticated Functions runtime monitoring

Control source/runtime `be557e0742ca8d2fb9030aa5f17a6f9936811acb`, OpenAPI
0.13 (96 implemented routes), public Linux CI `38219164757`: 13 successful jobs,
723 Go/PostgreSQL checks, zero failures/skips. Seven OCI images are independently
verified anonymously on Linux. The own-fork Neon/Postgres/autoscaling and fixed
Functions guest images are unchanged.

This slice adds an explicitly refreshed Functions monitoring card and
`GET .../functions/{slug}/runtime`. Active observations bind the published original
VM/Service/bootstrap UIDs, complete execution spec, TLS/HMAC supervisor and boot,
then recheck current parent/version/generation/instance. Inactive observations
read metadata only. Neither path invokes customer code, connects SQL, wakes a
Compute or increments invocation activity. Background work remains unmetered;
monitoring is not authorization for automatic retirement or a billing ledger.

The API excludes customer-provided NodeObservation, secrets, SQL URL, private
addresses and raw transport errors. The Console clears old observations on
selection/version changes or failures. Viewers may inspect runtime; authoring
and invocation controls require Editor/Admin, with server authorization retained.
Console invocation now shares the same identity/freshness verifier and keeps
single dispatch/no automatic replay.

The prior [native deployment/UI slice](ACCEPTANCE-2026-10-12-FUNCTIONS.md) remains
qualified at 0.1.19. The new focused `functions-observation.spec.ts` reuses its
owned database and retained row, creates one monitoring function and verifies
unpublished/active/suspended observations, unchanged activity for management
reads, activity after one real SQL read invocation, old health removal, no SQL
wake when paused, normal owned deletion and final Compute zero. It does not
repeat the previous whole native suite or its writes/grants.

**New runtime monitoring live acceptance is pending.** Use the exact Linux
receipt before promoting it. The protected Linux workflow now exposes native
and monitoring suites and packages the pinned example outside the checkout;
monitoring requires an operator-controlled private owner fixture path. No
password, Python transport or private evidence is shipped in the public code.
The [protocol, model, UI and limits](https://github.com/william-lbn/control-plane/blob/be557e0742ca8d2fb9030aa5f17a6f9936811acb/docs/FUNCTIONS-RUNTIME-OBSERVATION.md)
remain the development contract. All broader production gates remain independent.
