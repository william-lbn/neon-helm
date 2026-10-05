# Neon Helm

Versioned deployment source for self-hosted Neon, NeonVM, upstream autoscaling,
the Go control API, independent Worker and TypeScript Console.

**Status: laboratory release candidate. Not certified for production.**
The repository applies production-oriented deployment discipline, but the
underlying product still has independent [production gates](docs/PRODUCTION-GATES.md).
Installing a chart does not implement Neon's proprietary Backend services.

## Start here

1. [Architecture and component coverage](docs/ARCHITECTURE.md)
2. [New Linux cluster deployment](docs/DEPLOYMENT.md)
3. [Existing cluster migration, backups and rollback](docs/UPGRADE.md)
4. [Linux CI and UI end-to-end reproduction](docs/TESTING.md)
5. [Security, persistence and production requirements](docs/PRODUCTION-GATES.md)
6. [Version/source ownership](docs/SOURCE-PROVENANCE.md)
7. [Actual deployment and UI acceptance](docs/ACCEPTANCE-2026-10-05.md)

```bash
git clone https://github.com/william-lbn/neon-helm.git
cd neon-helm
npm ci --ignore-scripts --no-audit --fund=false
bash tools/install-helm.sh "$PWD/.local/bin"
export HELM_BIN="$PWD/.local/bin/helm"
node tools/stack.mjs plan
```

This prints the deployment order and prerequisites; it changes no cluster state.
The [stack contract](stack/stack.json) has eight independently upgradeable
releases. Two optional charts cover the retained static Compute and a standalone
Data API gateway. Native Computes and branch Data API workloads are created by
the control-plane Drivers, not permanently installed by Helm.

## Repository layout

| Path | Purpose |
|---|---|
| `charts/` | Ten independently packaged charts, schemas and commented defaults |
| `profiles/lab/` | Public, digest-pinned component settings; no credentials |
| `locks/` | Source revisions, full image distribution, control images and tool checksums |
| `stack/stack.json` | Release identity, dependency order and rollout checks |
| `tools/` | Linux validation, bootstrap, maintenance and packaging |
| `tests/` | Ownership, dependency, persistence and schema rejection contracts |
| `docs/` | Deployment, upgrade, test and qualification runbooks |

Images are pulled from the public `williamluckyli` Docker Hub repositories at
fixed digests. The chart repository does not rebuild these images. GitHub CI
validates all charts on Linux; a version tag publishes chart packages and hashes
as GitHub Release assets using the repository's own `GITHUB_TOKEN`.
No Docker Hub publishing credential is needed for chart publication.

After a versioned release is published, the standard Helm repository endpoint is:

```bash
helm repo add neon https://github.com/william-lbn/neon-helm/releases/download/v0.1.0
helm repo update
helm search repo neon
```

Use the stack tool for the complete ordered installation; installing one search
result does not install all external prerequisites or dependent releases.

The initial deployment retains existing resource names and namespaces. Only one
stack is supported per cluster. This preserves existing data identities; it is
not a multi-install or cross-region HA architecture.

See [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md) and [LICENSE](LICENSE).
