# Linux capacity, test retirement and incident evidence

## 1. Reserve the foundation

The current three-node lab reserves 1 CPU/2 GiB per node for the host and
Kubernetes. Keep etcd/API, controller DB, metadata DB, storage broker,
Pageservers, Safekeeper quorum, Proxy, VM controllers, autoscaler agents and
control API/Worker available. Pod requests, host reservations and priority
are distinct controls; an idle CPU chart does not establish disk capacity.

Before accepting a suite, save a read-only snapshot privately:

```bash
umask 077
task_out=/secure/neon-capacity-001
test ! -e "$task_out"
install -d -m 0700 "$task_out"
kubectl get nodes -o json > "$task_out/nodes.private.json"
kubectl top nodes > "$task_out/node-usage.txt"
kubectl get pods -A -o json > "$task_out/pods.private.json"
kubectl -n neon get pvc -o json > "$task_out/pvc.private.json"
kubectl -n neon get virtualmachines.vm.neon.tech -o json > "$task_out/vms.private.json"
kubectl get events -A --sort-by=.lastTimestamp > "$task_out/events.private.txt"
```

Review allocatable capacity and **requests**, pending Pods and node pressure,
not only `top`. Run one Compute UI suite at a time with 1 CPU/1 GiB bounds.
Use data-only branches when an Endpoint is unnecessary; suspend the writer
before activating a child or reader. Do not start a build, image import,
backup stress test or disk benchmark concurrently with live UI/SQL acceptance.
Limiting a pull client does not necessarily limit the containerd daemon's I/O.

## 2. Stop completed test runtime and retain reproducibility

| Resource | Retirement | Preserve |
|---|---|---|
| Managed `cp-*` Compute | UI/API suspend, then wait for VM and Pod removal | project/branch/Endpoint/Operation IDs, password fixture, timeline and SQL rows |
| Owned branch Data API | UI/API disable, then observe its Operation | application tables, service configuration, JWT fixture and evidence |
| Owned branch Managed Auth | disable dependent Data API first, then UI/API disable Auth | branch users/accounts, SQL schema, immutable Secrets and private app credentials |
| Optional imported static VM | graceful PostgreSQL shutdown and `compute.enabled=false`; see UPGRADE.md | complete values, config/SSH Secrets, Service UID and tenant/timeline |
| Finished test Job | archive Job/Pod JSON and every container's logs, then delete the reviewed terminal Job UID | all attempt folders, success/failure receipts and screenshots |
| Active or unknown workload | inspect owner and current work first | do not infer permission to retire it from a name alone |

Completed Jobs generally do not consume running CPU/RAM; their objects and
retained logs still need housekeeping. Never clear PVCs, WAL, Pageserver cache,
object prefixes, metadata, credentials or test files to regain compute capacity.
Do not prune image/build caches without preserving the rollback set and reviewing
all references. Kubernetes deletion is asynchronous; an absent VM can leave a
terminating runner. Bound observation (for example 120 seconds), then retain and
investigate a timeout. Avoid force deletion/finalizer removal.

