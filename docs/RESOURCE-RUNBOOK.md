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

## 4. Final release gate

Run `audit-live --expect-zero --require-manifest-match` as documented in
TESTING.md. Require zero managed VM/runner Pods, all foundation nodes/workloads
healthy, unchanged PVC bindings and external credentials, and exact installed
manifests/hooks and image locks. Keep the audit and restore receipt; metadata
dump restore alone does not verify user database WAL/S3 recovery or RPO/RTO.
