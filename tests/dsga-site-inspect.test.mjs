import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';

const root=path.resolve(import.meta.dirname,'..');
const uid=i=>`00000000-0000-4000-8000-${String(i).padStart(12,'0')}`;
function fixture(){const names=['host-a','host-b'];return {nodes:{apiVersion:'v1',kind:'NodeList',items:names.map((name,i)=>({apiVersion:'v1',kind:'Node',metadata:{name,uid:uid(i+1),resourceVersion:String(10+i)},spec:{},status:{conditions:[{type:'Ready',status:'True'}]}}))},leases:{apiVersion:'coordination.k8s.io/v1',kind:'LeaseList',items:names.map((name,i)=>({apiVersion:'coordination.k8s.io/v1',kind:'Lease',metadata:{namespace:'neon',name:'neon-dsga-host-'+name,uid:uid(i+11),resourceVersion:String(20+i),annotations:{'internal.autoscaling.neon.tech/dsga-host-lease-v1':`1:${uid(i+1)}:${name}`},ownerReferences:[{apiVersion:'v1',kind:'Node',name,uid:uid(i+1),controller:true}]}}))}};}
function run(mutate){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'dsga-inspect-')),data=fixture();if(mutate)mutate(data);for(const key of ['nodes','leases'])fs.writeFileSync(path.join(dir,key+'.json'),JSON.stringify(data[key]));const result=spawnSync(process.execPath,['tools/dsga-site-inspect.mjs','--nodes',path.join(dir,'nodes.json'),'--leases',path.join(dir,'leases.json'),'--allowed-nodes','host-a,host-b'],{cwd:root,encoding:'utf8'});return {result,receipt:result.stdout?JSON.parse(result.stdout):null};}

test('complete original Node and Lease identities pass without creating state',()=>{const {result,receipt}=run();assert.equal(result.status,0,result.stderr);assert.equal(receipt.ready,true);assert(receipt.hosts.every(host=>host.ready));assert.equal(receipt.identitiesCreated,false);assert.equal(receipt.leasesCreated,false);});
test('missing original Host Lease fails closed with an auditable issue',()=>{const {result,receipt}=run(data=>data.leases.items.shift());assert.equal(result.status,2);assert.equal(receipt.ready,false);assert.deepEqual(receipt.hosts[0].issues,['host-lease-absent']);});
test('marker drift fails closed',()=>{const {result,receipt}=run(data=>data.leases.items[0].metadata.annotations={});assert.equal(result.status,2);assert(receipt.hosts[0].issues.includes('lease-marker-mismatch'));});
test('paginated snapshots are rejected before inspection',()=>{const {result}=run(data=>data.nodes.metadata={continue:'next'});assert.notEqual(result.status,0);assert.match(result.stderr,/Complete unpaginated NodeList/);});
