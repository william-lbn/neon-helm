#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {parseArgs} from 'node:util';
import {fileDigest} from './lib.mjs';
import {inspectHostPodLimits} from './host-pod-preflight.mjs';

const {values:flags}=parseArgs({options:{nodes:{type:'string'},leases:{type:'string'},pods:{type:'string'},'allowed-nodes':{type:'string'},'discover-hosts':{type:'boolean',default:false},output:{type:'string'}}});
for(const key of ['nodes','leases'])if(!flags[key])throw new Error('--'+key+' is required');
if(Boolean(flags['allowed-nodes'])===flags['discover-hosts'])throw new Error('Choose exactly one of --allowed-nodes or --discover-hosts');
const nodePath=path.resolve(flags.nodes),leasePath=path.resolve(flags.leases);
const nodes=JSON.parse(fs.readFileSync(nodePath,'utf8')),leases=JSON.parse(fs.readFileSync(leasePath,'utf8'));
let allowed=(flags['allowed-nodes']||'').split(',').map(value=>value.trim()).filter(Boolean);
const dns=/^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$/;
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const decimal=/^[1-9][0-9]*$/;
const require=(value,message)=>{if(!value)throw new Error(message);};
require(['NodeList','List'].includes(nodes.kind)&&Array.isArray(nodes.items)&&!nodes.metadata?.continue&&nodes.items.every(item=>item.kind==='Node'),'Complete unpaginated NodeList is required');
require(['LeaseList','List'].includes(leases.kind)&&Array.isArray(leases.items)&&!leases.metadata?.continue&&leases.items.every(item=>item.kind==='Lease'),'Complete unpaginated LeaseList is required');
if(flags['discover-hosts']){
  const controlRoles=['node-role.kubernetes.io/control-plane','node-role.kubernetes.io/master'];
  allowed=nodes.items.filter(node=>!controlRoles.some(role=>Object.hasOwn(node.metadata?.labels||{},role)||node.spec?.taints?.some(taint=>taint.key===role))).map(node=>node.metadata?.name).sort();
}
require(allowed.length>=1&&allowed.length<=16&&new Set(allowed).size===allowed.length&&allowed.every(name=>dns.test(name)),'allowed-nodes must contain 1..16 unique hostnames');
const byNode=new Map();for(const node of nodes.items){const m=node.metadata||{};require(m.name&&!byNode.has(m.name),'Duplicate/missing Node name');byNode.set(m.name,node);}
const byLease=new Map();for(const lease of leases.items){const m=lease.metadata||{},key=(m.namespace||'')+'/'+(m.name||'');require(m.namespace&&m.name&&!byLease.has(key),'Duplicate/missing Lease identity');byLease.set(key,lease);}
const rows=[];
for(const name of allowed){
  const node=byNode.get(name),issues=[];
  if(!node)issues.push('node-absent');
  const uid=node?.metadata?.uid,rv=node?.metadata?.resourceVersion;
  if(node&&!uuid.test(uid||''))issues.push('node-uid-invalid');
  if(node&&!decimal.test(rv||''))issues.push('node-resource-version-invalid');
  if(node?.metadata?.deletionTimestamp)issues.push('node-deleting');
  const ready=node?.status?.conditions?.some(condition=>condition.type==='Ready'&&condition.status==='True')===true;
  if(node&&!ready)issues.push('node-not-ready');
  if(node?.status?.conditions?.some(condition=>['MemoryPressure','DiskPressure','PIDPressure'].includes(condition.type)&&condition.status==='True'))issues.push('node-resource-pressure');
  if(node?.spec?.unschedulable===true)issues.push('node-cordoned');
  const leaseName='neon-dsga-host-'+name;
  const candidates=[...byLease.values()].filter(lease=>lease.metadata?.name===leaseName);
  let lease=null;if(candidates.length===1)lease=candidates[0];else if(candidates.length===0)issues.push('host-lease-absent');else issues.push('host-lease-namespace-ambiguous');
  if(lease){
    const m=lease.metadata||{},owners=m.ownerReferences||[];
    if(!uuid.test(m.uid||''))issues.push('lease-uid-invalid');
    if(!decimal.test(m.resourceVersion||''))issues.push('lease-resource-version-invalid');
    if(m.deletionTimestamp)issues.push('lease-deleting');
    if(m.annotations?.['internal.autoscaling.neon.tech/dsga-host-lease-v1']!=='1:'+uid+':'+name)issues.push('lease-marker-mismatch');
    if(!(owners.length===1&&owners[0].apiVersion==='v1'&&owners[0].kind==='Node'&&owners[0].name===name&&owners[0].uid===uid&&owners[0].controller===true))issues.push('lease-owner-mismatch');
  }
  rows.push({nodeName:name,nodeUID:uid||null,nodeResourceVersion:rv||null,nodeReady:ready,leaseNamespace:lease?.metadata?.namespace||null,leaseName,leaseUID:lease?.metadata?.uid||null,leaseResourceVersion:lease?.metadata?.resourceVersion||null,ready:issues.length===0,issues});
}
const podPath=flags.pods&&path.resolve(flags.pods);
const podPreflight=podPath?inspectHostPodLimits(JSON.parse(fs.readFileSync(podPath,'utf8')),allowed):null;
const identitiesReady=rows.every(row=>row.ready);
const receipt={apiVersion:'neon-dsga-site-inspection/v1',observedAt:new Date().toISOString(),inspectionScope:podPreflight?'identity-and-ordinary-pod-hard-limits':'identity-only',inputs:{nodes:{path:nodePath,sha256:fileDigest(nodePath)},leases:{path:leasePath,sha256:fileDigest(leasePath)},...(podPath?{pods:{path:podPath,sha256:fileDigest(podPath)}}:{})},allowedNodes:allowed,hosts:rows,identitiesReady,podPreflight,ready:identitiesReady&&(!podPreflight||podPreflight.ready),identitiesCreated:false,leasesCreated:false,budgetsInferred:false,hostBudgetsVerified:false,qualificationsIssued:false};
const text=JSON.stringify(receipt,null,2)+'\n';if(flags.output)fs.writeFileSync(path.resolve(flags.output),text,{encoding:'utf8',flag:'wx'});process.stdout.write(text);if(!receipt.ready)process.exitCode=2;
