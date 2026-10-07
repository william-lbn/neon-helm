#!/usr/bin/env node
// Read-only audit. Results contain resource identities, never credentials.
import fs from 'node:fs';
import path from 'node:path';
import {parseArgs} from 'node:util';
import {root,readJSON,validatePlan,get,helm,documents,lockedValues,privateDirectory,writePrivate,pinned} from './lib.mjs';
const {values}=parseArgs({options:{'overlay-dir':{type:'string'},'pvc-before':{type:'string'},'state-before':{type:'string'},output:{type:'string'},'expect-zero':{type:'boolean'},'require-manifest-match':{type:'boolean'}}});
if(!values.output)throw new Error('Require immutable --output');
const output=path.resolve(values.output);
if(fs.existsSync(output))throw new Error('Evidence directory already exists');
privateDirectory(output);
const report={result:'running',productionQualified:false,releases:[],images:[],pvcIdentitiesPreserved:false};
try {
  const plan=validatePlan(readJSON('stack/stack.json'));
  for(const step of plan.steps) {
    const status=JSON.parse(helm(['status',step.release,'-n',step.namespace,'-o','json']).stdout);
    if(status.info.status!=='deployed')throw new Error('Release not deployed '+step.release);
    report.releases.push({release:step.release,namespace:step.namespace,revision:status.version,chart:step.chart});
    const file=path.join(output,step.chart+'.values.private.json');
    writePrivate(file,JSON.stringify(lockedValues(step,values['overlay-dir'])));
    const rendered=helm(['template',step.release,'charts/'+step.chart,'-n',step.namespace,'--kube-version','1.36.4','-f',file]).stdout;
    if(values['require-manifest-match']) {
      const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
      const normalize=text=>documents(text).map(canonical).sort((a,b)=>(a.kind+'/'+(a.metadata?.namespace||'')+'/'+a.metadata?.name).localeCompare(b.kind+'/'+(b.metadata?.namespace||'')+'/'+b.metadata?.name));
      // Helm records lifecycle hooks separately from the normal manifest. A
      // completed/deleted bucket-init hook must still be included in this check.
      const installed=helm(['get','manifest',step.release,'-n',step.namespace]).stdout+'\n---\n'+helm(['get','hooks',step.release,'-n',step.namespace]).stdout;
      if(JSON.stringify(normalize(rendered))!==JSON.stringify(normalize(installed)))throw new Error('Release manifest/hook differs from checked-out source '+step.release);
    }
    for(const obj of documents(rendered).filter(o=>['Deployment','DaemonSet'].includes(o.kind))) {
      const ns=obj.metadata.namespace||step.namespace;
      const current=get(obj.kind,obj.metadata.name,ns);
      if(!current)throw new Error('Workload missing '+obj.metadata.name);
      for(const expected of [...(obj.spec.template.spec.containers||[]),...(obj.spec.template.spec.initContainers||[])]) {
        const actual=[...(current.spec.template.spec.containers||[]),...(current.spec.template.spec.initContainers||[])].find(c=>c.name===expected.name);
        if(!actual||actual.image!==expected.image||!pinned.test(actual.image))throw new Error('Workload image differs '+obj.metadata.name+'/'+expected.name);
        report.images.push({namespace:ns,workload:obj.metadata.name,container:expected.name,image:actual.image});
      }
    }
  }
  const nodes=get('nodes').items;
  if(nodes.some(n=>!n.status.conditions.some(c=>c.type==='Ready'&&c.status==='True')))throw new Error('Node not Ready');
  report.nodes=nodes.map(n=>({name:n.metadata.name,version:n.status.nodeInfo.kubeletVersion}));
  const pvcs=get('persistentvolumeclaims',null,'neon').items;
  if(pvcs.some(p=>p.status.phase!=='Bound'))throw new Error('PVC not Bound');
  if(values['pvc-before']) {
    const before=JSON.parse(fs.readFileSync(values['pvc-before'],'utf8')).items;
    for(const old of before) {
      const current=pvcs.find(p=>p.metadata.name===old.metadata.name);
      if(!current||current.metadata.uid!==old.metadata.uid||current.spec.volumeName!==old.spec.volumeName)throw new Error('Durable PVC identity changed '+old.metadata.name);
    }
    report.pvcIdentitiesPreserved=true;
  }
  report.pvcs=pvcs.map(p=>({name:p.metadata.name,uid:p.metadata.uid,volume:p.spec.volumeName,phase:p.status.phase}));
  if(values['state-before']) {
    for(const file of fs.readdirSync(values['state-before']).filter(f=>f.endsWith('.secret.private.json'))) {
      const old=JSON.parse(fs.readFileSync(path.join(values['state-before'],file),'utf8'));
      const current=get('secret',old.metadata.name,'neon');
      if(!current||current.metadata.uid!==old.metadata.uid)throw new Error('External Secret identity changed '+old.metadata.name);
      // routes are intentionally rewritten by product tests; all other credentials
      // must remain byte-identical across this packaging-only upgrade.
      if(old.metadata.name!=='neon-control-routes'&&JSON.stringify(old.data)!==JSON.stringify(current.data))throw new Error('Credential data changed '+old.metadata.name);
    }
    report.externalSecretIdentitiesPreserved=true;
  }
  const managed=get('virtualmachines.vm.neon.tech',null,'neon').items.filter(v=>v.metadata.name.startsWith('cp-'));
  report.managedVMCount=managed.length;
  if(values['expect-zero']&&managed.length)throw new Error('Managed test Computes remain active');
  // VM removal is asynchronous: a runner can still consume resources while
  // its VM is already absent. Require actual Pod removal for the zero gate.
  const runners=get('pods',null,'neon').items.filter(p=>p.metadata.name.startsWith('cp-'));
  report.managedComputePods=runners.map(p=>({name:p.metadata.name,uid:p.metadata.uid,
    phase:p.status.phase,deletionTimestamp:p.metadata.deletionTimestamp||null}));
  if(values['expect-zero']&&runners.length)throw new Error('Managed Compute runner deletion is not complete');
  const pods=[];
  for(const ns of ['neon','neonvm-system','kube-system']) {
    for(const pod of get('pods',null,ns).items.filter(p=>p.status.phase==='Running'&&!p.metadata.name.startsWith('cp-'))) {
      if(!(pod.status.containerStatuses||[]).every(c=>c.ready))throw new Error('Running pod not Ready '+pod.metadata.name);
      pods.push({namespace:ns,name:pod.metadata.name,node:pod.spec.nodeName,containers:(pod.status.containerStatuses||[]).map(c=>({name:c.name,imageID:c.imageID,ready:c.ready}))});
    }
  }
  report.pods=pods;report.result='pass';
} catch(error) {report.result='fail';report.error=error.message;process.exitCode=1;}
writePrivate(path.join(output,'result.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({result:report.result,releases:report.releases.length,images:report.images.length,managedVMCount:report.managedVMCount,pvcIdentitiesPreserved:report.pvcIdentitiesPreserved,error:report.error}));
