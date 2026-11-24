import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';
import YAML from 'yaml';

const root = path.resolve(import.meta.dirname, '..');
const helm = process.env.HELM_BIN || 'helm';
const charts = ['neon-autoscaler', 'dsga-platform-qualifier', 'dsga-qualification-issuer', 'dsga-qualifier-access', 'dsga-runner-access', 'neon-control-runtime-access'];
const uid = i => `90000000-1111-4222-8333-${String(i).padStart(12, '0')}`;
const names = count => Array.from({length: count}, (_, i) => `edge-${i + 1}.site-new`);
const hostLease = node => `neon-dsga-host-${node}`;
const fixture = chart => JSON.parse(fs.readFileSync(path.join(root, 'tests/fixtures/helm', `${chart}.json`), 'utf8'));
const rules = docs => docs.filter(d => ['Role', 'ClusterRole'].includes(d.kind)).flatMap(d => d.rules);

test('native Agent can verify real Host nodes with GET only', () => {
  const docs = render('neon-autoscaler', valuesFor('neon-autoscaler'));
  const role = docs.find(d => d.kind === 'ClusterRole' && d.metadata.name === 'neon-dsga-agent-node-reader');
  assert.deepEqual(role.rules, [{apiGroups: [''], resources: ['nodes'], resourceNames: names(5), verbs: ['get']}]);
  const binding = docs.find(d => d.kind === 'ClusterRoleBinding' && d.metadata.name === role.metadata.name);
  assert.equal(binding.roleRef.name, role.metadata.name);
  assert.deepEqual(binding.subjects, [{kind: 'ServiceAccount', name: 'autoscaler-agent', namespace: 'kube-system'}]);
});

test('explicit pool constrains Agent Node reads without granting writes', () => {
  const values = valuesFor('neon-autoscaler');
  values.placement = {allowedNodeNames: names(5)};
  const role = render('neon-autoscaler', values).find(d => d.kind === 'ClusterRole' && d.metadata.name === 'neon-dsga-agent-node-reader');
  assert.deepEqual(role.rules, [{apiGroups: [''], resources: ['nodes'], resourceNames: names(5), verbs: ['get']}]);
});

test('runtime namespace ownership is explicit and observer permissions remain scoped', () => {
  const values = valuesFor('neon-autoscaler');
  values.dsga.agent.runtimeSelectionNamespace = 'neon-control-existing';
  values.dsga.agent.resourceReadSocket = {enabled: true, hostDirectory: '/run/neon-resource', mountDirectory: '/run/neon-resource', name: 'resource.sock'};
  const docs = render('neon-autoscaler', values);
  assert.equal(docs.some(d => d.kind === 'Namespace' && d.metadata.name === 'neon-control-existing'), false);
  const role = docs.find(d => d.kind === 'Role' && d.metadata.name === 'neon-dsga-runtime-selection-observer');
  assert.equal(role.metadata.namespace, 'neon-control-existing');
  assert.deepEqual(role.rules, [{apiGroups: [''], resources: ['configmaps'], verbs: ['get']}]);
  values.dsga.agent.runtimeSelectionCreateNamespace = true;
  assert.equal(render('neon-autoscaler', values).filter(d => d.kind === 'Namespace' && d.metadata.name === 'neon-control-existing').length, 1);
});

