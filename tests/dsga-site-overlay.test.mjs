import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';

const root=path.resolve(import.meta.dirname,'..');
const image=name=>'registry.invalid/neon/'+name+'@sha256:'+name.charCodeAt(0).toString(16).padStart(2,'0').repeat(32);
const uid=i=>`00000000-0000-4000-8000-${String(i).padStart(12,'0')}`;
function fixture() {
  const names=['worker-117','worker-118','worker-119'];
  const nodes={apiVersion:'v1',kind:'NodeList',items:names.map((name,i)=>({apiVersion:'v1',kind:'Node',metadata:{name,uid:uid(i+1),resourceVersion:String(100+i)}}))};
  const leases={apiVersion:'coordination.k8s.io/v1',kind:'LeaseList',items:names.map((name,i)=>({apiVersion:'coordination.k8s.io/v1',kind:'Lease',metadata:{namespace:'neon',name:'neon-dsga-host-'+name,uid:uid(i+11),resourceVersion:String(200+i),annotations:{'internal.autoscaling.neon.tech/dsga-host-lease-v1':`1:${uid(i+1)}:${name}`},ownerReferences:[{apiVersion:'v1',kind:'Node',name,uid:uid(i+1),controller:true}]}}))};
  const input={apiVersion:'neon-dsga-site/v1',kind:'DSGASiteOverlay',site:{kubernetesMinor:'31',allowUntestedKubernetes:false,workloadNamespace:'neon',agentNamespace:'kube-system',runtimeSelectionNamespace:'neon-control-runtime'},images:{scheduler:image('scheduler'),agent:image('agent'),gateway:image('gateway')},gateway:{url:'https://neon-compute-management-gateway.neon.svc:8444',managementCASecret:'neon-dsga-management-ca',tlsSecret:'neon-dsga-gateway-tls'},agent:{resourceReadSocket:{enabled:true,hostDirectory:'/run/neon-dsga-resource',mountDirectory:'/run/neon-dsga-resource',name:'resource.sock'}},podProtectionNamespaces:['kube-system','neon-cert-manager','neonvm-system','neon-control-runtime'],hosts:names.map((nodeName,i)=>({nodeName,nodeUID:uid(i+1),leaseNamespace:'neon',leaseName:'neon-dsga-host-'+nodeName,leaseUID:uid(i+11),frozenNodeResourceVersion:String(100+i),profile:{id:'render-profile',schedulerName:'autoscale-scheduler',vmOverheadBytes:'3221225472',podOverheadBytes:'16777216'},systemBytes:'4294967296',kubernetesBudget:{capacityBytes:'25213054976',allocatableBytes:'25213054976'}}))};
  return {input,nodes,leases};
}
function run(mutator) {
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'dsga-site-'));
  const values=fixture();if(mutator)mutator(values);
  for(const key of ['input','nodes','leases'])fs.writeFileSync(path.join(directory,key+'.json'),JSON.stringify(values[key]));
  const output=path.join(directory,'output');
  const result=spawnSync(process.execPath,['tools/dsga-site-overlay.mjs','--input',path.join(directory,'input.json'),'--nodes',path.join(directory,'nodes.json'),'--leases',path.join(directory,'leases.json'),'--output',output],{cwd:root,encoding:'utf8'});
  return {directory,output,result};
}

test('verified snapshots produce only fail-closed site overlays and a provenance receipt',()=>{
  const {output,result}=run();assert.equal(result.status,0,result.stderr);
  const autoscaler=JSON.parse(fs.readFileSync(path.join(output,'neon-autoscaler.json')));
  assert.equal(autoscaler.dsga.enabled,true);assert.deepEqual(Object.keys(autoscaler.dsga.hostIdentities),['worker-117','worker-118','worker-119']);
  assert.deepEqual(autoscaler.dsga.agent.automaticMemory,{});assert.deepEqual(autoscaler.dsga.agent.prepareQualifications,{});
  const qualifier=JSON.parse(fs.readFileSync(path.join(output,'dsga-platform-qualifier.json')));assert.equal(qualifier.enabled,false);
  const manifest=JSON.parse(fs.readFileSync(path.join(output,'manifest.json')));
  assert.equal(manifest.identitiesCreated,false);assert.equal(manifest.leasesCreated,false);assert.equal(manifest.budgetsInferred,false);assert.equal(manifest.qualificationsIssued,false);assert.equal(manifest.controlPlaneDSGAOverlayGenerated,false);
  const helm=process.env.HELM_BIN||'helm';
  for(const [chart,namespace] of [['neon-autoscaler','default'],['neon-control-runtime-access','neon-control-runtime'],['compute-management-gateway','neon'],['dsga-platform-qualifier','neon-control-runtime']]) {
    const rendered=spawnSync(helm,['template','site-contract','charts/'+chart,'-n',namespace,'--kube-version','1.31.2','-f',path.join(output,chart+'.json')],{cwd:root,encoding:'utf8'});
    assert.equal(rendered.status,0,chart+': '+rendered.stderr);
  }
});

for(const [name,mutate,message] of [
  ['node UID drift',x=>{x.nodes.items[0].metadata.uid=uid(99);},/Node UID drift/],
  ['frozen RV drift',x=>{x.nodes.items[0].metadata.resourceVersion='999';},/Frozen Node RV drift/],
  ['missing original Lease',x=>{x.leases.items.shift();},/Original Host Lease is absent/],
  ['Lease UID drift',x=>{x.leases.items[0].metadata.uid=uid(99);},/Lease UID drift/],
  ['Lease marker drift',x=>{x.leases.items[0].metadata.annotations={};},/Host Lease marker mismatch/],
  ['Lease owner drift',x=>{x.leases.items[0].metadata.ownerReferences[0].uid=uid(99);},/Host Lease owner mismatch/],
])test(name+' is rejected without output qualification',()=>{const {result}=run(mutate);assert.notEqual(result.status,0);assert.match(result.stderr,message);});
