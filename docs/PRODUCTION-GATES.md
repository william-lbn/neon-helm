# Production qualification gates

## 1. Deployment discipline versus product qualification

The charts provide source/image locks, schemas, dependency ordering, rollout
checks, external Secret references, PVC retention, Safekeeper disruption budget,
nonroot control workloads, separate API/Worker/Web, public Linux CI, immutable
attempt records and selective safe adoption. These controls are necessary but
do not certify the current self-hosted product for production.

Only the explicitly acknowledged `lab` profile is provided and accepted by the
stack tool. There is no misleading `production.yaml`. Configuring external HA
PostgreSQL/S3 is supported by component values but does not make unimplemented
fencing, TLS, IAM or DR gates pass.

## 2. Independent gates

| Capability | Current boundary | Required evidence before production |
|---|---|---|
| Project/branch/Endpoint, SQL and Proxy wake | current Go product implemented | real UI + external SQL regression after each release |
| Read Computes, manual/idle zero and wake | current single-adapter deployment | writer/reader independence, read-only rejection and cold reconnect |
| Cross-instance suspend/wake fencing | not certified; Adapter remains one replica | multiple API/Worker/adapter races, crash expiry, stale generation rejection, admitted SQL leases |
| Authorization | current membership/permission and invited Console registration implemented | complete adversarial access matrix, enterprise identity/email verification; branch Managed Auth separate |
| HA/DR | not qualified; local-path and singleton DB/MinIO/Pageserver | node/zone failure, metadata failover, storage redundancy, recovery exercises and measured RPO/RTO |
| Shared host storage stability | repeated simultaneous I/O stalls; 2026-10-08 etcd fdatasync maxima 21.875/30.589/26.358 seconds | host/driver/virtual-disk cause and mitigation, independent I/O/failure domains, sustained flush/SQL latency qualification; successful rerun is insufficient |
| Historical new-branch restore | timestamp/LSN, native retention lease, durable intent and UI implemented | release-specific real storage/UI acceptance; long-window GC races, relocated/sharded storage |
| Complete PITR and deletion | historical new-branch restore, protected retained deletion and seven-day project recovery implemented; in-place reset, physical GC, TTL and failed-resource deletion unfinished | release-specific UI service/credential retirement and recovery; endpoint cutover/rollback, Backend consistency, GC and distributed races separately |
| Fractional CPU / full memory downscale | upstream capability must be separately qualified | guest/cgroup/QEMU reconciliation, low-memory load, OOM/coldboot recovery and quota accuracy |
| Trusted TLS | internal gateway certificates exist; Auth verifies an explicit Proxy CA and DNS identity; browser/control DB/storage lab exceptions remain | trusted external DNS/certificate, Proxy verify-full, database/backend transport trust and rotation |
| Data API | first branch Driver/UI + real PostgREST/RLS present | broader production API/SQL isolation, complete backend lifecycle, trusted TLS |
| Branch Managed Auth | Go Driver, maintained Better Auth runtime, React UI and dedicated PostgreSQL tests implemented; release-specific Neon UI acceptance is separate | trusted browser TLS, SMTP/OAuth/MFA, comprehensive isolation, branch/restore lifecycle and HA |
| Product Object Storage | branch REST Driver/UI, immutable backing bytes, clone directory, conditional writes and signed downloads implemented; real release acceptance recorded separately | external S3 interoperability, multipart, scoped storage credentials, verified physical GC, distributed isolation/TLS/HA/DR |
| Functions | runtime/Driver/UI execution not implemented | Node.js 24 microVM isolation, branch deployment/inheritance, secret injection, HTTP/streaming, idle lifecycle, limits and independent real tests |
| AI Gateway inference | application credentials and authorization checker only | real provider credential onboarding, model routing, inference/streaming, limits, billing and isolation |

The core S3/MinIO layer stores Neon database pages/WAL; it is not the customer
Object Storage product. A route adapter is not an Auth backend. Credential UI
is not an inference gateway. Do not enable unsupported Backend capabilities
in the UI just because their image names appear in a build manifest.

## 3. Required platform hardening

* Metadata and controller PostgreSQL require independent, authenticated HA
  databases and verified backups; source credentials must never enter values.
* Replace legacy MinIO images with maintained external redundant S3 only after
  compatibility/restore validation. Image locks preserve current behavior and
  do not imply current vulnerability-free upstream support.
* Storage Controller `--dev` and current unauthenticated storage RPCs are lab
  exceptions. Proper JWT trust/public keys, tokens and all client integrations
  require implementation and an end-to-end acceptance gate.
* Scope ingress and PostgreSQL exposure; NodePorts/HTTP Console are lab values.
  Production needs trusted DNS/TLS, cookies, identity, rate limits and audit.
* Add measured NetworkPolicy coverage and admission ownership boundaries. CNI
  enforcement and host-level VXLAN/KVM traffic need explicit tests. Do not
  blanket-apply a policy that breaks necessary storage or VM paths.
* NeonVM's hostPaths, KVM/device privileges, kernel modules and VXLAN permissions
  are deliberate platform exceptions. They cannot run under generic restricted
  Pod Security rules. Apply least privilege to application namespaces separately.
* Safekeeper PDB protects voluntary disruptions only. Do not restart all three
  simultaneously; keep quorum and separate node placement. Drain one node at a
  time and stop if fewer than two Safekeepers remain healthy.

## 4. Compatibility policy

The scheduler was built for Kubernetes 1.31, while current lab is RKE2 1.36.4.
The chart uses an explicit experimental/untested override for that lab. Lock
the verified combination before evolving it; run integration and failure tests
when changing Kubernetes, CRDs, image commits or PostgreSQL majors. A successful
template render proves no runtime or data compatibility by itself.