function valuesFor(chart, count = 5) {
  const nodes = names(count);
  const identities = Object.fromEntries(nodes.map((name, i) => [name, uid(i + 1)]));
  if (chart === 'neon-autoscaler') {
    const profile = {id: 'offline-new-site', scheduler_name: 'autoscale-scheduler', vm_overhead_bytes: '3221225472', pod_overhead_bytes: '16777216'};
    return {
      experimentalAcknowledged: true,
      images: {agent: 'render.invalid/agent@sha256:' + 'a'.repeat(64), scheduler: 'render.invalid/scheduler@sha256:' + 'b'.repeat(64)},
      dsga: {
        enabled: true, hostIdentities: identities,
        agent: {gatewayURL: 'https://render.invalid:8444', managementCASecret: 'offline-public-ca'},
        scheduler: {
          podProtectionNamespaces: ['kube-system', 'neon-cert-manager', 'neonvm-system'],
          nodes: nodes.map((name, i) => ({
            binding: {node_name: name, node_uid: identities[name], namespace: 'neon', lease_name: hostLease(name), lease_uid: uid(i + 101)},
            profile, system_bytes: '4294967296',
            kubernetes_budget: {protocol_version: 1, scope: 'kubernetes-node-memory-budget-v1', node_name: name, node_uid: identities[name], capacity_bytes: '25769803776', allocatable_bytes: '25769803776', system_reservation_bytes: '4294967296', profile_sha256: createHash('sha256').update(JSON.stringify(profile)).digest('hex')},
          })),
        },
      },
    };
  }
  if (chart === 'dsga-platform-qualifier') return {
    enabled: true, hostIdentities: identities,
    image: {repository: 'render.invalid/qualifier', digest: 'sha256:' + 'c'.repeat(64)},
    binding: {vmName: 'cp-0123456789abcdef', vmUID: uid(201), incarnation: 'a'.repeat(32), nodeName: nodes[0], nodeUID: identities[nodes[0]], runnerPodName: 'cp-0123456789abcdef-offline', runnerConfigMapNames: ['offline-birth', 'offline-state', 'offline-exit', 'offline-stopped']},
    hostLease: {namespace: 'neon', name: hostLease(nodes[0])},
    inputs: {hostDirectory: '/offline/input', mountDirectory: '/offline/input', configFileName: 'issuer.json', configSHA256: 'd'.repeat(64), reportSHA256: 'e'.repeat(64)},
    agentResourceReadSocket: {hostDirectory: '/offline/resource', mountDirectory: '/offline/resource', name: 'resource.sock', sourceManifestSHA256: 'f'.repeat(64)},
  };
  if (chart === 'neon-control-runtime-access') return {allowedNodes: nodes, hostLeaseNames: nodes.map(hostLease)};
  const values = fixture(chart);
  values.allowedNodeNames = nodes;
  if (chart === 'dsga-runner-access') {
    values.enabled = true;
    values.hostLeases = nodes.map(name => ({namespace: 'neon', name: hostLease(name)}));
  } else {
    values.nodeName = nodes[0];
    if (chart === 'dsga-qualification-issuer') values.hostLeaseName = hostLease(nodes[0]);
  }
  return values;
}

function render(chart, values, error, kubeVersion = '1.31.2') {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'dsga-site-identity-'));
  try {
    const file = path.join(directory, 'values.json');
    fs.writeFileSync(file, JSON.stringify(values));
    const namespace = chart === 'neon-control-runtime-access' ? 'neon-control-offline' : chart === 'neon-autoscaler' ? 'default' : 'neon';
    const release = chart === 'dsga-qualification-issuer' ? values.subject.name : 'site-identity';
    const result = spawnSync(helm, ['template', release, path.join(root, 'charts', chart), '--namespace', namespace, '--kube-version', kubeVersion, '--values', file], {cwd: root, encoding: 'utf8', timeout: 20000, maxBuffer: 8 * 1024 * 1024, env: {...process.env, HELM_NO_PLUGINS: '1'}});
    assert.ifError(result.error);
    if (error) {
      assert.notEqual(result.status, 0, `${chart}: unsafe values rendered`);
      assert.match(result.stderr, error, `${chart}: unrelated refusal`);
      return [];
    }
    assert.equal(result.status, 0, `${chart}: ${result.stderr}`);
    return YAML.parseAllDocuments(result.stdout).map(doc => doc.toJSON()).filter(Boolean);
  } finally {
    fs.rmSync(directory, {recursive: true, force: true});
  }
}

for (const namespace of ['neon-cert-manager', 'cert-manager', 'local-path-storage']) {
  test(`autoscaler protects the explicit ${namespace} namespace without extra scope`, () => {
    const values = valuesFor('neon-autoscaler');
    values.dsga.scheduler.podProtectionNamespaces = ['kube-system', namespace, 'neonvm-system'];
    const docs = render('neon-autoscaler', values);
    const protectedNamespaces = docs.filter(d => d.kind === 'Role' && d.metadata.name === 'neon-dsga-scheduler-pod-protection').map(d => d.metadata.namespace).sort();
    assert.deepEqual(protectedNamespaces, [...values.dsga.scheduler.podProtectionNamespaces].sort());
  });
}
test('autoscaler refuses wildcard namespace authority', () => {
  const values = valuesFor('neon-autoscaler');
  values.dsga.scheduler.podProtectionNamespaces.push('*');
  render('neon-autoscaler', values, /podProtectionNamespaces/);
});
test('namespace portability does not bypass Kubernetes qualification', () => {
  const values = valuesFor('neon-autoscaler');
  values.compatibility = {expectedKubernetesMinor: '36', allowUntestedKubernetes: true};
  render('neon-autoscaler', values, /forbids compatibility.allowUntestedKubernetes/, '1.36.6');
});

