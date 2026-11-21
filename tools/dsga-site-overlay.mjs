#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {parseArgs} from 'node:util';
import {fileDigest,pinned,privateDirectory,writePrivate} from './lib.mjs';

const {values:flags}=parseArgs({options:{input:{type:'string'},nodes:{type:'string'},leases:{type:'string'},output:{type:'string'}}});
for(const key of ['input','nodes','leases','output'])if(!flags[key])throw new Error('--'+key+' is required');
const inputPath=path.resolve(flags.input),nodesPath=path.resolve(flags.nodes),leasesPath=path.resolve(flags.leases),output=path.resolve(flags.output);
const read=file=>JSON.parse(fs.readFileSync(file,'utf8'));
const input=read(inputPath),nodeList=read(nodesPath),leaseList=read(leasesPath);
const dns=/^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$/;
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const decimal=/^[1-9][0-9]{0,19}$/;
const require=(value,message)=>{if(!value)throw new Error(message);};
const canonical=value=>JSON.stringify(value,Object.keys(value).sort());
const profileDigest=profile=>crypto.createHash('sha256').update(JSON.stringify({id:profile.id,scheduler_name:profile.schedulerName,vm_overhead_bytes:profile.vmOverheadBytes,pod_overhead_bytes:profile.podOverheadBytes})).digest('hex');

require(input.apiVersion==='neon-dsga-site/v1'&&input.kind==='DSGASiteOverlay','Unsupported DSGA site contract');
require(['NodeList','List'].includes(nodeList.kind)&&Array.isArray(nodeList.items)&&!nodeList.metadata?.continue&&nodeList.items.every(item=>item.kind==='Node'),'Complete unpaginated NodeList is required');
require(['LeaseList','List'].includes(leaseList.kind)&&Array.isArray(leaseList.items)&&!leaseList.metadata?.continue&&leaseList.items.every(item=>item.kind==='Lease'),'Complete unpaginated LeaseList is required');
require(Array.isArray(input.hosts)&&input.hosts.length>=1&&input.hosts.length<=16,'hosts must contain 1..16 explicit domains');
const site=input.site||{},gateway=input.gateway||{},images=input.images||{},agent=input.agent||{};
for(const key of ['workloadNamespace','agentNamespace','runtimeSelectionNamespace'])require(dns.test(site[key]||''),'Invalid site namespace: '+key);
require(/^([0-9]+)$/.test(site.kubernetesMinor||''),'Invalid Kubernetes minor');
for(const key of ['scheduler','agent','gateway'])require(pinned.test(images[key]||''),'Digest-pinned image required: '+key);
require(new RegExp('^https://[A-Za-z0-9.-]+(?::[1-9][0-9]{0,4})?/?$').test(gateway.url||''),'Trusted HTTPS gateway URL is required');
for(const key of ['managementCASecret','tlsSecret'])require(dns.test(gateway[key]||''),'Existing gateway secret name required: '+key);
require(agent.resourceReadSocket?.enabled===true,'Dynamic runtime selection requires the original resource-read socket');
for(const key of ['hostDirectory','mountDirectory'])require(new RegExp('^/[A-Za-z0-9_./-]+$').test(agent.resourceReadSocket[key]||''),'Invalid resource-read socket directory');
require(/^[A-Za-z0-9][A-Za-z0-9_.-]*[.]sock$/.test(agent.resourceReadSocket.name||''),'Invalid resource-read socket name');

const nodes=new Map(),nodeUIDs=new Set();
for(const node of nodeList.items){const m=node.metadata||{};require(m.name&&!nodes.has(m.name),'Duplicate/missing Node name');require(uuid.test(m.uid||'')&&!nodeUIDs.has(m.uid),'Duplicate/invalid Node UID');require(decimal.test(m.resourceVersion||''),'Node resourceVersion must be positive decimal');nodes.set(m.name,node);nodeUIDs.add(m.uid);}
const leases=new Map(),leaseUIDs=new Set();
for(const lease of leaseList.items){const m=lease.metadata||{},key=(m.namespace||'')+'/'+(m.name||'');require(m.namespace&&m.name&&!leases.has(key),'Duplicate/missing Lease identity');require(uuid.test(m.uid||'')&&!leaseUIDs.has(m.uid),'Duplicate/invalid Lease UID');require(decimal.test(m.resourceVersion||'')&&!m.deletionTimestamp,'Lease must be live with resourceVersion');leases.set(key,lease);leaseUIDs.add(m.uid);}

