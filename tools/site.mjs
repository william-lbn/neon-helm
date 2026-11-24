#!/usr/bin/env node
// Site composition only. Runtime identity, budgets and business lifecycle remain
// with their existing owners. No image/source audit or global maintenance here.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const name = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;
const keys = new Set(['apiVersion', 'name', 'kubeconfig', 'kubeContext', 'releases']);
const releaseKeys = new Set(['id', 'release', 'namespace', 'chart', 'valuesFiles', 'dependsOn', 'timeout']);
const hash = data => createHash('sha256').update(data).digest('hex');
export const quote = value => "'" + String(value).replaceAll("'", "'\"'\"'") + "'";
export function loadSite(file) {
  const base = path.dirname(path.resolve(file));
  const site = JSON.parse(fs.readFileSync(file, 'utf8'));
  for (const key of Object.keys(site)) if (!keys.has(key)) throw Error('Unknown site field: ' + key);
  if (site.apiVersion !== 'neon-site/v1' || !name.test(site.name) || !Array.isArray(site.releases) || !site.releases.length) throw Error('Expected named neon-site/v1 with releases');
  const ids = new Map(), identities = new Set();
  const releases = site.releases.map(raw => {
    for (const key of Object.keys(raw)) if (!releaseKeys.has(key)) throw Error('Unknown release field: ' + key);
    if (![raw.id, raw.release, raw.namespace].every(v => typeof v === 'string' && name.test(v)) || raw.release.length > 53 || raw.namespace.length > 63) throw Error('Invalid release identity');
    const identity = raw.namespace + '/' + raw.release;
    if (ids.has(raw.id) || identities.has(identity)) throw Error('Duplicate release: ' + identity);
    if (typeof raw.chart !== 'string' || !raw.chart || !Array.isArray(raw.valuesFiles) || !raw.valuesFiles.every(v => typeof v === 'string' && v)) throw Error('Explicit local Chart and valuesFiles required');
    if (raw.dependsOn !== undefined && (!Array.isArray(raw.dependsOn) || !raw.dependsOn.every(v => typeof v === 'string'))) throw Error('Invalid dependsOn');
    if (raw.timeout !== undefined && !/^[1-9][0-9]*(?:s|m|h)$/.test(raw.timeout)) throw Error('Invalid Helm timeout');
    const r = {...raw, chart: path.resolve(base, raw.chart), valuesFiles: raw.valuesFiles.map(v => path.resolve(base, v)), dependsOn: raw.dependsOn || [], timeout: raw.timeout || '5m'};
    if (!fs.existsSync(r.chart) || !r.valuesFiles.every(v => fs.statSync(v).isFile())) throw Error('Chart/values file missing: ' + raw.id);
    ids.set(r.id, r);identities.add(identity);return r;
  });
  const visiting = new Set(), done = new Set(), ordered = [];
  function visit(r) {
    if (done.has(r.id)) return;
    if (visiting.has(r.id)) throw Error('Dependency cycle: ' + r.id);
    visiting.add(r.id);
    for (const dep of r.dependsOn) {if (!ids.has(dep)) throw Error('Missing dependency: ' + dep);visit(ids.get(dep));}
    visiting.delete(r.id);done.add(r.id);ordered.push(r);
  }
  if (site.kubeconfig !== undefined && (typeof site.kubeconfig !== 'string' || !site.kubeconfig)) throw Error('Invalid kubeconfig reference');
  if (site.kubeContext !== undefined && (typeof site.kubeContext !== 'string' || !site.kubeContext)) throw Error('Invalid kubeContext');
  releases.forEach(visit);return {...site, kubeconfig: site.kubeconfig ? path.resolve(base, site.kubeconfig) : undefined, releases: ordered};
}
export function helmArgs(command, r, kubeVersion) {
  const values = r.valuesFiles.flatMap(f => ['-f', f]);
  if (command === 'render') return ['template', r.release, r.chart, '-n', r.namespace, '--include-crds', '--kube-version', kubeVersion, ...values];
  if (command === 'apply') return ['upgrade', '--install', r.release, r.chart, '-n', r.namespace, '--create-namespace', '--reset-values', ...values, '--wait', '--timeout', r.timeout];
  if (command === 'uninstall') return ['uninstall', r.release, '-n', r.namespace, '--wait', '--timeout', r.timeout];
  throw Error('Unsupported Helm operation');
}
function run(binary, args, out, timeout) {
  const result = spawnSync(binary, args, {encoding: 'utf8', timeout, maxBuffer: 64 * 1024 * 1024, env: process.env});
  fs.writeFileSync(out + '.stdout', result.stdout || '', {mode: 0o600, flag: 'wx'});
  fs.writeFileSync(out + '.stderr', result.stderr || '', {mode: 0o600, flag: 'wx'});
  return {exit: result.status, error: result.error?.code, stdout: out + '.stdout', stderr: out + '.stderr'};
}
export function main(argv = process.argv.slice(2)) {
  const {values: flags, positionals} = parseArgs({args: argv, allowPositionals: true, options: {site: {type: 'string'}, output: {type: 'string'}, resume: {type: 'string'}, 'kube-version': {type: 'string'}, 'confirm-site': {type: 'string'}}});
  const command = positionals[0];
  if (!['plan', 'render', 'apply', 'uninstall'].includes(command) || positionals.length !== 1 || !flags.site || !flags.output) throw Error('Usage: site.mjs plan|render|apply|uninstall --site SITE.json --output NEW_DIRECTORY [--kube-version VERSION]');
  if (command === 'render' && !/^v?1\.[0-9]+\.[0-9]+(?:[+-][0-9A-Za-z.-]+)?$/.test(flags['kube-version'] || '')) throw Error('Offline render requires explicit --kube-version; apply always uses actual API discovery');
  const site = loadSite(flags.site);
  if (command === 'uninstall' && flags['confirm-site'] !== site.name) throw Error('Uninstall requires --confirm-site matching site.name');
  const kubeconfig = site.kubeconfig || process.env.KUBECONFIG;
  if (['apply', 'uninstall'].includes(command) && (!kubeconfig || !path.isAbsolute(kubeconfig) || !fs.statSync(kubeconfig).isFile())) throw Error('Mutation requires an explicit absolute site.kubeconfig or KUBECONFIG file');
  const output = path.resolve(flags.output);
  const previous = flags.resume ? JSON.parse(fs.readFileSync(flags.resume, 'utf8')) : null;
  if (previous && (command !== 'apply' || previous.command !== 'apply' || previous.site !== site.name || previous.kubeconfig !== kubeconfig || previous.kubeContext !== (site.kubeContext || null))) throw Error('Resume requires the same apply site and explicit cluster target');
  if (previous?.steps.some(s => s.status === 'UNKNOWN' || s.status === 'submitted')) throw Error('Previous operation has an unknown outcome; reconcile its original Helm request before resuming');
  if (fs.existsSync(output)) throw Error('Use a new output directory; retain original receipts');
  fs.mkdirSync(output, {recursive: true, mode: 0o700});fs.chmodSync(output, 0o700);
  const binary = process.env.HELM_BIN || 'helm';
  const releases = command === 'uninstall' ? site.releases.toReversed() : site.releases;
  const receipt = {apiVersion: 'neon-site-receipt/v1', site: site.name, kubeconfig: kubeconfig || null, kubeContext: site.kubeContext || null, command, startedAt: new Date().toISOString(), status: 'running', businessE2E: 'NOT_RUN', cleanReset: false, steps: []};
  const save = () => {const pending = path.join(output, 'receipt.pending');fs.writeFileSync(pending, JSON.stringify(receipt, null, 2) + '\n', {mode: 0o600});fs.renameSync(pending, path.join(output, 'receipt.json'));};
  const lock = path.join(path.dirname(path.resolve(flags.site)), '.site-operation.lock');
  let locked = false;
  save();
  try {
    if (['apply', 'uninstall'].includes(command)) {fs.writeFileSync(lock, JSON.stringify({pid: process.pid, output, command, startedAt: receipt.startedAt}) + '\n', {mode: 0o600, flag: 'wx'});locked = true;}
    const lines = ['#!/usr/bin/env bash', 'set -euo pipefail'];
    for (const [index, r] of releases.entries()) {
      const args = helmArgs(command === 'plan' ? 'apply' : command, r, flags['kube-version']);
      if (kubeconfig) args.push('--kubeconfig', kubeconfig);
      if (site.kubeContext) args.push('--kube-context', site.kubeContext);
      lines.push([binary, ...args].map(quote).join(' '));
      const step = {id: r.id, release: r.release, namespace: r.namespace, chart: r.chart, values: r.valuesFiles.map(file => ({path: file, sha256: hash(fs.readFileSync(file))})), args, status: 'planned'};
      receipt.steps.push(step);save();
      const old = previous?.steps.find(s => s.id === r.id);
      if (old && ['completed', 'previously_completed'].includes(old.status)) {
        if (old.release !== step.release || old.namespace !== step.namespace || old.chart !== step.chart || JSON.stringify(old.values) !== JSON.stringify(step.values) || JSON.stringify(old.args) !== JSON.stringify(step.args)) throw Error('Completed step inputs changed; cannot skip ' + r.id);
        step.status = 'previously_completed';step.previousReceipt = path.resolve(flags.resume);save();continue;
      }
      if (command !== 'plan') {
        step.status = 'submitted';save();
        // The marker is persisted before invoking Helm. Unknown outcomes are
        // reconciled with helm status/history, never automatically rolled back.
        const timeout = Math.min(2147483647, Number.parseInt(r.timeout) * ({s: 1000, m: 60000, h: 3600000}[r.timeout.at(-1)]) + 90000);
        Object.assign(step, run(binary, args, path.join(output, String(index).padStart(2, '0') + '-' + r.id), timeout));
        step.status = step.error || step.exit === null ? 'UNKNOWN' : step.exit === 0 ? 'completed' : 'failed';save();
        if (step.status !== 'completed') throw Error('Helm ' + step.status + ' at ' + r.id + '; inspect receipt and original release before resuming');
      }
    }
    fs.writeFileSync(path.join(output, 'helm-commands.sh'), lines.join('\n') + '\n', {mode: 0o700, flag: 'wx'});
    receipt.status = command === 'plan' ? 'planned' : 'completed';
  } catch (error) {receipt.status = 'incomplete';receipt.error = error.message;throw error;}
  finally {receipt.finishedAt = new Date().toISOString();save();if (locked && !receipt.steps.some(step => step.status === 'UNKNOWN' || step.status === 'submitted')) fs.unlinkSync(lock);}
  console.log(JSON.stringify({site: site.name, command, status: receipt.status, releases: receipt.steps.length, receipt: path.join(output, 'receipt.json'), businessE2E: receipt.businessE2E}));
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {main();} catch (error) {console.error(error.message);process.exitCode = 1;}
}
