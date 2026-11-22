#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {parseArgs} from 'node:util';
import {kube, privateDirectory, writePrivate, fileDigest} from './lib.mjs';
import {projectHostSnapshot} from './host-pod-preflight.mjs';

const {values: flags} = parseArgs({options: {output: {type: 'string'}, 'node-selector': {type: 'string'}}});
if (!flags.output) throw new Error('--output is required');
const output = path.resolve(flags.output);
if (fs.existsSync(output)) throw new Error('Snapshot output must be a new evidence directory');
const read = args => JSON.parse(kube(['get', ...args, '-o', 'json']).stdout);
const nodes = read(['nodes', ...(flags['node-selector'] ? ['-l', flags['node-selector']] : [])]);
if (!Array.isArray(nodes.items) || nodes.items.length < 1) throw new Error('Snapshot requires observed Nodes matching the selected scope');
const pods = read(['pods', '-A']);
const leases = read(['leases.coordination.k8s.io', '-A']);
const snapshots = projectHostSnapshot(nodes, pods, leases);
privateDirectory(output);
const inputs = {};
for (const [name, value] of Object.entries(snapshots)) {
  const file = path.join(output, name + '.json');
  writePrivate(file, JSON.stringify(value, null, 2) + '\n');
  inputs[name] = {path: file, sha256: fileDigest(file)};
}
const receipt = {apiVersion: 'neon-dsga-site-snapshot/v1', observedAt: new Date().toISOString(), nodeSelector: flags['node-selector'] || null, inputs, atomicCrossResourceSnapshot: false, podCredentialsIncluded: false, secretsRead: false, clusterMutated: false, hostBudgetsVerified: false, qualificationsIssued: false};
writePrivate(path.join(output, 'manifest.json'), JSON.stringify(receipt, null, 2) + '\n');
console.log(JSON.stringify({result: 'snapshot-created', output, nodes: snapshots.nodes.items.length, hostLeases: snapshots.leases.items.length, clusterMutated: false, hostBudgetsVerified: false}));