test('configured Kubernetes target is explicit; rendering grants no runtime qualification', () => {
  const values = valuesFor('neon-autoscaler');
  values.compatibility = {expectedKubernetesMinor: '36', allowUntestedKubernetes: false};
  const docs = render('neon-autoscaler', values, null, '1.36.6');
  assert.ok(docs.some(d => d.kind === 'Deployment'));
  values.compatibility.expectedKubernetesMinor = '31';
  render('neon-autoscaler', values, /configured target|configured actual target/, '1.36.6');
});

test('open node pool uses native selectors without hostname lists or derived labels', () => {
  const values = valuesFor('neon-autoscaler');
  values.placement = {allowedNodeNames: [], nodeSelector: {'capacity.example.com/class': 'compute'}, matchExpressions: [{key: 'node-role.kubernetes.io/control-plane', operator: 'DoesNotExist'}]};
  const docs = render('neon-autoscaler', values);
  for (const object of docs.filter(d => ['Deployment', 'DaemonSet'].includes(d.kind))) {
    const pod = object.spec.template.spec;
    assert.equal(pod.nodeSelector['capacity.example.com/class'], 'compute');
    assert.equal(pod.nodeSelector['kubernetes.io/os'], 'linux');
    assert.equal(pod.nodeSelector['neon.tech/pg17-memory-pool'], undefined);
    const terms = pod.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms;
    assert.equal(terms.length, 1);
    assert.deepEqual(terms[0].matchExpressions, values.placement.matchExpressions);
  }
});

test('first-install Agent warmup precedes Host CAS without changing final Host defaults', () => {
  const values = valuesFor('neon-autoscaler');
  values.dsga.scheduler.enabled = false;
  values.dsga.agent.resourceReadSocket = {enabled: true, hostDirectory: '/run/neon-test-resource', mountDirectory: '/run/neon-test-resource', name: 'resource.sock'};
  const warm = render('neon-autoscaler', values);
  const scheduler = docs => JSON.parse(docs.find(d => d.kind === 'ConfigMap' && d.metadata.name === 'scheduler-plugin-config').data['autoscale-enforcer-config.json']);
  const agent = JSON.parse(warm.find(d => d.kind === 'ConfigMap' && d.metadata.name === 'autoscaler-agent-config').data['config.json']);
  assert.equal(scheduler(warm).dsgaHost, undefined);
  assert.equal(agent.dsga.resourceReadSocketPath, '/run/neon-test-resource/resource.sock');
  values.dsga.scheduler.enabled = true;
  assert.equal(scheduler(render('neon-autoscaler', values)).dsgaHost.nodes.length, values.dsga.scheduler.nodes.length);
});

for (const chart of charts) {
  test(`${chart}: five entirely new site Nodes/UIDs render without broader Node/Lease authority`, () => {
    const values = valuesFor(chart);
    const docs = render(chart, values);
    assert.ok(docs.length);
    if (chart === 'neon-autoscaler') {
      const config = docs.find(d => d.kind === 'ConfigMap' && d.metadata.name === 'scheduler-plugin-config');
      assert.deepEqual(JSON.parse(config.data['autoscale-enforcer-config.json']).dsgaHost.nodes, values.dsga.scheduler.nodes);
    } else {
      const expected = ['dsga-qualification-issuer', 'dsga-qualifier-access', 'dsga-platform-qualifier'].includes(chart) ? [names(5)[0]] : names(5);
      const nodeRules = rules(docs).filter(rule => rule.resources.includes('nodes'));
      assert.equal(nodeRules.length, 1);
      assert.deepEqual(nodeRules[0], {apiGroups: [''], resources: ['nodes'], resourceNames: expected, verbs: ['get']});
      if (chart === 'dsga-runner-access' || chart === 'neon-control-runtime-access') {
        const leaseRules = rules(docs).filter(rule => rule.resources.includes('leases') && rule.resourceNames);
        assert.deepEqual(leaseRules.flatMap(rule => rule.resourceNames).sort(), names(5).map(hostLease).sort());
        for (const rule of leaseRules) assert.deepEqual(rule.verbs, ['get']);
      }
      for (const rule of rules(docs)) for (const key of ['verbs', 'resources', 'apiGroups']) assert.ok(!rule[key].includes('*'));
    }
  });
  for (const count of [1, 16]) test(`${chart}: ${count}-Node boundary is supported`, () => render(chart, valuesFor(chart, count)));
}

