#!/usr/bin/env node
// Run once for a new product store, outside the repository. Never overwrite a
// previous identity or print its value; rotation needs an explicit operator run.
import fs from 'node:fs';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import { parseArgs } from 'node:util';
// Keep secret bootstrap independent of YAML/npm dependencies. The binary uses
// only Node's standard library and can run before installing Helm tooling.
function privateDirectory(directory) { fs.mkdirSync(directory, { recursive: true, mode: 0o700 }); fs.chmodSync(directory, 0o700); }
function writePrivate(filename, content) { fs.writeFileSync(filename, content, { encoding: 'utf8', mode: 0o600, flag: 'wx' }); }
const { values } = parseArgs({ options: {
  output: { type: 'string' }, endpoint: { type: 'string' }, bucket: { type: 'string', default: 'neon-product-blobs' },
  region: { type: 'string', default: 'us-east-1' }, 'lab-http': { type: 'boolean', default: false },
} });
if (!values.output || !values.endpoint) throw new Error('--output and --endpoint required');
const u = new URL(values.endpoint);
if (u.username || u.password || u.pathname !== '/' || u.search || u.hash || !['https:', 'http:'].includes(u.protocol) || (u.protocol === 'http:' && !values['lab-http'])) throw new Error('Exact HTTPS endpoint required, or explicit --lab-http');
if (!/^neon-product-[a-z0-9-]{1,40}$/.test(values.bucket)) throw new Error('Dedicated neon-product-* bucket required');
const output = path.resolve(values.output);
if (fs.existsSync(output)) throw new Error('Never overwrite a product storage identity');
privateDirectory(output);
const accessKey = 'neon-product-' + randomBytes(12).toString('hex');
const secretKey = randomBytes(32).toString('base64url');
const config = { endpoint: u.origin, bucket: values.bucket, region: values.region, access_key: accessKey, secret_key: secretKey, lab_http: values['lab-http'] };
writePrivate(path.join(output, 'neon-product-blob-store.private.json'), JSON.stringify({
  apiVersion: 'v1', kind: 'Secret', type: 'Opaque', immutable: true,
  metadata: { name: 'neon-product-blob-store', namespace: 'neon' },
  stringData: { accessKey, secretKey, 'config.json': JSON.stringify(config) },
}, null, 2));
console.log('Prepared one immutable product credential Secret. Apply with kubectl create; keep its file protected. No credential was printed.');
