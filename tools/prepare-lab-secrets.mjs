#!/usr/bin/env node
// Offline CSPRNG bootstrap for a NEW isolated lab. No secret is written to stdout
// or to a Helm release. Existing installations must keep their original keys.
import fs from 'node:fs';
import path from 'node:path';
import {randomBytes} from 'node:crypto';
import {parseArgs} from 'node:util';
import {privateDirectory,writePrivate,run} from './lib.mjs';
const {values}=parseArgs({options:{output:{type:'string'},'acknowledge-lab':{type:'boolean'}}});
if(!values.output||!values['acknowledge-lab'])throw new Error('Require --output outside the source and --acknowledge-lab');
const output=path.resolve(values.output);
if(fs.existsSync(output))throw new Error('Never overwrite existing bootstrap keys');
privateDirectory(output);
const token=()=>randomBytes(32).toString('base64');
const password=()=>randomBytes(32).toString('hex');
const controlPassword=password(),controllerPassword=password(),admin=password();
const records={
  'neon-object-store':{accessKey:'minio',secretKey:password()},
  'neon-controller-db':{password:controllerPassword,url:`postgresql://neon_controller:${controllerPassword}@controller-db:5432/storage_controller`},
  'neon-proxy-auth':{proxyToken:token()},
  'neon-control-hook-auth':{token:token()},
  'neon-control-v2-db':{password:controlPassword},
  'neon-control-plane-credentials':{'database-url':`postgres://neon_control_v2:${controlPassword}@neon-control-v2-db:5432/neon_control_v2?sslmode=disable`,'admin-password':admin,'idempotency-key':token()},
  'neon-backend-credential-keys-v1':{'keyring.json':JSON.stringify({active:'v1',keys:{v1:token()}})},
};
run('openssl',['req','-x509','-newkey','rsa:3072','-nodes','-days','30',
  '-subj','/CN=proxy.neon.svc.cluster.local','-addext','subjectAltName=DNS:proxy,DNS:proxy.neon.svc.cluster.local',
  '-keyout',path.join(output,'proxy.key'),'-out',path.join(output,'proxy.crt')]);
fs.chmodSync(path.join(output,'proxy.key'),0o600);
records['neon-proxy-tls']={'tls.key':fs.readFileSync(path.join(output,'proxy.key'),'utf8'),'tls.crt':fs.readFileSync(path.join(output,'proxy.crt'),'utf8')};
for(const [name,stringData] of Object.entries(records))writePrivate(path.join(output,name+'.private.json'),JSON.stringify({apiVersion:'v1',kind:'Secret',metadata:{name,namespace:'neon'},type:name==='neon-proxy-tls'?'kubernetes.io/tls':'Opaque',stringData},null,2));
writePrivate(path.join(output,'admin-password'),admin);
console.log('Prepared 8 external Secrets. Apply with kubectl create; preserve the directory securely. Laboratory transport only.');
