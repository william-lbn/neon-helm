# 0.1.19 — Complete retained Functions environment hydration

Control runtime/source: `bf0dd9e41f9d3d65e321958d16c0c255f8a8b2ad`.
Public Linux CI `38212771326` passed all 13 jobs; the Go/PostgreSQL receipt has
722 passing checks, zero failures and zero skips. Seven OCI images were checked
anonymously on Linux and imported serially on all three laboratory nodes.
The own-fork Neon/Postgres/autoscaling and fixed Functions guest images remain
unchanged. This release includes the Worker-only Service retirement Role from
[0.1.18](RELEASE-0.1.18.md).

The retained source loader now hydrates the environment names inventory and
exact project/branch backing scope. The recovered Secret must still match its
MAC, original UID and names inventory. This fixes the real UI recovery failure
where the inventory was omitted and the integrity check rejected a nonempty
environment. It does not remove that check. Eleven focused Linux PostgreSQL
checks include nonempty inventory hydration and mismatched-name rejection.

The original failed guest's stop Operation has already completed through the
UI after the RBAC repair; VM and Service were normally retired. The protected
browser continuation uses `completed_suspend_operation_id` to verify that
checkpoint and deploy the retained source without another stop, new project,
new grants, replacement SQL credentials or another ZIP upload. A new
deployment/boot is expected after the acknowledged original retirement.

The original failed test receipts remain distinct from recovery. The chart-only
permission patch also preserved all business Secret/PVC UIDs. Its initial audit
classified Helm's default old-release Secret garbage collection as a failure;
the resumed **read-only** audit documented those history records and confirmed
business identities and the actual authorization boundary. Helm was not replayed
for that audit. Private original values/manifests and test evidence are retained.

**Native Functions UI invocation acceptance remains pending.** Continue from
the completed-stop checkpoint, then independently verify guest publication,
real Proxy SQL identity/read/write, schema denial, safe responses, manual stop,
configuration-only redeploy and NOLOGIN/retained deletion. Source/CI/chart gates
are not substitutes for that live result. All unrelated production and official
parity gates remain as defined in [the recovery contract](RELEASE-0.1.17.md).
