import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {parseAllDocuments} from 'yaml';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const pinned = /^[^\s]+@sha256:[a-f0-9]{64}$/;
export const readJSON = (name) => JSON.parse(fs.readFileSync(path.resolve(root, name), 'utf8'));
export const digest = (value) => crypto.createHash('sha256').update(value).digest('hex');
export function validateControlImagesLock(lock, references) {
  const expected=['adapter','api','auth','dataapi','gateway','postgrest','web'];
  if(!/^[a-f0-9]{40}$/.test(lock.source_commit)||lock.platform!=='linux/amd64'||
     lock.anonymous_registry_verified!==true||!Number.isSafeInteger(lock.github_ci_run_id)||
     JSON.stringify(Object.keys(lock.images||{}).sort())!==JSON.stringify(expected)||
     JSON.stringify(Object.keys(references).sort())!==JSON.stringify(expected))throw new Error('Invalid control image distribution');
  for(const component of expected) {
    const image=lock.images[component];
    if(image.source_commit!==lock.source_commit||image.anonymous_pull_verified!==true||
       !pinned.test(image.reference)||image.reference!==references[component])throw new Error('Control source/image drift: '+component);
  }
  return true;
}
export function fileDigest(file) {
  const hash=crypto.createHash('sha256');
  const fd=fs.openSync(file,'r');
  const buffer=Buffer.alloc(64*1024);
  try {
    for(let bytes;(bytes=fs.readSync(fd,buffer,0,buffer.length,null))>0;)hash.update(buffer.subarray(0,bytes));
  } finally {fs.closeSync(fd);}
  return hash.digest('hex');
}
export function documents(input) {
  return parseAllDocuments(input).map((doc) => {
    if (doc.errors.length) throw new Error('Invalid rendered YAML: ' + doc.errors[0].message);
    return doc.toJSON();
  }).filter(Boolean);
}
export function merge(base, overlay) {
  if (!overlay || typeof overlay !== 'object' || Array.isArray(overlay)) return overlay ?? base;
  const value = structuredClone(base ?? {});
  for (const [key, item] of Object.entries(overlay)) {
    value[key] = item && typeof item === 'object' && !Array.isArray(item)
      ? merge(value[key], item) : structuredClone(item);
  }
  return value;
}
export function validatePlan(plan) {
  if (plan.apiVersion !== 'neon-helm/v1' || plan.platform !== 'linux/amd64' || !Array.isArray(plan.steps)) throw new Error('Unsupported stack contract');
  const seen = new Set();
  for (const item of plan.steps) {
    if (!/^[a-z][a-z0-9-]*$/.test(item.release) || !/^[a-z][a-z0-9-]*$/.test(item.namespace) || seen.has(item.release)) throw new Error('Invalid/duplicate release identity');
    if (!/^[a-z][a-z0-9-]*$/.test(item.chart) || !item.values.startsWith('profiles/lab/')) throw new Error('Invalid chart/profile path');
    for (const dep of item.dependsOn) if (!seen.has(dep)) throw new Error('Dependency is not ready before ' + item.release + ': ' + dep);
    seen.add(item.release);
  }
  return plan;
}
export function run(binary, args, options = {}) {
  // Large pg_dump output must bypass Node's stdout maxBuffer. Open exclusively
  // and retain partial bytes on failure for diagnosis; never overwrite evidence.
  let fd;
  let result;
  try {
    if(options.stdoutFile)fd=fs.openSync(options.stdoutFile,'wx',0o600);
    result = spawnSync(binary, args, {cwd: root, encoding: 'utf8', timeout: options.timeout ?? 90000,
      maxBuffer: 32 * 1024 * 1024, input: options.input, env: process.env,
      ...(fd===undefined?{}:{stdio:['pipe',fd,'pipe']})});
    if(fd!==undefined)fs.fsyncSync(fd);
  } finally {if(fd!==undefined)fs.closeSync(fd);}
  if (result.error) throw new Error(binary + ' execution failed: ' + result.error.code);
  if (result.status !== 0 && !options.allowFailure) {
    // Child output can include metadata or accidental secrets. Keep errors
    // typed and terse; full private evidence is written only by operators.
    throw new Error(binary + ' failed with exit ' + result.status + ' for ' + args.slice(0, 2).join(' '));
  }
  return result;
}
export function kube(args, options) {
  const binary = process.env.KUBECTL_BIN || 'kubectl';
  const flags = ['--request-timeout=30s'];
  if (process.env.KUBE_API_SERVER) flags.push('--server=' + process.env.KUBE_API_SERVER);
  return run(binary, [...flags, ...args], options);
}
export function helm(args, options) {
  const flags = process.env.KUBE_API_SERVER ? ['--kube-apiserver=' + process.env.KUBE_API_SERVER] : [];
  return run(process.env.HELM_BIN || 'helm', [...flags, ...args], options);
}
export function get(kind, name, namespace) {
  kind = ({NetworkAttachmentDefinition:'network-attachment-definitions.k8s.cni.cncf.io',
    IPPool:'ippools.vm.neon.tech', Certificate:'certificates.cert-manager.io', Issuer:'issuers.cert-manager.io',
    VirtualMachine:'virtualmachines.vm.neon.tech', VirtualMachineMigration:'virtualmachinemigrations.vm.neon.tech'})[kind] || kind;
  const flags = namespace ? ['-n', namespace] : [];
  let result;
  try {result = kube([...flags, 'get', kind, ...(name ? [name] : []), '--ignore-not-found', '-o', 'json']);}
  catch {throw new Error('Kubernetes lookup failed for '+kind+'/'+(namespace||'cluster')+'/'+(name||'list'));}
  return resourceResult(result.stdout, name);
}
// kubectl --ignore-not-found can produce no JSON for an empty custom-resource
// collection. Preserve list semantics after the last test VM is retired;
// named lookup still returns null. Lookup/JSON errors continue to fail closed.
export function resourceResult(stdout, name) {
  return stdout.trim() ? JSON.parse(stdout) : name ? null : {apiVersion:'v1',kind:'List',items:[]};
}
export function privateDirectory(target) {
  // Secret-bearing evidence must not be accidentally placed in tracked source.
  const relative = path.relative(root, path.resolve(target));
  if (!relative.startsWith('..') && !relative.startsWith('artifacts' + path.sep) && !relative.startsWith('.local' + path.sep)) throw new Error('Evidence must be outside source or in ignored artifacts/.local');
  fs.mkdirSync(target, {recursive: true, mode: 0o700});
  fs.chmodSync(target, 0o700);
}
export function writePrivate(target, data) {
  fs.writeFileSync(target, data, {encoding: 'utf8', mode: 0o600, flag: 'wx'});
}
export function lockedValues(step, overlayDirectory) {
  const base = readJSON(step.values);
  const file = overlayDirectory && path.join(overlayDirectory, step.chart + '.json');
  return file && fs.existsSync(file) ? merge(base, JSON.parse(fs.readFileSync(file, 'utf8'))) : base;
}
export function rendered(step, valuesFile) {
  return helm(['template', step.release, 'charts/' + step.chart, '-n', step.namespace,
    '--kube-version', '1.36.4', '-f', valuesFile], {timeout: 60000}).stdout;
}
export function clusterScoped(kind) {
  return ['ClusterRole', 'ClusterRoleBinding', 'CustomResourceDefinition', 'Namespace', 'PriorityClass',
    'MutatingWebhookConfiguration', 'ValidatingWebhookConfiguration'].includes(kind);
}
export function compatibleAdoption(desired, current) {
  if (desired.kind === 'Secret' || desired.kind === 'Namespace' || desired.kind === 'CustomResourceDefinition') throw new Error('Never automatically adopt secret/namespace/CRD state');
  const owner = current.metadata.annotations?.['meta.helm.sh/release-name'];
  if (owner) throw new Error('Refusing to steal a resource already owned by ' + owner);
  const allowed = new Set(['neon-control-v2-db','neon-control-adapter','neon-control-adapter-code',
    'pageserver-managed-config','pageserver-managed-cache','neon-proxy-public']);
  if (!allowed.has(desired.metadata.name)) throw new Error('Resource is outside the documented adoption allowlist');
  const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key,canonical(value[key])])) : value;
  const compare = (left, right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
  if (desired.kind === 'Deployment' && !compare(desired.spec.selector, current.spec.selector)) throw new Error('Deployment selector differs');
  if (desired.kind === 'Service' && !compare(desired.spec.selector, current.spec.selector)) throw new Error('Service selector differs');
  if (desired.kind === 'PersistentVolumeClaim') {
    if (current.status.phase !== 'Bound' || !compare(desired.spec.accessModes, current.spec.accessModes)) throw new Error('PVC binding/access mode differs');
    if (desired.spec.storageClassName && desired.spec.storageClassName !== current.spec.storageClassName) throw new Error('PVC storage class differs');
    if (desired.spec.resources.requests.storage !== current.spec.resources.requests.storage) throw new Error('PVC size differs; expansion requires separate review');
  }
  if (desired.kind === 'ConfigMap') {
    const normalize = (value) => {
      try {return JSON.stringify(canonical(JSON.parse(value)));} catch {return String(value).trimEnd();}
    };
    const names = Object.keys(desired.data ?? {}).sort();
    if (!compare(names, Object.keys(current.data ?? {}).sort()) || names.some((name) => normalize(desired.data[name]) !== normalize(current.data[name]))) throw new Error('Unowned ConfigMap contents differ; do not overwrite runtime state');
  }
  return true;
}