For a reviewed terminal Job, ordinary `kubectl delete` does not protect against
concurrent resource replacement. Save its UID/resourceVersion, confirm no active
Pods, and use API DeleteOptions preconditions when automating cleanup. The CLI
supports a raw DELETE body through the configured authenticated transport.
See [kubectl delete](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_delete/)
and its [versioned implementation](https://github.com/kubernetes/kubectl/blob/v0.36.4/pkg/cmd/delete/delete.go).
Never put a cluster token into a command argument or disable certificate verification.

### Endpoint availability versus a running Compute

An enabled route can retain `desired_state=active` while its observed Compute
is `observed_state=suspended`. This allows the next authorized request to wake
the same Endpoint; it does not mean the VM is still consuming resources. Confirm
zero using the observed runtime **and** absence of its VM and runner Pod. Do not
rewrite endpoint metadata or disable a valid route to make those fields equal.
The final test gate checks all managed VMs and running runners, not just a button
label or the desired state returned by the Endpoint list.

The 2026-10-09 MinIO bootstrap failure was a container OOM at its 128 MiB limit
while the nodes had approximately 9–10 GiB available. The hook now requests
128 MiB, limits 512 MiB and sets the Go soft heap target to 128 MiB. A container
limit failure, physical RAM exhaustion, project quota exhaustion and a shared
disk fsync stall require different evidence and different remedies.

### Logical quota is separate from host resource pressure

An idle retained project still consumes organization project/Endpoint quota.
The default metadata limits are 50 live projects and 200 live Endpoints.
On 2026-10-08, `local` reached 50/50 with only 102/200 Endpoints; a new
project returned `429 organization_quota_exceeded` before any Operation was
accepted. CPU/memory availability and suspended VMs do not release that quota.

Keep an explicit reviewed allowlist of completed test projects and original
passing receipts. Prefer already unprotected managed projects; do not guess
ownership from a `ci-*` name or unset protection on unknown resources. Use
the product lifecycle API, exact name confirmation, `If-Match` and one
`Idempotency-Key`; observe the original Operation to success. Record the
tombstone, `recover_until` and `physical_gc_state=held`. This closes public
access and releases logical quota while retaining timeline, SQL, roles,
Secrets and evidence. Product recovery is currently limited to seven days;
data retention alone does not promise unlimited UI recovery. Protect any
fixture that must stay directly accessible instead of silently retiring it.

Four proven historical lifecycle fixtures were retired this way. The failed
native attempt and the successful follow-up both remain in evidence. Never
raise quotas, delete metadata rows or clear databases just to pass a test.

## 3. Diagnose stalls without masking them

On each Linux node, preserve a bounded time window around the failing request:

```bash
journalctl -u rke2-server --since '10 minutes ago' --no-pager
journalctl -k --since '10 minutes ago' --no-pager
cat /proc/pressure/{cpu,memory,io}
free -h
df -h /var/lib/rancher/rke2
iostat -xz 1 10 # if sysstat is already installed
```

Save detailed output privately, since logs can contain sensitive metadata.
Correlate request/Operation timestamps with etcd slow requests, lease loss,
RKE2 restart, disk latency/queue, OOM, node pressure and VM host evidence.
Three virtual machines on one physical NVMe still share I/O and a failure
domain. Memory availability does not rule out storage/host stalls, and an I/O
wait sample does not identify the initiating cause by itself.

On 2026-10-07 two RKE2 instances lost leadership leases. The sampled hosts
showed available memory and no observed OOM; temporary I/O wait was recorded.
The initiating stall remains unattributed. The accepted project Operation
eventually succeeded, exposing a Console observation gap now covered by
bounded read recovery. Keep the original failure. A successful retry is not
HA, etcd latency, durability or cross-instance fencing qualification.

On 2026-10-08, native cold SELECT encountered another SQL 503 during
simultaneous I/O waits. The three guests' 14:03–14:17 UTC etcd logs recorded
slow fdatasync maxima 21.875/30.589/26.358 seconds; all RKE2 processes
automatically restarted once. Guest and Windows host available memory was
ample; small sampled write volumes do not exclude severe flush latency.
Pause admission, preserve the original fixture and recover its runtime
normally when pressure returns below the gate. The fresh full native suite
passed afterwards, but **the host storage cause remains unresolved**. Do not
disable fsync, increase SQL timeouts or claim requests/priority fix a common
physical failure domain. Host ETW/driver/virtual-disk evidence and independent
storage remain needed for permanent qualification.

## 4. Final release gate

### Read-only Linux pressure admission

Run `bash tools/check-node-pressure.sh` on **every** candidate Linux node before
the next build, image pull or Compute suite. The default requires I/O PSI some
avg10 at most 5%, memory PSI some avg10 at most 0.10%, and at least 4096 MiB
available memory. Save each JSON result privately. This leaves room for one
bounded browser/Compute suite; it is not a storage throughput guarantee or a
replacement for requests/reservations. Explicit operator threshold changes
must be recorded, rather than silently accepting a failed check.

Stop admission on failure, preserve the current operation and sample `iostat`,
etcd/API readiness and host resources. Wait for a stable recovery; do not run
fio/compilation or restart the quorum during the stall. Run suites serially and
observe both VM and runner removal before admitting another. On 2026-10-07 the
restore follow-up sampled guest write waits of 0.2–2.5 seconds while all guests
had over 9 GiB available and the builder was inactive. The accepted Endpoint
eventually reconciled with its original identity. The initiating shared storage
stall is still unattributed; tests do not certify that it is permanently fixed.

Run `audit-live --expect-zero --require-manifest-match` as documented in
TESTING.md. Require zero managed VM/runner Pods, all foundation nodes/workloads
healthy, unchanged PVC bindings and external credentials, and exact installed
manifests/hooks and image locks. Keep the audit and restore receipt; metadata
dump restore alone does not verify user database WAL/S3 recovery or RPO/RTO.
