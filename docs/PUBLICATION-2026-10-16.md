# Source and image publication boundaries — 2026-10-16

## Source revisions

| Repository / branch | Source | Scope |
|---|---|---|
| `william-lbn/control-plane`, `main` | `b4ad4f4` | Locally accepted control-plane batch, through OpenAPI 0.37.0; Go API/Worker and TypeScript Console |
| `william-lbn/autoscaling`, `fix/runner-cgroup-cpu-limits` | `172092424135c565a7e49cb696201daa8e15c41b` | Apply real QEMU cgroup quota before acknowledging CPU changes |
| `william-lbn/neon-helm`, `main` | 0.1.31 source candidate | Consistent ten-chart metadata, public 0.23.0 control image locks and explicit runner cgroup configuration |

The runner fix is based on the exact original deployed revision
`c0052f5f2d38fce6c70e448f3f1ee2ee239a0a93`. No Neon Rust change is included.
Control-plane feature checks and retained evidence are described in its
[`DELIVERY-2026-10-15-BATCH-CURRENT.md`](https://github.com/william-lbn/control-plane/blob/b4ad4f4/docs/DELIVERY-2026-10-15-BATCH-CURRENT.md).

## Reproducible deployment baseline

The active stack selects `locks/control-plane-5449a11.json`: all eight images
come from control source `5449a11a8809767aca0ea934ef94cf7d7e7db10d`, image CI
`38581455583`, OpenAPI 0.23.0. These existing public digests were verified for
anonymous pull. The [OTP delivery receipt](DELIVERY-2026-10-14-AUTH-OTP.md)
records actual deployment and eight SMTP/browser acceptance groups.

The newer 0.37.0 control-plane batch and fixed runner were built and verified
inside the local Linux environment. Public profiles do not reference temporary
`neon.local` images. Cloning this Helm repository therefore does not reproduce
those newer local runtime features automatically. Enabling the runner cgroup
flag alone does not fix the old public runner's dynamic CPU callback.

## Next public image release

1. Publish images from the pushed control-plane commit and the exact runner fix
   commit using their own Linux pipelines or equivalent audited Linux builds.
2. Verify immutable image digests, source revision labels, target platform and
   anonymous pull. Record each component; do not infer publication from a Git push.
3. Update image locks, profiles and matching chart templates/app versions together.
   Run Linux source, render/package and focused compatibility gates.
4. Upgrade the existing stack with retained Secrets/PVC identities and perform
   the changed-feature UI acceptance before tagging a new unified release.

No secret, private test fixture or Python verification script belongs in the
public source. Pushing these sources does not change the running cluster,
issue a release tag, or close the independent production gates.
