import test from 'node:test';
import assert from 'node:assert/strict';
import {readJSON} from '../tools/lib.mjs';
import {checkChartCatalog, validateChartCatalog} from '../tools/chart-catalog.mjs';

const original = readJSON('catalog/charts.json');
const options = {chartNames: original.charts.map(chart => chart.name), plan: readJSON('stack/stack.json')};
test('catalog matches source Charts, stack roles and platform ownership', () => {
  assert.deepEqual(checkChartCatalog(), {charts: 15, roles: {'stack-default': 8, optional: 2, qualification: 5}, platformOwnedByApplication: false});
});
for (const [name, change] of [
  ['duplicate Chart', catalog => catalog.charts.push(catalog.charts[0])],
  ['missing Chart', catalog => catalog.charts.pop()],
  ['unknown Chart', catalog => catalog.charts[0].name = 'unreviewed-chart'],
  ['unknown layer', catalog => catalog.charts[0].layer = 'L9'],
  ['default role drift', catalog => catalog.charts[0].role = 'optional'],
  ['optional role drift', catalog => catalog.charts.find(chart => chart.role === 'optional').role = 'qualification'],
  ['platform takeover', catalog => catalog.platformPrerequisites.applicationStackMayReplace = true],
  ['missing platform prerequisite', catalog => catalog.platformPrerequisites.components = ['kubernetes']],
  ['qualification escalation', catalog => catalog.qualification.productionReady = true],
  ['untyped PVC ownership', catalog => delete catalog.charts[0].managesPVC]
]) test('catalog rejects ' + name, () => {
  const catalog = structuredClone(original);
  change(catalog);
  assert.throws(() => validateChartCatalog(catalog, options));
});
test('stack cannot classify one Chart as both default and optional', () => {
  const plan = structuredClone(options.plan);
  plan.optionalCharts.push(plan.steps[0].chart);
  assert.throws(() => validateChartCatalog(original, {...options, plan}), /Conflicting/);
});
