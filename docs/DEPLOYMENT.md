# Linux deployment runbook

## 1. Prerequisites and input contract

The current control images are pinned public GHCR mirrors of the same CI
publication also pushed to Docker Hub. Verify the selected seven-image lock
before deployment. A listening HTTP proxy does not prove its upstream is
working: this lab's chain is Linux `127.0.0.1:7890` → Windows VMnet
`192.168.146.1:11121` → Windows `127.0.0.1:11119`. After a host reboot the last
listener may be absent. Check the actual proxy CONNECT and CRI pull result,
not only socket readiness. Keep cluster and Service addresses in `NO_PROXY`.
Do not attach a host-loopback proxy to ordinary Pods or restart RKE2 to repair
an unrelated external proxy.

On containerd 2.x, `ctr images pull` defaults to the daemon transfer service;
clearing only the CLI's proxy environment does not clear the daemon's proxy.
For an explicitly verified direct route, an operator may pre-pull a locked
reference with `env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY
ctr --address /run/k3s/containerd/containerd.sock --namespace k8s.io images
pull --local --max-concurrent-downloads 1 --platform linux/amd64 IMAGE@sha256:DIGEST`.
Run this separately on each candidate node, preserve TLS verification and
inspect the exact CRI `repoDigests` before admitting a test. Existing images
and prior evidence must remain available for rollback. This is a lab egress
workaround; a fresh production cluster requires reliable registry access.

The 2026-10-08 startup incident also showed a present `11119` listener with
working HTTPS while `11121` timed out. Presence of all sockets is insufficient.
Direct GHCR metadata access succeeded but some CDN layer transfers stalled;
that route must not be declared usable from a token/manifest request alone.
The accepted test used a bounded, host-key-verified SSH loopback forward to
the existing working proxy, then pulled the seven digests on all three nodes.
The forward is temporary and removed after use. Never disable registry TLS,
pin a discovered CDN address globally or restart healthy storage to fix egress.

Use Linux amd64, Node 24, Helm 3.17.3 and kubectl matching the cluster. At least
three Ready nodes are required. `/dev/kvm` must work on each VM candidate; enable
nested virtualization on the hypervisor. Configure cert-manager, Multus,
Whereabouts, metrics-server and a working default storage class. This lab uses
RKE2, Cilium, local-path, cert-manager 1.21.2 and Kubernetes 1.36.4. Upstream
autoscaling's original Kubernetes target is 1.31; 1.36 is an explicit laboratory
exception, not a certified compatibility matrix.

Validate nonoverlapping host/Pod/Service and NeonVM network ranges. Defaults
reserve `10.100.1.0–10.100.127.255` for overlay Pods and VM allocation starts at
`10.100.128.0` within `10.100.0.0/16`. Both chart and control product currently
use the fixed `neon` namespace and service identities. Changing these requires
reviewing the API image's own namespace/config contract.

On RKE2:

```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
export KUBECTL_BIN=/var/lib/rancher/rke2/bin/kubectl
export KUBE_API_SERVER=https://192.168.146.101:6443
export HELM_BIN="$PWD/.local/bin/helm"
"$KUBECTL_BIN" get nodes
"$KUBECTL_BIN" get storageclass
"$KUBECTL_BIN" get crd certificates.cert-manager.io network-attachment-definitions.k8s.cni.cncf.io ippools.whereabouts.cni.cncf.io
```

## 2. Secret management

Never enter credentials into Helm values, Git or command arguments. Prefer a
secret manager / External Secrets operator. Each Secret below is externally
owned, backed up and restored independently of release manifests.

| Secret (namespace neon) | Required keys |
|---|---|
| neon-object-store | accessKey, secretKey |
| neon-controller-db | password, url (controller PostgreSQL DSN) |
| neon-proxy-auth | proxyToken; legacy API additionally requires scramVerifier |
| neon-proxy-tls | tls.crt, tls.key |
| neon-control-hook-auth | token |
| neon-control-v2-db | password |
| neon-control-plane-credentials | database-url, admin-password, idempotency-key |
| neon-backend-credential-keys-v1 | keyring.json: active version and 32–64-byte base64 pepper keys |
| neon-control-routes | routes.json: initially `{}`, then mutated by Drivers |

`neon-control-notifications` is an externally mutable ConfigMap with
`receipts.json` initially `{}`. The bootstrap tool only creates absent objects.

