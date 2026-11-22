import test from 'node:test';
import assert from 'node:assert/strict';
import {validateResourceOwnership} from '../tools/resource-ownership.mjs';

const object = (kind = 'ConfigMap', name = 'shared', apiVersion = 'v1') => ({apiVersion, kind, metadata: {name}});
const release = (name, objects, namespace = 'neon') => ({release: name, namespace, objects});
test('independent namespaces preserve resource identity', () => {
  assert.deepEqual(validateResourceOwnership([release('one', [object()]), release('two', [object()], 'other')]), {releases: 2, objects: 2, nodePorts: 0});
});
test('duplicate objects conflict across releases or within one release', () => {
  assert.throws(() => validateResourceOwnership([release('one', [object(), object()])]), /ownership conflict/);
  assert.throws(() => validateResourceOwnership([release('one', [object()]), release('two', [object()])]), /ownership conflict/);
});
test('API version changes cannot hide ownership conflicts', () => {
  assert.throws(() => validateResourceOwnership([release('one', [object('Deployment', 'app', 'apps/v1')]), release('two', [object('Deployment', 'app', 'apps/v1beta1')])]), /ownership conflict/);
});
for (const [kind, apiVersion] of [['Namespace', 'v1'], ['ClusterRole', 'rbac.authorization.k8s.io/v1']]) test('cluster-scoped ' + kind + ' cannot be shared between releases', () => {
  assert.throws(() => validateResourceOwnership([release('one', [object(kind, 'global', apiVersion)]), release('two', [object(kind, 'global', apiVersion)], 'other')]), /ownership conflict/);
});
test('cluster resources reject namespace fields', () => {
  const resource = object('Namespace');
  resource.metadata.namespace = 'neon';
  assert.throws(() => validateResourceOwnership([release('one', [resource])]), /cannot have a namespace/);
});
test('CRD scope is consumed before custom resources', () => {
  const crd = {...object('CustomResourceDefinition', 'widgets.example.test', 'apiextensions.k8s.io/v1'), spec: {group: 'example.test', names: {kind: 'Widget'}, scope: 'Cluster'}};
  const widget = object('Widget', 'one', 'example.test/v1');
  assert.throws(() => validateResourceOwnership([release('one', [widget, crd]), release('two', [widget], 'other')]), /ownership conflict/);
});
test('unknown custom resources require discovery or a CRD scope', () => {
  const widget = object('Widget', 'one', 'example.test/v1');
  assert.throws(() => validateResourceOwnership([release('one', [widget])]), /Unknown resource scope/);
  assert.equal(validateResourceOwnership([release('one', [widget])], {scopes: {'example.test/Widget': 'Namespaced'}}).objects, 1);
});
test('Helm annotations must match release and release namespace', () => {
  for (const name of ['meta.helm.sh/release-name', 'meta.helm.sh/release-namespace']) {
    const resource = object();
    resource.metadata.annotations = {[name]: 'another-owner'};
    assert.throws(() => validateResourceOwnership([release('one', [resource])]), /annotation mismatch/);
  }
});
test('explicit NodePorts cannot be shared by different Services', () => {
  const service = name => ({...object('Service', name), spec: {ports: [{port: 80, nodePort: 31000}]}});
  assert.throws(() => validateResourceOwnership([release('one', [service('one')]), release('two', [service('two')])]), /NodePort conflict/);
  const dual = service('one');
  dual.spec.ports.push({port: 80, nodePort: 31000, protocol: 'UDP'});
  assert.equal(validateResourceOwnership([release('one', [dual])]).nodePorts, 1);
});
test('List objects are expanded and unstable names are rejected', () => {
  assert.equal(validateResourceOwnership([release('one', [{kind: 'List', items: [object()]}])]).objects, 1);
  assert.throws(() => validateResourceOwnership([release('one', [{apiVersion: 'v1', kind: 'Pod', metadata: {generateName: 'unbound-'}}])]), /stable/);
});
