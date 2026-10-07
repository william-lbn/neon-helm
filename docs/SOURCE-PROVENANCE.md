# Source and version provenance

| Repository | Locked revision |
|---|---|
| william-lbn/neon | `1f30cd02092dc151f5d00aef97e7c629105b454b` |
| william-lbn/autoscaling | `c0052f5f2d38fce6c70e448f3f1ee2ee239a0a93` |
| william-lbn/postgres (v16) | `a42351fcd41ea01edede1daed65f651e838988fc` |
| william-lbn/control-plane | `6e778bbc631f6fa30a7543dc274789beb70afb0f` |

Data-plane release tag:
`2026.09.30-162021-1f30cd02092d-r36742713551-a1`.
Every deployment profile uses immutable registry digests. Consult
`locks/neon-fork-20260930.json` for the full 46-image source/build distribution
and `locks/control-plane-6e778bb.json` for the six published control images.
These are fixed current deployment versions, not an assertion of future latest.

The initial chart imports came from the existing validated deployment bundle
and the public control repository. `locks/source-imports.json` records baseline
paths and **import-time** hashes; subsequent chart changes are tracked by Git.
It is not a current-worktree checksum manifest. The NeonVM CRDs are the legacy
deployment schema derived from the earlier upstream bundle (v0.49.1), not
claimed to be newly generated from `c0052f5f2d38`. Existing CRDs are preserved.

`locks/adapter.json` records the Go adapter source revision and image digest.
The adapter implementation is in the public control-plane Go module; this chart
contains no adapter Python source or mounted code ConfigMap. Two optional legacy
proxy/resizer Python tools remain disabled in the standard lab profile for older
laboratory installations. They are not the native product control path. No private
Python verification/SSH tools are published. Historical 0.1.2 packages retain the
former adapter for explicit rollback; current Go tokens/routes/receipts preserve
existing resource identities. Go adapter single-replica status does not certify HA.

This chart repository changes packaging, configuration and deployment tooling.
It does not modify forked Neon, PostgreSQL or autoscaling runtime source in
this release. Future bug fixes must be reviewed against logs/source, committed
in their owning fork, rebuilt with traceable digests, then updated here with
compatibility and acceptance evidence.

Helm/Node/actionlint are pinned in `locks/tools.json`; the lockfile contains npm
package integrity. Linux local cached E2E Node may be a newer patch in the same
major; the actual version must appear in local evidence. GitHub CI uses the
explicit Node version in its workflow and Helm checksum installer.