For a **new isolated lab only**, generate strong credentials into an empty
protected directory. Existing clusters must follow UPGRADE.md instead.

```bash
umask 077
node tools/bootstrap-state.mjs
node tools/prepare-lab-secrets.mjs --output /secure/neon-bootstrap-001 --acknowledge-lab
for file in /secure/neon-bootstrap-001/*.private.json; do
  "$KUBECTL_BIN" -n neon create -f "$file"
done
```

Do not replace `create` with `apply` to reset an existing installation. The
generated Proxy certificate lasts 30 days, is self-signed and is only for lab
TLS transport; clients currently use the documented lab verification exception.
The initial Console password is in `/secure/neon-bootstrap-001/admin-password`.
Keep this material in encrypted operator storage. Rotate through a planned,
tested migration; do not regenerate the idempotency or pepper keys casually.

## 3. Configure site-specific nonsecret values

Create `/secure/neon-overlay` with files named `<chart>.json`. They deep-merge
over the locked public lab settings. Arrays replace completely. For example:

```json
{
  "api": {"publicProxyHost": "192.168.146.100", "publicProxyPort": 30432},
  "service": {"type": "NodePort", "nodePort": 30788}
}
```

Save that as `neon-control-plane.json`. Review all public profiles for storage
class, S3 endpoint, resource reservations and network CIDRs. Existing clusters
must use complete compatibility overlays based on their protected release
values. Do not replace existing tenant/node IDs with sample values.

## 4. Render, preflight and install

```bash
node tools/stack.mjs render --overlay-dir /secure/neon-overlay --output /secure/neon-render-001
node tools/stack.mjs preflight --overlay-dir /secure/neon-overlay --output /secure/neon-preflight-001
node tools/stack.mjs apply --maintenance-window --overlay-dir /secure/neon-overlay --output /secure/neon-install-001
node tools/stack.mjs verify --output /secure/neon-verify-001
```

Each attempt directory is immutable. `apply` waits for each release before the
next, uses image digests, preserves mutable state, and records previous release
values/manifests and metadata backups privately. A failure stops subsequent
stages. There is no automatic database rollback. Existing unowned resources
need the separately reviewed `--adopt-unowned` migration switch.

Node plugins must finish before VM use. The serving certificate must be Ready
before control-plane startup. Managed node-2 Pageserver creation is declarative;
Storage Controller attachment is validated by project creation. Node-1's
emergency-mode historical Pageserver is kept separate; moving its historical
tenants is a different migration.

## 5. Connect and verify the product

Open `http://192.168.146.100:30788/`; log in using the externally stored admin
password. Open `/api/docs` for the bundled OpenAPI contract. Create a project,
wait for Operation success, create a child branch and writer/read Endpoint,
execute SQL in the Console and test an external PostgreSQL client through
`192.168.146.100:30432`. Follow the connection string generated by the UI;
Endpoint selection is required without public DNS/SNI.

Use [TESTING.md](TESTING.md) for reproducible project creation, cold wake,
replicas, read-only rejection, branch Data API/RLS, credential isolation and
Worker restart. A successful Helm install alone is not product acceptance.

## 6. Resource policy

Reserve host/etcd resources before tests; this lab reserves 1 CPU/2 GiB per node.
Keep foundation requests/limits and platform priority enabled. Three controller
replicas spread across nodes; Safekeepers must be on separate nodes. Test one
managed Compute at a time, suspend owned Endpoints after testing, and preserve
project/test records. Never delete a PVC/WAL/S3 prefix to recover scheduling
capacity. Builds and UI tests run serially on the shared physical storage.

## Managed Auth SQL certificate identity

The public lab profile expects the fresh certificate generated by `tools/prepare-lab-secrets.mjs`: `proxy.neon.svc.cluster.local`. Auth projects only `tls.crt` from `neon-proxy-tls`, never the private key. Set `managedAuth.pgCASecret/pgCAKey/pgServerName` to the actual trusted CA and certificate DNS identity before enabling Auth. The existing 192.168.146.100 laboratory uses an older certificate naming `lab.neon.local`; retain that identity in its private overlay. Do not replace an existing certificate or guess a name during an upgrade. The browser origin must match `managedAuth.publicOrigin`. See the public control [Auth deployment contract](https://github.com/william-lbn/control-plane/blob/2dcd7d2dbac6edac9d7f2190ebf8c67db90ebb97/docs/MANAGED-AUTH.md). This explicit SQL trust does not certify browser, metadata, storage or management TLS.
