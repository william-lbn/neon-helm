import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {documents,readJSON} from '../tools/lib.mjs';

function render(chart, change) {
 const values=readJSON('profiles/lab/'+chart+'.json');change(values);
 const d=fs.mkdtempSync(path.join(os.tmpdir(),'neon-storage-auth-'));
 try {
  const f=path.join(d,'values.json');fs.writeFileSync(f,JSON.stringify(values));
  const r=spawnSync('helm',['template','test','charts/'+chart,'-n','neon','--kube-version','1.34.0','-f',f],{encoding:'utf8'});
  return {status:r.status,error:r.stderr,docs:r.status===0?documents(r.stdout):[]};
 } finally {fs.rmSync(d,{recursive:true,force:true});}
}
function native(v) {
 Object.assign(v.storageController,{managePageserver:true,devMode:false,management:{
  enabled:true,authenticationEnabled:true,serviceName:'storage-controller-management',port:1235,tlsSecret:'storage-tls',issuerName:'existing-ca',authSecret:'storage-server-auth',pageserverUpcallSecret:'storage-upcall'}});
}
test('native management wires TLS, scoped secret refs and generations upcall together',()=>{
 const r=render('neon-core',native);assert.equal(r.status,0,r.error);
 const get=(kind,name)=>r.docs.find(x=>x.kind===kind&&x.metadata.name===name);
 const sc=get('Deployment','storage-controller').spec.template.spec;
 const c=sc.containers[0];assert.ok(!c.args.includes('--dev'));
 for(const key of ['PUBLIC_KEY','PAGESERVER_JWT_TOKEN','SAFEKEEPER_JWT_TOKEN','PEER_JWT_TOKEN'])assert.equal(c.env.find(x=>x.name===key).valueFrom.secretKeyRef.name,'storage-server-auth');
 assert.equal(get('Service','storage-controller-management').spec.ports.length,1);
 assert.ok(get('Certificate','storage-tls').spec.dnsNames.includes('storage-controller-management.neon.svc'));
 const config=get('ConfigMap','pageserver-config').data['pageserver.toml'];
 assert.match(config,/https:\/\/storage-controller-management.neon.svc:1235\/upcall/);
 assert.ok(!config.includes('control_plane_api_token'));
 const ps=get('Deployment','pageserver').spec.template.spec;
 assert.ok(ps.initContainers[0].args[0].includes('control_plane_api_token'));
 assert.equal(ps.volumes.find(x=>x.name==='storage-upcall').secret.secretName,'storage-upcall');
});
test('partial native auth cannot render insecure final deployment',()=>{
 for(const change of [
 v=>v.storageController.devMode=true,
 v=>v.storageController.management.authSecret='',
 v=>v.storageController.management.pageserverUpcallSecret='',
 v=>v.storageController.management.port=1234,
 v=>v.storageController.management.authenticationEnabled=false
 ]) {
  const r=render('neon-core',v=>{native(v);change(v);});assert.notEqual(r.status,0);
 }
});
test('adapter native observer removes API proxy permission and binds only named read sources',()=>{
 const r=render('neon-adapter',v=>{v.storageManagement={enabled:true,profile:{protocol_version:1,service_name:'storage-controller-management',service_uid:'storage-service-uid',port:1235,credential_secret_name:'storage-observer',credential_secret_uid:'storage-secret-uid'}};});
 assert.equal(r.status,0,r.error);
 const role=r.docs.find(x=>x.kind==='Role');
 assert.ok(!role.rules.some(x=>x.resources.includes('services/proxy')));
 const read=role.rules.find(x=>x.resources.includes('secrets')&&x.resourceNames.includes('storage-observer'));
 assert.deepEqual(read.verbs,['get']);
 const c=r.docs.find(x=>x.kind==='Deployment').spec.template.spec.containers[0];
 assert.ok(c.env.some(x=>x.name==='NEON_ADAPTER_STORAGE_PROFILE'));
});
