# 0.1.17 — Native Functions failed deployment recovery

## 1. Source and scope

Control source: `07c997b07b9e3e1f60c1ed9ccd34b5cc1cbf1a54`.
Public Linux CI: `38209377058`. Runtime images must match the immutable OCI lock
generated from that successful run. This candidate extends the Functions preview;
it does not qualify complete official feature parity, HA or external fencing.
The Neon/autoscaling/Postgres forks and fixed Functions guest image are unchanged.

## 2. Changes

- Explicit `cpuScalingMode: QmpScaling` matches the own-fork controller's
  immutable default. Full post-controller specification/UID checks remain;
  missing/foreign scaling modes are rejected.
- An existing unretired candidate blocks new deployments before backing writes
  and again in the admission transaction. Unavailable readiness cannot authorize
  an additional guest or bypass original-instance retirement.
- A first failed deployment can be recovered without uploading another ZIP:
  the original definition must be suspended, its owned stop Operation must have
  succeeded for the current generation/branch, and every candidate must be
  retired. Immutable environment MAC/UID and code digest are still verified.
- Recovery keeps the definition, restricted SQL role/password and data. It
  creates a new deployment/generation/boot after normal original VM/Runner
  retirement. Original failure history, source and Secrets remain retained.
- Runtime identity/specification failures now have a specific safe Operation
  code, without logging credentials or private bootstrap content.

## 3. Operator recovery steps

1. Preserve the failed Operation ID, code digest, deployment ID and original
   resource UIDs. Fix the identified prerequisite; do not rewrite metadata.
2. If no guest was created, retry the original failed Operation from Operations.
3. If the one-shot guest bootstrap failed, open Functions, select the original
   function, click **Stop function instance** and explicitly acknowledge stopping
   background work. Wait for the stop Operation to succeed.
4. Leave ZIP unselected and environment input empty; click **Deploy function
   version**. This reuses the eligible retained immutable source/environment.
5. Invoke through the Console. Verify real SQL identity, read/write, another
   schema's denial and application errors. Stop, change only the environment and
   redeploy; confirm previous data and SQL identity remain.
6. Delete the test function and independently confirm its owned SQL role is
   NOLOGIN and user data remains. Suspend the completed test Compute from its UI.

Use the existing immutable Functions operator Secrets during the chart upgrade.
Never regenerate signing/MAC keys, patch a foreign UID, force-delete a VM, or
clear failure receipts. A completed metadata stop in a disposable test is not
proof of actual VM/Runner absence; the live product test must establish that.

## 4. Verification state

Focused Linux VM specification tests passed 20 checks. The retained-source
PostgreSQL gate passed 10 checks, covering missing/incomplete stop, live candidate,
wrong generation/branch, cancelled deployment and accepted original retirement.
The corrected canonical fixture retained the earlier failed test record.
React/TypeScript/Vite verification passed on Linux. Public CI, anonymous OCI,
three-node serial imports, Helm QA/deployment and actual browser recovery receipts
are separate mandatory gates. **Live Functions acceptance remains pending.**

Public HTTP/SSE/WebSocket ingress, automatic Functions idle/wake, logs/usage,
triggers, seamless replacement, backend inheritance/cloning and issuer rotation
remain subsequent slices. No real provider inference is claimed without model
credentials. Current hardware does not qualify HA/DR or shared-disk load gates.