for (const chart of ['neon-autoscaler', 'dsga-platform-qualifier']) {
  const map = values => chart === 'neon-autoscaler' ? values.dsga : values;
  const binding = values => chart === 'neon-autoscaler' ? values.dsga.scheduler.nodes[0].binding : values.binding;
  const uidKey = chart === 'neon-autoscaler' ? 'node_uid' : 'nodeUID';
  const nameKey = chart === 'neon-autoscaler' ? 'node_name' : 'nodeName';
  for (const [name, mutate, error] of [
    ['missing explicit identity map', v => { delete map(v).hostIdentities; }, /hostIdentities/],
    ['empty identity map', v => { map(v).hostIdentities = {}; }, /hostIdentities/],
    ['missing observed UID', v => { delete map(v).hostIdentities[names(5)[0]]; }, /hostIdentities/],
    ['invalid observed UID', v => { map(v).hostIdentities[names(5)[0]] = 'not-a-uuid'; }, /pattern|UUID/],
    ['wrong observed UID', v => { map(v).hostIdentities[names(5)[0]] = uid(999); }, /hostIdentities/],
    ['missing binding UID', v => { delete binding(v)[uidKey]; }, /node_uid|nodeUID|hostIdentities/],
    ['wrong binding UID', v => { binding(v)[uidKey] = uid(999); }, /hostIdentities/],
    ['out-of-site binding', v => { binding(v)[nameKey] = 'outside.site-new'; }, /hostIdentities/],
    ['wildcard Node', v => { map(v).hostIdentities['*'] = uid(999); }, /pattern|hostIdentities/],
    ['invalid DNS label', v => { map(v).hostIdentities['a'.repeat(64)] = uid(999); }, /pattern|hostIdentities/],
    ['too many Nodes', v => { map(v).hostIdentities = Object.fromEntries(names(17).map((n, i) => [n, uid(i + 1)])); }, /at most 16|hostIdentities/],
  ]) test(`${chart}: rejects ${name}`, () => {
    const values = valuesFor(chart); mutate(values); render(chart, values, error);
  });
  test(`${chart}: disabled defaults remain safe`, () => {
    if (chart === 'dsga-platform-qualifier') assert.deepEqual(render(chart, {}), []);
    else {
      const values = valuesFor(chart); values.dsga = {enabled: false};
      const docs = render(chart, values);
      const config = docs.find(d => d.kind === 'ConfigMap' && d.metadata.name === 'scheduler-plugin-config');
      assert.equal(JSON.parse(config.data['autoscale-enforcer-config.json']).dsgaHost, undefined);
    }
  });
}

for (const [name, mutate, error] of [
  ['duplicate Node domains', v => { v.dsga.scheduler.nodes[1] = structuredClone(v.dsga.scheduler.nodes[0]); }, /hostIdentities/],
  ['incomplete Host domain set', v => { v.dsga.scheduler.nodes.pop(); }, /exactly cover hostIdentities/],
  ['extra Host domain', v => { v.dsga.scheduler.nodes.push(structuredClone(v.dsga.scheduler.nodes[0])); }, /exactly cover hostIdentities/],
  ['duplicate original Lease UID', v => { v.dsga.scheduler.nodes[1].binding.lease_uid = v.dsga.scheduler.nodes[0].binding.lease_uid; }, /Lease domains and original UIDs must be distinct/],
  ['wrong budget Node UID', v => { v.dsga.scheduler.nodes[0].kubernetes_budget.node_uid = uid(999); }, /budget must match/],
  ['wrong profile digest', v => { v.dsga.scheduler.nodes[0].kubernetes_budget.profile_sha256 = '0'.repeat(64); }, /profile SHA256/],
]) test(`neon-autoscaler: rejects ${name}`, () => {
  const values = valuesFor('neon-autoscaler'); mutate(values); render('neon-autoscaler', values, error);
});

