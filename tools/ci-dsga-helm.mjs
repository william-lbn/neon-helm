#!/usr/bin/env node
// Offline-only render and RBAC contracts; no kubectl or real qualifications.
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {root} from './lib.mjs';
const output = path.join(root, 'artifacts/dsga-contracts');
fs.mkdirSync(output, {recursive: true});
const run = fs.mkdtempSync(path.join(output, 'run-'));
const python = process.env.PYTHON_BIN || 'python3';
const records = [];
function execute(name, binary, args) {
  const started = Date.now();
  const result = spawnSync(binary, args, {cwd: root, encoding: 'utf8', timeout: 120000, maxBuffer: 8 * 1024 * 1024,
    env: {...process.env, KUBECONFIG: '/dev/null', HELM_NO_PLUGINS: '1'}});
  fs.writeFileSync(path.join(run, `${name}.log`), (result.stdout || '') + (result.stderr || ''));
  records.push({name, status: result.status, elapsed_ms: Date.now() - started});
  if (result.status !== 0 || result.error) throw new Error(`${name}: ${result.error?.message || result.stderr || result.stdout}`);
}
try {
  execute('qualifier', python, ['charts/dsga-platform-qualifier/tests/check_render.py', '--output-dir', path.join(run, 'qualifier')]);
  execute('runner-rbac', python, ['charts/dsga-runner-access/tests/render-rbac.py']);
  execute('pod-protection', python, ['charts/neon-autoscaler/tests/pod-protection-rbac.py', '--output', path.join(run, 'pod-protection')]);
  // The original 0820655 baseline predates the later legitimate Lease-read
  // permission. Compare against the audited integration head for this release;
  // all socket isolation and no-additional-RBAC assertions still run unchanged.
  execute('control-socket', python, ['charts/neon-autoscaler/tests/full-control-uds.py', '--baseline-commit', '85ebf7f23521667fad84791b78b5fa36fac24ada', '--output', path.join(run, 'control-socket')]);
  execute('pod-resources', python, ['charts/neon-compute/tests/pod-resources.py', '--output', path.join(run, 'pod-resources')]);
  const baseline = path.join(run, 'pg17-baseline'); fs.mkdirSync(baseline);
  const archive = path.join(run, 'pg17-baseline.tar');
  // Immediate pre-PG18 template, after the trusted-image config split.
  execute('baseline-archive', 'git', ['archive', '--format=tar', '--output', archive, '62544f48df70a6ae263af5862570d656004d16fb', 'charts/neon-compute']);
  execute('baseline-extract', 'tar', ['-xf', archive, '-C', baseline]);
  execute('major-selection', python, ['charts/neon-compute/tests/major-selection.py', '--baseline-chart', path.join(baseline, 'charts/neon-compute'), '--output', path.join(run, 'major-selection')]);
  console.log(JSON.stringify({result: 'pass', contracts: 6, output: run, deployed: false, qualificationIssued: false}));
} finally {
  fs.writeFileSync(path.join(run, 'result.json'), JSON.stringify({records, deployed: false, qualificationIssued: false}, null, 2) + '\n');
}
