import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {root, readJSON, documents} from './lib.mjs';

export function validateChartCatalog(catalog, {chartNames, plan}) {
  assert.equal(catalog.apiVersion, 'neon-chart-catalog/v1', 'Unsupported Chart catalog');
  const platform = catalog.platformPrerequisites;
  assert.equal(platform?.layer, 'L0', 'Platform prerequisites must be L0');
  assert.equal(platform.owner, 'platform-operator', 'Application Charts must not own the platform');
  assert.equal(platform.applicationStackMayReplace, false, 'Application stack cannot replace platform resources');
  assert(Array.isArray(platform.components) && new Set(platform.components).size === platform.components.length, 'Platform prerequisites must be unique');
  for (const component of ['kubernetes', 'cni', 'registry', ...plan.prerequisites]) assert(platform.components.includes(component), 'Missing platform prerequisite: ' + component);
  assert.deepEqual(Object.keys(catalog.layers).sort(), ['L1', 'L2', 'L3', 'L4'], 'Invalid catalog layers');
  assert.equal(catalog.qualification?.productionReady, false, 'Catalog cannot grant production qualification');
  assert.equal(catalog.qualification?.physicalMemoryReleaseQualified, false, 'Catalog cannot grant physical release qualification');
  const actual = new Set(chartNames);
  assert.equal(actual.size, chartNames.length, 'Duplicate source Chart names');
  const defaults = new Set(plan.steps.map(step => step.chart));
  const optional = new Set(plan.optionalCharts);
  for (const name of defaults) assert(!optional.has(name), 'Conflicting default and optional Chart roles');
  const seen = new Set();
  const roles = {'stack-default': 0, optional: 0, qualification: 0};
  for (const chart of catalog.charts) {
    assert(actual.has(chart.name), 'Unknown catalog Chart: ' + chart.name);
    assert(!seen.has(chart.name), 'Duplicate catalog Chart: ' + chart.name);
    seen.add(chart.name);
    assert(Object.hasOwn(catalog.layers, chart.layer), 'Unknown Chart layer: ' + chart.name);
    const expected = defaults.has(chart.name) ? 'stack-default' : optional.has(chart.name) ? 'optional' : 'qualification';
    assert.equal(chart.role, expected, 'Chart role disagrees with stack: ' + chart.name);
    assert.equal(typeof chart.managesPVC, 'boolean', 'Explicit PVC ownership required');
    assert.equal(typeof chart.managesCRDs, 'boolean', 'Explicit CRD ownership required');
    assert(typeof chart.responsibility === 'string' && chart.responsibility.trim(), 'Chart responsibility required');
    assert(Array.isArray(chart.externalInputs) && chart.externalInputs.every(input => typeof input === 'string' && input.trim()), 'External input list required');
    roles[chart.role]++;
  }
  assert.deepEqual([...seen].sort(), [...actual].sort(), 'Catalog must cover every source Chart exactly once');
  for (const name of [...defaults, ...optional]) assert(seen.has(name), 'Stack Chart missing from catalog: ' + name);
  return {charts: seen.size, roles, platformOwnedByApplication: false};
}

export function checkChartCatalog() {
  const chartNames = fs.readdirSync(path.join(root, 'charts'), {withFileTypes: true}).filter(entry => entry.isDirectory()).map(entry => entry.name);
  for (const name of chartNames) {
    const metadata = documents(fs.readFileSync(path.join(root, 'charts', name, 'Chart.yaml'), 'utf8'))[0];
    assert.equal(metadata.name, name, 'Chart directory/name mismatch');
  }
  return validateChartCatalog(readJSON('catalog/charts.json'), {chartNames, plan: readJSON('stack/stack.json')});
}
