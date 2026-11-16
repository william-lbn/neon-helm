import test from 'node:test';
import assert from 'node:assert/strict';
import {ciValues} from '../tools/ci-values.mjs';
import {documents, helm, merge, digest} from '../tools/lib.mjs';

const enabled = {
  realtime: {enabled: true, subscriptionLimit: 24, sourceLimit: 4},
  backendCredentials: {enabled: true, existingSecret: 'operator-backend-keys', labHTTP: false},
  api: {cookieSecure: true},
  worker: {enabled: true},
};
function render(overlay = {}, options = {}) {
  const values = merge(ciValues('neon-control-plane'), overlay);
  return helm(['template', 'entry-ci', 'charts/neon-control-plane', '-n', 'entry-ci',
    '--kube-version', '1.36.4', '-f', '-'], {input: JSON.stringify(values), ...options});
}
function config(docs) {
  return docs.find(o => o.kind === 'ConfigMap' && o.metadata.name === 'neon-control-web').data['nginx.conf'];
}

test('Realtime remains disabled without routes, credential namespace or runtime grants', () => {
  const docs = documents(render().stdout);
  assert(!config(docs).includes('location ^~ /realtime/v1/'));
  assert(!docs.some(o => o.kind === 'Namespace'));
  for (const o of docs.filter(o => o.kind === 'Deployment')) {
    for (const c of o.spec.template.spec.containers) {
      assert(!(c.env || []).some(e => e.name.startsWith('NEON_REALTIME_')));
    }
  }
});

test('enabled Realtime binds both processes to isolated least privilege credentials', () => {
  const docs = documents(render(enabled).stdout);
  const namespace = docs.find(o => o.kind === 'Namespace');
  assert.equal(namespace.metadata.name, 'neon-control-rtcred');
  for (const role of ['api', 'worker']) {
    const deployment = docs.find(o => o.kind === 'Deployment' && o.metadata.name === `neon-control-${role}`);
    const env = Object.fromEntries(deployment.spec.template.spec.containers[0].env.map(e => [e.name, e.value]));
    assert.equal(env.NEON_REALTIME_ENABLED, 'true');
    assert.equal(env.NEON_REALTIME_CREDENTIAL_NAMESPACE, namespace.metadata.name);
    assert.equal(env.NEON_REALTIME_SUBSCRIPTION_LIMIT, '24');
    assert.equal(env.NEON_REALTIME_SOURCE_LIMIT, '4');
    const permission = docs.find(o => o.kind === 'Role' && o.metadata.name === `realtime-${role}`);
    assert.equal(permission.metadata.namespace, namespace.metadata.name);
    assert.deepEqual(permission.rules, [{apiGroups: [''], resources: ['secrets'],
      verbs: role === 'api' ? ['get'] : ['get', 'create', 'delete']}]);
    const binding = docs.find(o => o.kind === 'RoleBinding' && o.metadata.name === `realtime-${role}`);
    assert.deepEqual(binding.subjects, [{kind: 'ServiceAccount', name: `neon-control-${role}`, namespace: 'entry-ci'}]);
  }
});

test('packaged NGINX routes SSE with isolated Console identity and rendered config rollout', () => {
  const docs = documents(render(enabled).stdout);
  const nginx = config(docs);
  const route = nginx.match(/location \^~ \/realtime\/v1\/ \{([\s\S]*?)\n    \}/)?.[1];
  assert(route, 'public Realtime must reach API rather than SPA fallback');
  for (const directive of ['proxy_pass http://neon-control-api:8788;', 'proxy_http_version 1.1;',
    'proxy_set_header Connection "";', 'proxy_set_header Cookie "";', 'proxy_set_header X-CSRF-Token "";',
    'proxy_set_header X-Neon-Console-Ticket "";', 'proxy_hide_header Set-Cookie;', 'proxy_buffering off;',
    'proxy_next_upstream off;', 'error_log /dev/null;']) assert(route.includes(directive), directive);
  assert(!route.includes('proxy_set_header Authorization'), 'application bearer identity must be forwarded');
  assert(!route.includes('proxy_set_header Last-Event-ID'), 'original reconnect cursor must be forwarded');
  const checksum = docs.find(o => o.kind === 'Deployment' && o.metadata.name === 'neon-control-web')
    .spec.template.metadata.annotations['checksum/config'];
  assert.equal(checksum, digest(nginx));
  const disabled = documents(render().stdout).find(o => o.kind === 'Deployment' && o.metadata.name === 'neon-control-web');
  assert.notEqual(checksum, disabled.spec.template.metadata.annotations['checksum/config']);
});

test('Ingress uses operator supplied class, hostname and external certificate reference', () => {
  const docs = documents(render(merge(enabled, {ingress: {enabled: true, className: 'operator-entry',
    host: 'console.example.invalid', tls: [{hosts: ['console.example.invalid'], secretName: 'operator-tls'}]}})).stdout);
  const ingress = docs.find(o => o.kind === 'Ingress');
  assert.equal(ingress.spec.ingressClassName, 'operator-entry');
  assert.equal(ingress.spec.rules[0].host, 'console.example.invalid');
  assert.deepEqual(ingress.spec.tls, [{hosts: ['console.example.invalid'], secretName: 'operator-tls'}]);
  assert.deepEqual(ingress.spec.rules[0].http.paths[0].backend.service, {name: 'neon-control-web', port: {name: 'http'}});
  assert(!docs.some(o => ['Secret', 'IngressClass', 'Gateway', 'GatewayClass', 'HTTPRoute'].includes(o.kind)));
});

for (const [name, overlay] of [
  ['missing Backend credentials', {backendCredentials: {enabled: false}}],
  ['missing separated Worker', {worker: {enabled: false}}],
  ['zero subscription limit', {realtime: {subscriptionLimit: 0}}],
  ['zero source limit', {realtime: {sourceLimit: 0}}],
]) test(`Realtime rejects ${name}`, () => {
  assert.notEqual(render(merge(enabled, overlay), {allowFailure: true}).status, 0);
});
