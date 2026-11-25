import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import test from 'node:test';
import YAML from 'yaml';

test('长命名空间生成不同的集群角色名，并保留精确节点权限',()=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'portable-access-'));
 try {
  const names=[];
  for(const tail of ['a','b']){
   const ns='neon-control-'+'x'.repeat(42)+tail,release='neon-runtime-access';
   const raw=ns+'-'+release,prefix=raw.slice(0,35).replace(/-$/,'')+'-'+crypto.createHash('sha256').update(raw).digest('hex').slice(0,12);
   const values=JSON.parse(fs.readFileSync('profiles/standard-site/values/runtime-access.json','utf8'));
   values.workloadNamespace='portable-product';values.hostLeaseNamespace='portable-product';values.allowedNodes=['arbitrary-worker'];values.hostLeaseNames=['neon-dsga-host-arbitrary-worker'];values.nodeReadClusterRole=prefix+'-nodes';
   const file=path.join(directory,tail+'.json');fs.writeFileSync(file,JSON.stringify(values));
   const rendered=spawnSync(process.env.HELM_BIN||'helm',['template',release,'charts/neon-control-runtime-access','-n',ns,'--kube-version','1.36.6','-f',file],{encoding:'utf8',timeout:30000});
   assert.equal(rendered.status,0,rendered.stderr);
   const docs=YAML.parseAllDocuments(rendered.stdout).map(d=>d.toJSON()).filter(Boolean);
   const inventory=docs.find(d=>d.kind==='ClusterRole'&&d.metadata.name===prefix+'-qualifier-inventory');assert.ok(inventory);
   const nodeRead=docs.find(d=>d.kind==='ClusterRole'&&d.metadata.name===prefix+'-nodes');assert.deepEqual(nodeRead.rules[0].resourceNames,['arbitrary-worker']);assert.deepEqual(nodeRead.rules[0].verbs,['get']);
   names.push(inventory.metadata.name);
  }
  assert.notEqual(names[0],names[1]);
 } finally {fs.rmSync(directory,{recursive:true,force:true});}
});
