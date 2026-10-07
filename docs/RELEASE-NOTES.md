# Neon Helm releases

## 0.1.2

Historical PostgreSQL recovery to a **new branch** is implemented in the Go
control API/Worker and React Console. Timestamp/LSN resolution uses the native
Pageserver retention boundary and LSN lease before accepting intent. Worker
retry retains the resolved point and verifies exact timeline ancestry. Current
catalog intents are not projected into historical data. Migration 013 stores
restore provenance. OpenAPI 0.7.0 exposes 46 paths and 63 operations.

The chart adds `api.pitrEnabled` (default false), shared by API and Worker;
enabling it without resource creation is rejected. The locked lab profile opts
in after real Linux restore tests. Ten chart packages share version 0.1.2;
forked Neon/PostgreSQL/autoscaling sources and their 46-image lock are unchanged.
The acceptance report records exact control-image source/digests and fresh
regression results. In-place restore, Time Travel Assist, full Backend recovery,
deletion/GC, HA/DR, fencing, fractional CPU, full RAM downscale and trusted TLS
retain independent implementation or qualification gates.

A real published-image UI test exposed a missed-404 race during suspend/cold
wake. The Worker now observes deletion of the original VM generation: an owned
successor UID is accepted without mutating it, and missing/foreign identities
fail. The Linux Go gate includes this matrix; the live restore suite requires
the original suspend Operation to succeed after the cold wake. This correction
does not claim full cross-instance fencing.

## 0.1.1

The control product is locked to `f90c9370db583e71796c4c6ad44e51c6ea354f43`:
Console invitations, invited registration, existing-account acceptance and
permission revocation, bounded accepted-Operation observation recovery and
Linux UI transient-read fault injection. All five control images have public Docker Hub digests;
API/Worker/Web and native Data API use this one source revision. See the release
acceptance report for Linux CI, real UI and live manifest/provenance checks.

The optional static Compute chart adds `compute.enabled=false`. Only its VM is
removed; Service identity, external config and Neon persistent data are retained.
The default stack still creates no static Compute. A Helm gate verifies
retirement renders zero VMs and retains one Service. This does not implement
project deletion, garbage collection or managed Endpoint fencing.

Empty custom-resource lookup now preserves list semantics after the last VM
is retired. The final zero-resource audit requires removal of both managed
VMs and their runner Pods. Resource retirement/incident guidance preserves
failed attempts, database data, rollback values and external credentials.

## 0.1.0

Initial independent chart repository. Ten charts unify the Neon data plane,
NeonVM/autoscaling, metadata/Adapter and Go API/Worker/TypeScript Console.
Eight default releases have deterministic deployment order; dynamic Computes
and native branch Data API remain control-product owned. Images and sources are
locked; Secret state is external; PVCs are retained; Linux CI checks rendering,
schemas, ownership safety and packaging. See deployment and upgrade runbooks.

This release is a laboratory candidate. See PRODUCTION-GATES.md for unfinished
features and unqualified HA/DR, fencing, PITR, memory/fractional CPU and TLS.
