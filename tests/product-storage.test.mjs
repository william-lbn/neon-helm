import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const tool = fileURLToPath(new URL('../tools/prepare-product-storage.mjs', import.meta.url));
function invoke(args) { return spawnSync(process.execPath, [tool, ...args], { encoding: 'utf8' }); }
test('product bootstrap keeps credentials private and cannot replace an existing identity', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-product-bootstrap-'));
  try {
    const output = path.join(directory, 'protected');
    const args = ['--output', output, '--endpoint', 'http://minio.neon.svc.cluster.local:9000', '--lab-http'];
    const r = invoke(args); assert.equal(r.status, 0, r.stderr);
    const filename = path.join(output, 'neon-product-blob-store.private.json');
    const before = fs.readFileSync(filename, 'utf8'); const secret = JSON.parse(before);
    assert.equal(secret.immutable, true);
    assert.ok(!r.stdout.includes(secret.stringData.accessKey) && !r.stdout.includes(secret.stringData.secretKey));
    assert.equal(fs.statSync(filename).mode & 0o777, 0o600);
    assert.equal(fs.statSync(output).mode & 0o777, 0o700);
    assert.notEqual(invoke(args).status, 0); assert.equal(fs.readFileSync(filename, 'utf8'), before);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
test('unsafe endpoint or database bucket cannot generate product credentials', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-product-inputs-'));
  try {
    for (const [i, extra] of [
      ['--endpoint', 'http://minio:9000'],
      ['--endpoint', 'https://user:password@minio:9000'],
      ['--endpoint', 'https://minio:9000/other/path'],
      ['--endpoint', 'https://minio:9000', '--bucket', 'neon-pageserver'],
    ].entries()) {
      const output = path.join(directory, String(i));
      assert.notEqual(invoke(['--output', output, ...extra]).status, 0);
      assert.equal(fs.existsSync(output), false);
    }
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
