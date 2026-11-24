import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import test from 'node:test';
import YAML from 'yaml';

const profile=id=>JSON.parse(fs.readFileSync(`profiles/standard-site/values/${id}.json`,'utf8'));
function render(chart,values,expectedError) {
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'standard-primary-'));
 try {
  const file=path.join(dir,'values.json');fs.writeFileSync(file,JSON.stringify(values));
  const r=spawnSync(process.env.HELM_BIN||'helm',['template','portable',`charts/${chart}`,'-n','portable-product','--kube-version','1.36.6','-f',file],{encoding:'utf8',timeout:30000});
  if(expectedError){assert.notEqual(r.status,0);assert.match(r.stderr,expectedError);return [];}
  assert.equal(r.status,0,r.stderr);return YAML.parseAllDocuments(r.stdout).map(d=>d.toJSON()).filter(Boolean);
 } finally {fs.rmSync(dir,{recursive:true,force:true});}
}

test('标准站点只部署已选定的管理 Pageserver，保持认证存储入口',()=>{
 const values=profile('core');values.storageController.externalManagedPageserver.serviceUID='90000000-1111-4222-8333-000000000001';
 const docs=render('neon-core',values);
 assert.ok(docs.some(d=>d.kind==='Deployment'&&d.metadata.name==='storage-controller'));
 assert.ok(docs.some(d=>d.kind==='Service'&&d.metadata.name==='storage-controller-management'));
 assert.ok(!docs.some(d=>d.kind==='Deployment'&&d.metadata.name==='pageserver'));
 const deployment=docs.find(d=>d.kind==='Deployment'&&d.metadata.name==='storage-controller');
 assert.ok(deployment.spec.template.spec.containers[0].env.some(e=>e.name==='PUBLIC_KEY'));
 values.storageController.externalManagedPageserver={};render('neon-core',values,/needs a managed core or explicit external pageserver/);
});

test('主 CNI 模式不引入额外网卡和 VXLAN，保留 Controller 必需 IPAM',()=>{
 const docs=render('neonvm',profile('neonvm'));
 assert.ok(docs.some(d=>d.kind==='Deployment'&&d.metadata.name==='neonvm-controller'));
 assert.ok(docs.some(d=>d.kind==='DaemonSet'&&d.metadata.name==='neonvm-device-plugin'));
 assert.ok(!docs.some(d=>d.metadata.name==='neonvm-vxlan-controller'||d.metadata.name==='neonvm-overlay-for-pods'||d.metadata.name==='neonvm-overlay-for-vms'));
 assert.ok(docs.some(d=>d.kind==='NetworkAttachmentDefinition'&&d.metadata.name==='neonvm-overlay-ipam'));
 for(const d of docs.filter(d=>['Deployment','DaemonSet'].includes(d.kind))) {
  const terms=d.spec.template.spec.affinity?.nodeAffinity?.requiredDuringSchedulingIgnoredDuringExecution?.nodeSelectorTerms||[];
  for(const term of terms)for(const e of term.matchExpressions||[])if(['In','NotIn'].includes(e.operator))assert.ok(e.values?.length,`${d.metadata.name}: empty hostname set cannot become Kubernetes affinity`);
 }
});

test('复用站点模板不携带旧 Host、服务身份或 CA',()=>{
 const auto=profile('autoscaler');assert.deepEqual(auto.dsga.hostIdentities,{});assert.deepEqual(auto.dsga.scheduler.nodes,[]);
 assert.equal(profile('gateway').dsga.pki.agentCABundle,'');assert.equal(profile('adapter').storageManagement.profile.service_uid,'');
 assert.equal(profile('control').dsga.createEnabled,false);
 const catalog=JSON.parse(fs.readFileSync('profiles/standard-site/runtime-catalog-template.json','utf8'));
 for(const release of catalog.releases){assert.equal(release.creation.storage.service_uid,'');assert.equal(release.creation.storage.credential_secret_uid,'');assert.deepEqual(release.creation.vm.placement.allowed_node_names,[]);assert.deepEqual(release.creation.vm.generic_guest.supply.host_leases,[]);}
});
