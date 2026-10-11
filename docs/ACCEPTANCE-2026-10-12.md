# 0.1.12 Linux deployment and product acceptance

## Exact distribution

Control source: `f0b63f5eed0fc412960b8b7dc7e8cda34abf916f`.
Release chart source: `57a08dd62e6db9649605acb9364821d373e9466f`;
immutable annotated tag `v0.1.12`. Seven images are selected by
`locks/control-plane-f0b63f5.json`; the 46-image Neon/autoscaling/PG16 distribution
is unchanged. API and Worker are separate, metadata is 21/21 migrations, and
Functions execution is disabled. This is a laboratory product acceptance, not
production admission or complete Neon feature parity.

## Supply chain and upgrade

- Linux dedicated Go/PostgreSQL/race/vet/build: 610 pass, 0 fail, 0 skip.
- Public [control CI 38156200281](https://github.com/william-lbn/control-plane/actions/runs/38156200281): thirteen jobs succeeded; eight artifacts actually downloaded and verified.
- Seven anonymous OCI manifest/config/platform/source/license verifications;
  twenty-one serial pull/CRI digest inspections across the three Linux nodes.
- Linux Helm: fifteen tool tests, ten charts, sixteen invalid configurations
  rejected and ten packages.
- Public Helm main CI `38157567226` and tag CI `38157598694` succeeded.
- Anonymous Linux consumer downloaded ten packages, index and SHA256SUMS from
  [the public release](https://github.com/william-lbn/neon-helm/releases/tag/v0.1.12), checking all hashes.
- Eight-step ordered live upgrade plus full manifest/Secret/PVC identity audit
  passed. Previous complete values/manifests and persistent identities remain
  preserved; no database, credential, PVC or WAL was recreated.

## Actual serial Linux UI matrix

| Committed browser suite | Passing checks | Qualification |
| --- | ---: | --- |
| Functions metadata | 8 | read-only/disabled-execution boundary |
| Native product | 13 | injected read faults, exactly one creation mutation, actual SQL/zero/cold wake |
| Managed Auth | 23 | actual registration/session/JWT/RLS/branch isolation/cold wake |
| Data API original recovery | 5 | original rows/RLS, explicit test issuer rotation, manual/automatic zero followed by first read, held deletion |
| Object Storage | 19 | real objects, conditional writes, signed downloads, inheritance/isolation/lifecycle |
| Timestamp/LSN restore | 11 | actual restored branch SQL and permission/inheritance negative cases |
| Endpoint deletion | 19 | Reader retirement, Writer replacement, other Reader and original recovery |
| Multi-Reader/project lifecycle | 22 | two real Readers, read-only SQL/zero/WAL, dependency protection and retained recovery |
| Backend credentials | 8 | actual credential lifecycle; inference not tested |
| Console invitations | 6 | actual invitation/registration/organization/permission positive and negative cases |

Total **134**, comprising nine normal scenarios (**129**) and one original
Data API continuation (**5**). This is not ten clean first-pass suites. Tests
use the exact committed control source above, rather than a changing worktree.
All test Compute VMs/runners were absent after the matrix.

Original Data API Job `publication-ui-20261011170839` failed during first cold
read while Adapter Kubernetes route reads were unavailable. Its original
project/branch/writer suffix is `aed92631751b9d8e`; original SQL/passwords and
failures were retained. Recovery Job `publication-ui-20261011172026` passed the
manual cold wake but failed automatic cold wake. A transport timeout was
resolved by read-only collection of its original Job/Pod UID; no mutation replay.
Recovery Job `publication-ui-20261011172835` subsequently passed five checks
with the original fixture. Failed partial checks are not added to the total.
These results do not prove uninterrupted service during the API outage.

Backend credential Job `publication-ui-20261011174437` actually succeeded.
Windows path-length failure affected collection only. Original UID-verified
read-only collection recovered its eight passing checks without running a new
browser test. Invitations Job `publication-ui-20261011174627` passed six.

## Resource retirement and next gates

Twelve exact owned terminal Jobs were normally deleted after full JSON/log
archive and UID/resourceVersion checks. No active Job, SQL data, Secret, PVC,
WAL or object was deleted. Test projects use retained deletion, not physical GC.
Follow [TESTING.md](TESTING.md) and [RESOURCE-RUNBOOK.md](RESOURCE-RUNBOOK.md).

The next control source adds PG16 provisioning-principal delegation, immutable
SQL Secrets and migration 022 identity receipts. Those are separate development
and deployment gates, not features installed by 0.1.12. Actual Function
deployment/invocation, branch SQL/manifest, ingress and execution UI still need
the integrated Driver. HA/DR, external fencing, complete physical GC, fractional
CPU/full memory reclamation, trusted end-to-end TLS and real upstream AI
inference are not certified. See [PRODUCTION-GATES.md](PRODUCTION-GATES.md).
