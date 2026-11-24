import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {test} from 'node:test';
import {loadSite, helmArgs, quote, main} from '../tools/site.mjs';

function fixture(t, releases) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-site-'));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  fs.mkdirSync(path.join(root, 'chart'));
  fs.writeFileSync(path.join(root, 'values.json'), '{}');
  const file = path.join(root, 'site.json');
  fs.writeFileSync(file, JSON.stringify({apiVersion: 'neon-site/v1', name: 'test-site', releases: releases.map(r => ({chart: 'chart', valuesFiles: ['values.json'], ...r}))}));
  return {root, file};
}
test('two namespaces may share a release name; dependencies use explicit site IDs', t => {
  const f = fixture(t, [{id: 'product', release: 'neon', namespace: 'product', dependsOn: ['runtime']}, {id: 'runtime', release: 'neon', namespace: 'runtime'}]);
  const site = loadSite(f.file);
  assert.deepEqual(site.releases.map(r => r.id), ['runtime', 'product']);
  const apply = helmArgs('apply', site.releases[1]);
  assert.equal(apply[apply.indexOf('-n') + 1], 'product');
  assert.ok(!apply.some(arg => /insecure|force|take-ownership/.test(arg)));
});
test('cycles and duplicate physical release ownership fail before any Helm invocation', t => {
  const f = fixture(t, [{id: 'a', release: 'one', namespace: 'product', dependsOn: ['b']}, {id: 'b', release: 'two', namespace: 'product', dependsOn: ['a']}]);
  assert.throws(() => loadSite(f.file), /cycle/);
  const site = JSON.parse(fs.readFileSync(f.file));site.releases[1].release = 'one';
  fs.writeFileSync(f.file, JSON.stringify(site));assert.throws(() => loadSite(f.file), /Duplicate release/);
});
test('plan works without Kubernetes or Helm and does not claim E2E or clean reset', t => {
  const f = fixture(t, [{id: 'product', release: 'custom-name', namespace: 'custom-namespace'}]);
  const output = path.join(f.root, 'output');
  main(['plan', '--site', f.file, '--output', output]);
  const receipt = JSON.parse(fs.readFileSync(path.join(output, 'receipt.json')));
  assert.equal(receipt.status, 'planned');assert.equal(receipt.businessE2E, 'NOT_RUN');assert.equal(receipt.cleanReset, false);
  assert.match(fs.readFileSync(path.join(output, 'helm-commands.sh'), 'utf8'), /'custom-name'/);
  assert.throws(() => main(['uninstall', '--site', f.file, '--output', path.join(f.root, 'danger')]), /confirm-site/);
  assert.equal(fs.existsSync(path.join(f.root, 'danger')), false);
});
test('bash export quotes paths without expanding shell substitutions', () => {
  assert.equal(quote("/path with ' quote/$(id)`x`"), "'/path with '\"'\"' quote/$(id)`x`'");
});