const hostIdentities={},schedulerNodes=[],allowedNodeNames=[],hostLeaseNames=[];
const seenNames=new Set(),seenPinnedUIDs=new Set();
for(const host of input.hosts){
  require(dns.test(host.nodeName||'')&&!seenNames.has(host.nodeName),'Invalid/duplicate host nodeName');
  require(uuid.test(host.nodeUID||'')&&!seenPinnedUIDs.has(host.nodeUID),'Invalid/duplicate pinned nodeUID');
  require(dns.test(host.leaseNamespace||'')&&dns.test(host.leaseName||'')&&host.leaseName==='neon-dsga-host-'+host.nodeName,'Invalid Host Lease name/namespace');
  require(uuid.test(host.leaseUID||''),'Invalid pinned Lease UID');
  require(decimal.test(host.frozenNodeResourceVersion||''),'Frozen Node RV must be positive decimal');
  const node=nodes.get(host.nodeName);require(node,'Pinned Node is absent: '+host.nodeName);
  require(node.metadata.uid===host.nodeUID,'Node UID drift: '+host.nodeName);
  require(node.metadata.resourceVersion===host.frozenNodeResourceVersion,'Frozen Node RV drift: '+host.nodeName);
  const lease=leases.get(host.leaseNamespace+'/'+host.leaseName);require(lease,'Original Host Lease is absent: '+host.leaseName);
  require(lease.metadata.uid===host.leaseUID,'Lease UID drift: '+host.leaseName);
  require(lease.metadata.annotations?.['internal.autoscaling.neon.tech/dsga-host-lease-v1']==='1:'+host.nodeUID+':'+host.nodeName,'Host Lease marker mismatch: '+host.leaseName);
  const owners=lease.metadata.ownerReferences||[];
  require(owners.length===1&&owners[0].apiVersion==='v1'&&owners[0].kind==='Node'&&owners[0].name===host.nodeName&&owners[0].uid===host.nodeUID&&owners[0].controller===true,'Host Lease owner mismatch: '+host.leaseName);
  const profile=host.profile||{};
  require(profile.id&&profile.schedulerName==='autoscale-scheduler'&&decimal.test(profile.vmOverheadBytes||'')&&decimal.test(profile.podOverheadBytes||''),'Explicit Host profile is required');
  require(decimal.test(host.systemBytes||''),'Explicit systemBytes is required');
  const row={binding:{node_name:host.nodeName,node_uid:host.nodeUID,namespace:host.leaseNamespace,lease_name:host.leaseName,lease_uid:host.leaseUID},initialize_at_resource_version:host.frozenNodeResourceVersion,profile:{id:profile.id,scheduler_name:profile.schedulerName,vm_overhead_bytes:profile.vmOverheadBytes,pod_overhead_bytes:profile.podOverheadBytes},system_bytes:host.systemBytes};
  if(host.kubernetesBudget){const b=host.kubernetesBudget;for(const key of ['capacityBytes','allocatableBytes'])require(decimal.test(b[key]||''),'Explicit Kubernetes budget bytes are required');row.kubernetes_budget={protocol_version:1,scope:'kubernetes-node-memory-budget-v1',node_name:host.nodeName,node_uid:host.nodeUID,capacity_bytes:b.capacityBytes,allocatable_bytes:b.allocatableBytes,system_reservation_bytes:host.systemBytes,profile_sha256:profileDigest(profile)};}
  hostIdentities[host.nodeName]=host.nodeUID;schedulerNodes.push(row);allowedNodeNames.push(host.nodeName);hostLeaseNames.push(host.leaseName);seenNames.add(host.nodeName);seenPinnedUIDs.add(host.nodeUID);
}
allowedNodeNames.sort();schedulerNodes.sort((a,b)=>a.binding.node_name.localeCompare(b.binding.node_name));hostLeaseNames.sort();
const autoscaler={experimentalAcknowledged:true,compatibility:{expectedKubernetesMinor:site.kubernetesMinor,allowUntestedKubernetes:site.allowUntestedKubernetes===true},placement:{allowedNodeNames},images:{scheduler:images.scheduler,agent:images.agent},dsga:{enabled:true,pgVersion:17,vmNamespace:site.workloadNamespace,hostIdentities,agent:{gatewayURL:gateway.url,managementCASecret:gateway.managementCASecret,managementCAKey:gateway.managementCAKey||'ca.crt',tokenAudience:'neon-dsga-credential-broker',tokenExpirationSeconds:agent.tokenExpirationSeconds||600,requestTimeoutSeconds:agent.requestTimeoutSeconds||10,computeTimeoutSeconds:agent.computeTimeoutSeconds||100,pollIntervalSeconds:agent.pollIntervalSeconds||5,runtimeSelectionNamespace:site.runtimeSelectionNamespace,prepareQualifications:{},automaticMemory:{},cacheShadow:{},controlSocket:{enabled:false,hostDirectory:'',mountDirectory:'',name:''},resourceReadSocket:agent.resourceReadSocket},scheduler:{podProtectionNamespaces:input.podProtectionNamespaces||[],ordinaryStopSourceNames:[],nodes:schedulerNodes}}};
const runtimeAccess={workloadNamespace:site.workloadNamespace,agentNamespace:site.agentNamespace,agentDaemonSet:'autoscaler-agent',apiServiceAccount:input.controlPlane?.apiServiceAccount||'neon-control-api',workerServiceAccount:input.controlPlane?.workerServiceAccount||'neon-control-worker',qualifierServiceAccount:input.qualifier?.serviceAccount||'qualification-issuer',nodeReadClusterRole:input.controlPlane?.nodeReadClusterRole||'neon-control-runtime-worker-nodes',allowedNodes:allowedNodeNames,hostLeaseNamespace:input.hosts[0].leaseNamespace,hostLeaseNames};
require(input.hosts.every(h=>h.leaseNamespace===runtimeAccess.hostLeaseNamespace),'All Host Leases must share one explicit namespace');
const gatewayOverlay={placement:{allowedNodeNames},image:{reference:images.gateway,pullPolicy:'IfNotPresent'},dsga:{enabled:true,agentNamespace:site.agentNamespace,agentServiceAccount:'autoscaler-agent',tlsSecret:gateway.tlsSecret}};
// Qualification stays disabled; the chart's own fail-closed defaults provide every required value.
const qualifier={enabled:false};
const outputs={'neon-autoscaler.json':autoscaler,'neon-control-runtime-access.json':runtimeAccess,'compute-management-gateway.json':gatewayOverlay,'dsga-platform-qualifier.json':qualifier};
privateDirectory(output);
const hashes={};for(const [name,value] of Object.entries(outputs)){const text=JSON.stringify(value,null,2)+'\n';writePrivate(path.join(output,name),text);hashes[name]=crypto.createHash('sha256').update(text).digest('hex');}
const manifest={apiVersion:'neon-dsga-site-receipt/v1',generatedAt:new Date().toISOString(),inputs:{contract:{path:inputPath,sha256:fileDigest(inputPath)},nodes:{path:nodesPath,sha256:fileDigest(nodesPath)},leases:{path:leasesPath,sha256:fileDigest(leasesPath)}},outputs:hashes,hosts:allowedNodeNames,identitiesCreated:false,leasesCreated:false,budgetsInferred:false,qualificationsIssued:false,automaticMemoryConfigured:false,controlPlaneDSGAOverlayGenerated:false,controlPlaneBlocker:'Local neon-control-plane Chart does not implement the deployed dsga.* contract; use a source-bound Control Plane Chart before enabling creation.'};
writePrivate(path.join(output,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(JSON.stringify({result:'pass',output,hosts:allowedNodeNames,controlPlaneDSGAOverlayGenerated:false}));
