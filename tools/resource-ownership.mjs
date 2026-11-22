import assert from 'node:assert/strict';

const clusterKinds = new Set(['Namespace', 'Node', 'PersistentVolume', 'ClusterRole', 'ClusterRoleBinding', 'CustomResourceDefinition', 'StorageClass', 'CSIDriver', 'CSINode', 'VolumeAttachment', 'RuntimeClass', 'PriorityClass', 'IngressClass', 'APIService', 'MutatingWebhookConfiguration', 'ValidatingWebhookConfiguration', 'ValidatingAdmissionPolicy', 'ValidatingAdmissionPolicyBinding']);
const builtinGroups = {
  '': ['Namespace', 'Node', 'PersistentVolume', 'ConfigMap', 'Secret', 'Service', 'ServiceAccount', 'Pod', 'PersistentVolumeClaim', 'Endpoints', 'ResourceQuota', 'LimitRange', 'Event'],
  apps: ['Deployment', 'StatefulSet', 'DaemonSet', 'ReplicaSet'],
  batch: ['Job', 'CronJob'],
  'rbac.authorization.k8s.io': ['Role', 'RoleBinding', 'ClusterRole', 'ClusterRoleBinding'],
  'networking.k8s.io': ['NetworkPolicy', 'Ingress', 'IngressClass'],
  policy: ['PodDisruptionBudget'],
  autoscaling: ['HorizontalPodAutoscaler'],
  'coordination.k8s.io': ['Lease'],
  'discovery.k8s.io': ['EndpointSlice'],
  'storage.k8s.io': ['StorageClass', 'CSIDriver', 'CSINode', 'VolumeAttachment'],
  'node.k8s.io': ['RuntimeClass'],
  'scheduling.k8s.io': ['PriorityClass'],
  'apiextensions.k8s.io': ['CustomResourceDefinition'],
  'apiregistration.k8s.io': ['APIService'],
  'admissionregistration.k8s.io': ['MutatingWebhookConfiguration', 'ValidatingWebhookConfiguration', 'ValidatingAdmissionPolicy', 'ValidatingAdmissionPolicyBinding'],
  'events.k8s.io': ['Event']
};
const group = object => object.apiVersion.includes('/') ? object.apiVersion.split('/')[0] : '';
const flatten = objects => objects.flatMap(object => object?.kind === 'List' ? flatten(object.items || []) : [object]);

export function validateResourceOwnership(releases, {scopes = {}} = {}) {
  const custom = new Map(Object.entries(scopes));
  const batches = releases.map(release => ({...release, objects: flatten(release.objects)}));
  for (const release of batches) for (const object of release.objects) {
    if (object?.kind !== 'CustomResourceDefinition') continue;
    const key = object.spec.group + '/' + object.spec.names.kind;
    const scope = object.spec.scope;
    assert(['Namespaced', 'Cluster'].includes(scope), 'Invalid custom resource scope: ' + key);
    assert(!custom.has(key) || custom.get(key) === scope, 'Conflicting custom resource scope: ' + key);
    custom.set(key, scope);
  }
  const resources = new Map();
  const ports = new Map();
  const identities = new Set();
  let count = 0;
  for (const release of batches) {
    assert(release.release && release.namespace, 'Release name and namespace are required');
    const owner = release.namespace + '/' + release.release;
    assert(!identities.has(owner), 'Duplicate release identity: ' + owner);
    identities.add(owner);
    for (const object of release.objects) {
      assert(object && typeof object.apiVersion === 'string' && object.kind && object.metadata?.name, 'Rendered resources require stable API identity and name');
      const apiGroup = group(object);
      const type = apiGroup + '/' + object.kind;
      let scope = custom.get(type);
      if (!scope && Object.hasOwn(builtinGroups, apiGroup) && builtinGroups[apiGroup].includes(object.kind)) scope = clusterKinds.has(object.kind) ? 'Cluster' : 'Namespaced';
      assert(['Cluster', 'Namespaced'].includes(scope), 'Unknown resource scope: ' + type);
      assert(scope !== 'Cluster' || !object.metadata.namespace, 'Cluster resource cannot have a namespace: ' + type);
      const namespace = scope === 'Cluster' ? '' : object.metadata.namespace || release.namespace;
      const key = [apiGroup, object.kind, namespace, object.metadata.name].join('/');
      assert(!resources.has(key), 'Resource ownership conflict: ' + key);
      resources.set(key, owner);
      const annotations = object.metadata.annotations || {};
      for (const [name, expected] of [['meta.helm.sh/release-name', release.release], ['meta.helm.sh/release-namespace', release.namespace]]) {
        assert(!Object.hasOwn(annotations, name) || annotations[name] === expected, 'Helm ownership annotation mismatch: ' + key);
      }
      if (apiGroup === '' && object.kind === 'Service') for (const port of object.spec?.ports || []) {
        if (port.nodePort === undefined || port.nodePort === 0) continue;
        assert(Number.isInteger(port.nodePort) && port.nodePort > 0 && port.nodePort <= 65535, 'Invalid explicit NodePort: ' + key);
        assert(!ports.has(port.nodePort) || ports.get(port.nodePort) === key, 'NodePort conflict: ' + port.nodePort);
        ports.set(port.nodePort, key);
      }
      count++;
    }
  }
  return {releases: batches.length, objects: count, nodePorts: ports.size};
}
