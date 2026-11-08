import fs from 'node:fs';
import path from 'node:path';
import {root, readJSON} from './lib.mjs';

// These values only feed helm lint/template. They must never be installed or
// included in release overlays: several names are synthetic offline fixtures.
export function ciValues(chart) {
  for (const directory of ['profiles/lab', 'tests/fixtures/helm']) {
    const file = `${directory}/${chart}.json`;
    if (fs.existsSync(path.join(root, file))) return readJSON(file);
  }
  throw new Error(`No explicit offline Helm fixture for ${chart}`);
}

export function ciNamespace(chart) {
  if (chart === 'neon-control-runtime-access') return 'neon-control-offline';
  return ['neonvm', 'neon-autoscaler'].includes(chart) ? 'default' : 'neon';
}

export function ciKubeVersion(chart) {
  return chart === 'dsga-platform-qualifier' ? '1.31.2' : '1.36.4';
}