for (const chart of charts.slice(2)) {
  const key = chart === 'neon-control-runtime-access' ? 'allowedNodes' : 'allowedNodeNames';
  for (const [name, list] of [
    ['empty allowlist', []], ['duplicate Nodes', [names(5)[0], names(5)[0]]],
    ['wildcard', ['*']], ['invalid DNS', ['Invalid_Node']], ['empty DNS label', ['edge..site']],
    ['overlong DNS label', ['a'.repeat(64)]], ['over 16 Nodes', names(17)],
  ]) test(`${chart}: rejects ${name}`, () => {
    const values = valuesFor(chart); values[key] = list;
    render(chart, values, /allowedNodeNames|allowedNodes/);
  });
  test(`${chart}: requires an explicit site allowlist`, () => {
    const values = valuesFor(chart); delete values[key]; render(chart, values, /allowedNodeNames|allowedNodes/);
  });
}

for (const chart of ['dsga-qualification-issuer', 'dsga-qualifier-access']) test(`${chart}: selected Node must be inside allowlist`, () => {
  const values = valuesFor(chart); values.nodeName = 'outside.site-new';
  if (chart === 'dsga-qualification-issuer') values.hostLeaseName = hostLease(values.nodeName);
  render(chart, values, /explicitly allowed Node|explicit allowedNodeNames/);
});
test('issuer: Host Lease must be derived from the selected Node, not another allowed Node', () => {
  const values = valuesFor('dsga-qualification-issuer'); values.hostLeaseName = hostLease(names(5)[1]);
  render('dsga-qualification-issuer', values, /HostLease must exactly match/);
});

for (const chart of ['dsga-runner-access', 'neon-control-runtime-access']) {
  const key = chart === 'dsga-runner-access' ? 'hostLeases' : 'hostLeaseNames';
  for (const [name, mutate] of [
    ['incomplete Lease set', list => list.slice(1)],
    ['same-length foreign Lease set', list => list.map((v, i) => i ? v : typeof v === 'string' ? hostLease('outside.site-new') : {...v, name: hostLease('outside.site-new')})],
    ['duplicate Lease', list => [list[0], ...list.slice(0, -1)]],
    ['extra Lease', list => [...list, typeof list[0] === 'string' ? hostLease('outside.site-new') : {namespace: 'neon', name: hostLease('outside.site-new')}]],
  ]) test(`${chart}: rejects ${name}`, () => {
    const values = valuesFor(chart); values[key] = mutate(values[key]);
    render(chart, values, /hostLeases|hostLeaseNames|derived Node Lease set/);
  });
  test(`${chart}: complete Lease set need not be in Node order`, () => {
    const values = valuesFor(chart); values[key].reverse(); render(chart, values);
  });
}

test('runner default remains disabled and unprivileged', () => assert.deepEqual(render('dsga-runner-access', {}), []));
test('control access still rejects workload namespace reuse', () => {
  const values = valuesFor('neon-control-runtime-access'); values.workloadNamespace = 'neon-control-offline'; values.hostLeaseNamespace = values.workloadNamespace;
  render('neon-control-runtime-access', values, /namespace must differ/);
});
test('control access still rejects a foreign Host Lease namespace', () => {
  const values = valuesFor('neon-control-runtime-access'); values.hostLeaseNamespace = 'foreign';
  render('neon-control-runtime-access', values, /Host leases must share/);
});

for (const count of [1, 5, 16]) test(`open placement keeps Node authority bound to ${count} trusted Host identities`, () => {
  const values = valuesFor('neon-autoscaler', count);
  values.placement = {allowedNodeNames: []};
  const docs = render('neon-autoscaler', values);
  const authority = Object.keys(values.dsga.hostIdentities).sort();
  for (const [name, verbs] of [['neon-dsga-agent-node-reader', ['get']], ['neon-dsga-scheduler-node-ledger', ['get', 'patch']]]) {
    const role = docs.find(d => d.kind === 'ClusterRole' && d.metadata.name === name);
    assert.deepEqual(role.rules, [{apiGroups: [''], resources: ['nodes'], resourceNames: authority, verbs}]);
    assert.ok(role.rules[0].resourceNames.length > 0);
  }
});
