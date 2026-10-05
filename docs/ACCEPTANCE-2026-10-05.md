# Initial Helm repository acceptance — 2026-10-05

## 1. Conclusion

The eight-stage stack was deployed successfully on the existing three-node
Linux RKE2 environment, then the same configuration was applied again and
verified. The runtime uses the owner's locked fork/control images. No forked
Neon/Autoscaling/PostgreSQL runtime code was changed by this packaging work.

This is an independently repeatable laboratory deployment with production-
oriented controls. It does **not** certify full Neon SaaS feature parity,
production security, HA/DR or data-plane recovery.

## 2. Actual results

| Gate | Result | Evidence identity |
|---|---|---|
| Linux chart quality | PASS: 10 charts lint/render/package; unknown setting rejection; five unsafe configuration cases | `helm-quality-1791213322` |
| Tool contracts | PASS: 5 tests, 0 failed/skipped | same Linux quality Job |
| GitHub Linux CI | PASS for initial code commit `83b822d` | [run 37331378852](https://github.com/william-lbn/neon-helm/actions/runs/37331378852) |
| GitHub Linux CI with audit/report | PASS for `83d4128` | [run 37332838769](https://github.com/william-lbn/neon-helm/actions/runs/37332838769) |
| GitHub Linux CI with fail-closed fork image defaults | PASS for `5b3be23` | [run 37333848969](https://github.com/william-lbn/neon-helm/actions/runs/37333848969) |
| Ordered upgrade | PASS: eight releases Ready | protected `apply-attempt1` and `verify-attempt1` |
| Repeated same-config upgrade | PASS: eight releases Ready again | protected `apply-attempt2` and `verify-attempt2` |
| Durable identity | PASS: all original PVC UIDs/bindings retained; external Secret UIDs/data retained, routes allowed to reconcile | protected `audit-attempt1` |
| Runtime image audit | PASS: 29 declared container/init-container image references match desired digests | protected `audit-attempt1` |
| Public source/release match | PASS: anonymously cloned `5b3be23`; all eight release manifests and separately stored hooks match rendered public source | protected `public-source-audit-attempt2` |
| New-lab credential bootstrap | PASS: eight generated external Secret contracts in a protected directory; not applied to current cluster | same public-source check |
| Native UI + Worker recovery | PASS: project/branch, real Proxy SQL, inheritance/isolation, suspend/cold resume, monitoring, same queued Operation after Worker restart | `publication-ui-20261005150958` |
| Data API UI | PASS: real RLS reads/writes, invalid identity rejection, idempotency, disable/reenable, manual/automatic zero and first-request cold wake | `publication-ui-20261005151226` |
| Application credentials UI | PASS: lineage/model checks, one-time secret, replay, rotation/revocation and reload | `publication-ui-20261005151932` |
| Metadata restore | PASS: isolated PostgreSQL restored pre-upgrade dump, 24 projects / 64 branches / 73 Endpoints / 375 Operations / 24 tables | `helm-restore-1791213483` |
| Test resource completion | PASS: managed test VM count 0; retained original `vm-neon-compute` and historical release unchanged | protected runtime audit |

Test projects `prj_6fd630399b4f2f21` and `prj_fad40f5c35c08ca0` remain available
for reconnection using protected private fixtures. Evidence/screenshots and
database passwords were retained outside this public repository. No public
source or release asset includes an admin password, private dump or kubeconfig.

## 3. Migration details

Previously scripted metadata DB/Adapter resources, managed Pageserver config
and PVC, and public Proxy Service were adopted only after readonly checks of
their current identity/content. External route/credential state was not adopted
or reset. All eight releases now use the normalized 0.1.0 chart series.
The serving gateway uses an image without a host binary mount.

Source/runtime revisions and immutable image digests are in `locks/`. Local
verification used Node 24.20.0 and Helm 3.18.6; GitHub CI explicitly installs
Node 24.19.0 and checksum-verified Helm 3.17.3. Kubernetes is 1.36.4+rke2r1,
an explicitly acknowledged autoscaling compatibility exception.

## 4. Unrun or unfinished gates

This upgrade did not independently recreate an empty three-node cluster from
scratch, test two read Computes/vertical resize/catalog permissions again, or
run HA/DR, PITR, full deletion, fractional CPU, full RAM downscale, distributed
fencing, comprehensive tenant adversarial tests or full trusted TLS. Their
historical results are not relabeled as this release's acceptance.

Auth, Functions, customer Object Storage and AI inference are not implemented
Neon-equivalent services by these charts. Application credential authorization
is not provider inference. See [PRODUCTION-GATES](PRODUCTION-GATES.md) for the
required implementation and evidence. The metadata restore above is not WAL/
object-store disaster recovery. Failure records from chart/tool validation were
retained with their repair attempts.

## 5. Reproduction and evolution

Follow DEPLOYMENT.md for bootstrap inputs, UPGRADE.md for safe live migration,
TESTING.md for pinned Linux TypeScript browser tests and fixture preservation.
Change an image only after reviewing its owning source commit, compatible CRDs,
configuration and durable state. Submit code, migration and actual test proof
together; keep production qualification separate from Helm readiness.
