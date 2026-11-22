import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';

const root=path.resolve(import.meta.dirname,'..');
const uid=i=>`00000000-0000-4000-8000-${String(i).padStart(12,'0')}`;
function fixture(){const names=['host-a','host-b'];return {nodes:{apiVersion:'v1',kind:'NodeList',items:names.map((name,i)=>({apiVersion:'v1',kind:'Node',metadata:{name,uid:uid(i+1),resourceVersion:String(10+i)},spec:{},status:{conditions:[{type:'Ready',status:'True'}]}}))},leases:{apiVersion:'coordination.k8s.io/v1',kind:'LeaseList',items:names.map((name,i)=>({apiVersion:'coordination.k8s.io/v1',kind:'Lease',metadata:{namespace:'neon',name:'neon-dsga-host-'+name,uid:uid(i+11),resourceVersion:String(20+i),annotations:{'internal.autoscaling.neon.tech/dsga-host-lease-v1':`1:${uid(i+1)}:${name}`},ownerReferences:[{apiVersion:'v1',kind:'Node',name,uid:uid(i+1),controller:true}]}}))}};}
function run(mutate,{discover=false,pods}={}){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'dsga-inspect-')),data=fixture();
  if(mutate)mutate(data);
  for(const key of ['nodes','leases'])fs.writeFileSync(path.join(dir,key+'.json'),JSON.stringify(data[key]));
  const args=['tools/dsga-site-inspect.mjs','--nodes',path.join(dir,'nodes.json'),'--leases',path.join(dir,'leases.json'),...(discover?['--discover-hosts']:['--allowed-nodes','host-a,host-b'])];
  if(pods){const file=path.join(dir,'pods.json');fs.writeFileSync(file,JSON.stringify(pods));args.push('--pods',file);}
  const result=spawnSync(process.execPath,args,{cwd:root,encoding:'utf8'});
  return {result,receipt:result.stdout?JSON.parse(result.stdout):null};
}

test('complete original Node and Lease identities pass without creating state',()=>{const {result,receipt}=run();assert.equal(result.status,0,result.stderr);assert.equal(receipt.ready,true);assert(receipt.hosts.every(host=>host.ready));assert.equal(receipt.identitiesCreated,false);assert.equal(receipt.leasesCreated,false);});
test('missing original Host Lease fails closed with an auditable issue',()=>{const {result,receipt}=run(data=>data.leases.items.shift());assert.equal(result.status,2);assert.equal(receipt.ready,false);assert.deepEqual(receipt.hosts[0].issues,['host-lease-absent']);});
test('marker drift fails closed',()=>{const {result,receipt}=run(data=>data.leases.items[0].metadata.annotations={});assert.equal(result.status,2);assert(receipt.hosts[0].issues.includes('lease-marker-mismatch'));});
test('paginated snapshots are rejected before inspection',()=>{const {result}=run(data=>data.nodes.metadata={continue:'next'});assert.notEqual(result.status,0);assert.match(result.stderr,/Complete unpaginated NodeList/);});
test('discovery excludes control-plane Nodes without copying a pinned worker name',()=>{
  const {result,receipt}=run(data=>data.nodes.items.push({apiVersion:'v1',kind:'Node',metadata:{name:'control',uid:uid(99),resourceVersion:'99',labels:{'node-role.kubernetes.io/control-plane':''}},status:{conditions:[{type:'Ready',status:'True'}]}}),{discover:true});
  assert.equal(result.status,0,result.stderr);assert.deepEqual(receipt.allowedNodes,['host-a','host-b']);assert.equal(receipt.inspectionScope,'identity-only');assert.equal(receipt.hostBudgetsVerified,false);
});
test('discovery cannot hide a worker whose original Host Lease is missing',()=>{
  const {result,receipt}=run(data=>data.leases.items.pop(),{discover:true});
  assert.equal(result.status,2);assert.equal(receipt.hosts.length,2);assert(receipt.hosts.find(host=>host.nodeName==='host-b').issues.includes('host-lease-absent'));
});
test('a deleting Node cannot pass identity readiness',()=>{
  const {result,receipt}=run(data=>data.nodes.items[0].metadata.deletionTimestamp='2026-11-22T00:00:00Z');
  assert.equal(result.status,2);assert(receipt.hosts[0].issues.includes('node-deleting'));
});
test('pod input distinguishes valid identity from missing init-container memory bounds',()=>{
  const pods={apiVersion:'v1',kind:'PodList',items:[{apiVersion:'v1',kind:'Pod',metadata:{name:'network-init',namespace:'system',uid:uid(100),resourceVersion:'100'},spec:{nodeName:'host-a',containers:[{name:'main',resources:{limits:{memory:'2Gi'}}}],initContainers:[{name:'init'}]},status:{phase:'Running'}}]};
  const {result,receipt}=run(null,{discover:true,pods});
  assert.equal(result.status,2);assert.equal(receipt.identitiesReady,true);assert.equal(receipt.ready,false);assert.equal(receipt.inspectionScope,'identity-and-ordinary-pod-hard-limits');assert.equal(receipt.podPreflight.hosts[0].issues[0].container,'init');assert.equal(receipt.hostBudgetsVerified,false);
});
