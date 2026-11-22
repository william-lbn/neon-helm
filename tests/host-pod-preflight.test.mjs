import assert from 'node:assert/strict';
import {test} from 'node:test';
import {inspectHostPodLimits, positiveMemoryBytes, projectHostSnapshot} from '../tools/host-pod-preflight.mjs';

for (const [value, bytes] of [['128Mi', 134217728n], ['0.5Gi', 536870912n], ['1.5k', 1500n], ['1000m', 1n], ['1e3', 1000n], ['2E+3', 2000n], ['1Ei', 1152921504606846976n], ['9223372036854775807', 9223372036854775807n]]) test('exact positive memory bytes: ' + value, () => assert.equal(positiveMemoryBytes(value), bytes));
for (const value of [undefined, 1024, '0', '-1Gi', '1m', '1.1', '1e99', '1e-99', '8Ei', '9223372036854775808', 'NaN', '128MB', '1K', ' 1Gi']) test('rejects invalid memory bytes: ' + String(value), () => assert.equal(positiveMemoryBytes(value), null));
const pod = (name, node = 'host-a') => ({apiVersion: 'v1', kind: 'Pod', metadata: {name, namespace: 'system', uid: name + '-uid', resourceVersion: '5'}, spec: {nodeName: node, containers: [{name: 'app', resources: {limits: {memory: '256Mi'}}}], initContainers: [{name: 'init', resources: {limits: {memory: '64Mi'}}}]}, status: {phase: 'Running'}});
const list = items => ({apiVersion: 'v1', kind: 'PodList', metadata: {}, items});
test('ordinary and initialization containers are independently bounded', () => {
  const result = inspectHostPodLimits(list([pod('good')]), ['host-a']);
  assert.equal(result.ready, true);
  assert.equal(result.hosts[0].ordinaryPods, 1);
  assert.equal(result.budgetsVerified, false);
});
test('requests and a main container limit cannot hide an unbounded init container', () => {
  const item = pod('unbounded');
  item.spec.initContainers[0].resources = {requests: {memory: '64Mi'}};
  const result = inspectHostPodLimits(list([item]), ['host-a']);
  assert.equal(result.ready, false);
  assert.deepEqual(result.hosts[0].issues.map(issue => [issue.code, issue.containerType, issue.container, issue.reason]), [['container-memory-limit-invalid', 'initContainers', 'init', 'missing']]);
});
test('terminal and other-host Pods do not enter ordinary Host allocation', () => {
  const done = pod('done');
  done.status.phase = 'Succeeded';
  done.spec.containers[0].resources = {};
  const other = pod('other', 'unselected');
  other.spec.containers[0].resources = {};
  assert.equal(inspectHostPodLimits(list([done, other]), ['host-a']).hosts[0].ordinaryPods, 0);
});
test('ephemeral and terminating ordinary Pods remain explicit blockers', () => {
  const item = pod('unsupported');
  item.spec.ephemeralContainers = [{name: 'debug'}];
  item.metadata.deletionTimestamp = '2026-11-22T00:00:00Z';
  assert.deepEqual(inspectHostPodLimits(list([item]), ['host-a']).hosts[0].issues.map(issue => issue.code), ['pod-terminating', 'unsupported-ephemeral-containers']);
});
test('VMs are delegated to the original runtime protocol, never certified by this check', () => {
  const item = pod('runner');
  item.metadata.ownerReferences = [{apiVersion: 'vm.neon.tech/v1', kind: 'VirtualMachine', name: 'vm', uid: 'vm-uid', controller: true}];
  item.spec.containers[0].resources = {};
  const result = inspectHostPodLimits(list([item]), ['host-a']);
  assert.equal(result.hosts[0].delegatedVMPods, 1);
  assert.equal(result.runtimeVMChecksPerformed, false);
  assert.equal(result.budgetsVerified, false);
  item.metadata.ownerReferences.push({kind: 'Other'});
  assert.equal(inspectHostPodLimits(list([item]), ['host-a']).ready, false);
});
test('incomplete or duplicated snapshots fail before reporting coverage', () => {
  const incomplete = list([]);
  incomplete.metadata.continue = 'next';
  assert.throws(() => inspectHostPodLimits(incomplete, ['host-a']), /Complete unpaginated/);
  const item = pod('duplicate');
  assert.throws(() => inspectHostPodLimits(list([item, item]), ['host-a']), /duplicate Pod identity/);
});
test('operator snapshots preserve resource identity but never persist Pod credentials or arbitrary annotations', () => {
  const item = pod('private');
  item.spec.containers[0].env = [{name: 'PASSWORD', value: 'do-not-persist'}];
  item.metadata.annotations = {'kubectl.kubernetes.io/last-applied-configuration': 'do-not-persist'};
  const nodes = {kind: 'NodeList', items: [{kind: 'Node', metadata: {name: 'host-a', uid: 'node-uid', resourceVersion: '1', labels: {'node-role.kubernetes.io/worker': '', accidentalToken: 'do-not-persist'}, annotations: {'rke2.io/node-args': 'do-not-persist'}}, status: {capacity: {memory: '32Gi'}}}]};
  const leases = {kind: 'LeaseList', items: [{kind: 'Lease', metadata: {name: 'neon-dsga-host-host-a', namespace: 'system', uid: 'lease-uid', resourceVersion: '2', annotations: {'internal.autoscaling.neon.tech/dsga-host-lease-v1': 'original-marker', private: 'do-not-persist'}}, spec: {holderIdentity: 'do-not-persist'}}]};
  const output = projectHostSnapshot(nodes, list([item]), leases);
  assert(!JSON.stringify(output).includes('do-not-persist'));
  assert.equal(output.pods.items[0].metadata.uid, 'private-uid');
  assert.equal(output.leases.items[0].metadata.annotations['internal.autoscaling.neon.tech/dsga-host-lease-v1'], 'original-marker');
  output.pods.items[0].spec.containers[0].resources.limits.memory = '1Mi';
  assert.equal(item.spec.containers[0].resources.limits.memory, '256Mi');
});
test('operator snapshot projection rejects partial input instead of manufacturing completeness', () => {
  const nodes = {kind: 'NodeList', items: [], metadata: {continue: 'next'}};
  assert.throws(() => projectHostSnapshot(nodes, list([]), {kind: 'LeaseList', items: []}), /Complete unpaginated NodeList/);
});
