import assert from 'node:assert/strict';

const fields = (value, names) => Object.fromEntries(names.filter(name => Object.hasOwn(value || {}, name)).map(name => [name, structuredClone(value[name])]));

export function projectHostSnapshot(nodes, pods, leases) {
  for (const [list, kind, itemKind] of [[nodes, 'NodeList', 'Node'], [pods, 'PodList', 'Pod'], [leases, 'LeaseList', 'Lease']]) assert([kind, 'List'].includes(list?.kind) && Array.isArray(list.items) && !list.metadata?.continue && list.items.every(item => item.kind === itemKind), 'Complete unpaginated ' + kind + ' is required');
  const metadata = value => fields(value, ['name', 'namespace', 'uid', 'resourceVersion', 'ownerReferences', 'deletionTimestamp']);
  const projectedNodes = nodes.items.map(node => {
    const meta = metadata(node.metadata);
    meta.labels = fields(node.metadata?.labels, ['node-role.kubernetes.io/control-plane', 'node-role.kubernetes.io/master', 'node-role.kubernetes.io/worker', 'kubernetes.io/hostname', 'kubernetes.io/arch', 'kubernetes.io/os']);
    meta.annotations = fields(node.metadata?.annotations, ['internal.autoscaling.neon.tech/dsga-host-ledger-v1']);
    return {apiVersion: 'v1', kind: 'Node', metadata: meta, spec: fields(node.spec, ['taints', 'unschedulable']), status: fields(node.status, ['conditions', 'capacity', 'allocatable', 'nodeInfo'])};
  });
  const projectedPods = pods.items.map(pod => {
    const spec = fields(pod.spec, ['nodeName', 'schedulerName', 'overhead']);
    for (const name of ['containers', 'initContainers', 'ephemeralContainers']) spec[name] = (pod.spec?.[name] || []).map(container => ({...fields(container, ['name', 'restartPolicy']), resources: fields(container.resources, ['requests', 'limits'])}));
    return {apiVersion: 'v1', kind: 'Pod', metadata: metadata(pod.metadata), spec, status: fields(pod.status, ['phase'])};
  });
  const projectedLeases = leases.items.filter(lease => lease.metadata?.name?.startsWith('neon-dsga-host-')).map(lease => ({apiVersion: 'coordination.k8s.io/v1', kind: 'Lease', metadata: {...metadata(lease.metadata), annotations: fields(lease.metadata?.annotations, ['internal.autoscaling.neon.tech/dsga-host-lease-v1'])}}));
  return {nodes: {apiVersion: 'v1', kind: 'NodeList', metadata: fields(nodes.metadata, ['resourceVersion']), items: projectedNodes}, pods: {apiVersion: 'v1', kind: 'PodList', metadata: fields(pods.metadata, ['resourceVersion']), items: projectedPods}, leases: {apiVersion: 'coordination.k8s.io/v1', kind: 'LeaseList', metadata: fields(leases.metadata, ['resourceVersion']), items: projectedLeases}};
}

const maximumMemory = (1n << 63n) - 1n;
const decimalPowers = {n: -9, u: -6, m: -3, '': 0, k: 3, M: 6, G: 9, T: 12, P: 15, E: 18};
const binaryPowers = {Ki: 10n, Mi: 20n, Gi: 30n, Ti: 40n, Pi: 50n, Ei: 60n};

export function positiveMemoryBytes(value) {
  if (typeof value !== 'string' || value.length > 64) return null;
  const match = /^(\+?(?:\d+(?:\.\d*)?|\.\d+))([eE][+-]?\d+|[KMGTPE]i|[numkMGTPE])?$/.exec(value);
  if (!match) return null;
  const [whole, fraction = ''] = match[1].replace(/^\+/, '').split('.');
  let numerator = BigInt((whole || '0') + fraction);
  let denominator = 10n ** BigInt(fraction.length);
  const suffix = match[2] || '';
  if (Object.hasOwn(binaryPowers, suffix)) numerator *= 1n << binaryPowers[suffix];
  else {
    const exponent = Object.hasOwn(decimalPowers, suffix) ? decimalPowers[suffix] : Number(suffix.slice(1));
    if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 64) return null;
    if (exponent >= 0) numerator *= 10n ** BigInt(exponent);
    else denominator *= 10n ** BigInt(-exponent);
  }
  if (numerator % denominator !== 0n) return null;
  const bytes = numerator / denominator;
  return bytes > 0n && bytes <= maximumMemory ? bytes : null;
}

export function inspectHostPodLimits(pods, hostNames) {
  assert(['PodList', 'List'].includes(pods?.kind) && Array.isArray(pods.items) && !pods.metadata?.continue && pods.items.every(pod => pod.kind === 'Pod'), 'Complete unpaginated PodList is required');
  assert(Array.isArray(hostNames) && hostNames.length && new Set(hostNames).size === hostNames.length, 'Unique selected Host names are required');
  const hosts = new Map(hostNames.map(nodeName => [nodeName, {nodeName, ordinaryPods: 0, delegatedVMPods: 0, issues: []}]));
  const seen = new Set();
  for (const pod of pods.items) {
    const metadata = pod.metadata || {};
    const key = metadata.namespace + '/' + metadata.name;
    assert(metadata.namespace && metadata.name && metadata.uid && metadata.resourceVersion && !seen.has(key), 'Missing or duplicate Pod identity');
    seen.add(key);
    const host = hosts.get(pod.spec?.nodeName);
    if (!host || ['Succeeded', 'Failed'].includes(pod.status?.phase)) continue;
    const identity = {namespace: metadata.namespace, pod: metadata.name, uid: metadata.uid};
    const issue = (code, extra = {}) => host.issues.push({...identity, code, ...extra});
    if (metadata.deletionTimestamp) issue('pod-terminating');
    const vmOwners = (metadata.ownerReferences || []).filter(owner => owner.kind === 'VirtualMachine' && owner.apiVersion?.split('/')[0] === 'vm.neon.tech');
    if (vmOwners.length) {
      host.delegatedVMPods++;
      if (vmOwners.length !== 1 || metadata.ownerReferences.length !== 1 || vmOwners[0].controller !== true || !vmOwners[0].uid) issue('ambiguous-vm-owner');
      continue;
    }
    host.ordinaryPods++;
    if (!Array.isArray(pod.spec.containers) || !pod.spec.containers.length) issue('unsupported-container-set');
    if (pod.spec.ephemeralContainers?.length) issue('unsupported-ephemeral-containers');
    for (const field of ['containers', 'initContainers']) for (const container of pod.spec[field] || []) {
      if (positiveMemoryBytes(container.resources?.limits?.memory) === null) issue('container-memory-limit-invalid', {containerType: field, container: container.name, reason: container.resources?.limits?.memory === undefined ? 'missing' : 'not-positive-integral-int64'});
    }
  }
  const rows = [...hosts.values()].map(host => ({...host, ready: host.issues.length === 0}));
  return {scope: 'ordinary-pod-hard-limits', ready: rows.every(host => host.ready), hosts: rows, runtimeVMChecksPerformed: false, budgetsVerified: false};
}
