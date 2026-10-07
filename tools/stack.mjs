#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {parseArgs} from 'node:util';
import {root, readJSON, validatePlan, helm, kube, get, documents, lockedValues, rendered, privateDirectory,
  writePrivate, compatibleAdoption, clusterScoped, fileDigest} from './lib.mjs';

const {values: flags, positionals} = parseArgs({allowPositionals: true, options: {
  'overlay-dir': {type: 'string'}, output: {type: 'string'}, 'maintenance-window': {type: 'boolean'},
  'adopt-unowned': {type: 'boolean'}, profile: {type: 'string', default: 'lab'},
}});
const command = positionals[0] || 'plan';
const plan = validatePlan(readJSON('stack/stack.json'));
if (flags.profile !== 'lab') throw new Error('Only the explicitly acknowledged lab profile is runtime-qualified. See docs/PRODUCTION-GATES.md');
const selected = plan.steps;
const output = path.resolve(flags.output || path.join(root, 'artifacts', command + '-' + Date.now()));
const receipt = {command, startedAt: new Date().toISOString(), result: 'running', productionQualified: false, steps: []};
const restore = [];

function environment() {
  const nodes = get('nodes').items;
  if (nodes.length < 3 || nodes.some(n => n.status.nodeInfo.architecture !== 'amd64' ||
    !n.status.conditions.some(c => c.type === 'Ready' && c.status === 'True') ||
    n.status.conditions.some(c => ['MemoryPressure', 'DiskPressure'].includes(c.type) && c.status === 'True'))) throw new Error('Three ready amd64 nodes without resource pressure are required');
  for (const crd of ['certificates.cert-manager.io', 'network-attachment-definitions.k8s.cni.cncf.io', 'ippools.whereabouts.cni.cncf.io']) {
    if (!get('customresourcedefinition', crd)) throw new Error('Missing external prerequisite ' + crd);
  }
  // Fresh clusters advertise KVM after the first stage installs the device plugin.
  // Physical /dev/kvm and nested virtualization remain mandatory prerequisites.
  if (get('daemonset','neonvm-device-plugin','neonvm-system') && nodes.some(n => !n.status.allocatable['neonvm/kvm'])) throw new Error('KVM device capacity is required on every candidate node');
  const crd = get('customresourcedefinition', 'virtualmachines.vm.neon.tech');
  if (crd) {
    const vms = get('virtualmachines.vm.neon.tech', null, 'neon').items;
    if (vms.some(v => v.metadata.name.startsWith('cp-'))) throw new Error('Suspend owned managed Computes through the control API before this maintenance upgrade');
  }
  for (const [name, keys] of Object.entries({
    'neon-object-store':['accessKey','secretKey'], 'neon-controller-db':['password','url'],
    'neon-proxy-auth':['proxyToken'], 'neon-proxy-tls':['tls.crt','tls.key'],
    'neon-control-hook-auth':['token'], 'neon-control-v2-db':['password'],
    'neon-control-plane-credentials':['database-url','admin-password','idempotency-key'],
    'neon-backend-credential-keys-v1':['keyring.json'], 'neon-control-routes':['routes.json'],
  })) {
    const secret = get('secret', name, 'neon');
    if (!secret || keys.some(key => !secret.data?.[key])) throw new Error('Missing prerequisite Secret/key for ' + name);
    // Deliberately do not return or persist Secret.data in this receipt.
  }
  if (!get('configmap','neon-control-notifications','neon')) throw new Error('Initialize external mutable receipts state using bootstrap-state.mjs');
  return {nodes: nodes.map(n => n.metadata.name), existingVMCRD: Boolean(crd), transport: 'explicit-laboratory-exceptions'};
}
function activeOperations() {
  const pods = get('pods', null, 'neon').items.filter(p => p.metadata.labels?.['app.kubernetes.io/name'] === 'neon-control-v2-db' && p.status.phase === 'Running');
  if (!pods.length) return null; // Fresh metadata DB does not yet have product tables.
  const sql = "SELECT CASE WHEN to_regclass('public.operations') IS NULL THEN -1 ELSE 0 END";
  const shell = 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U neon_control_v2 -d neon_control_v2 -At -c ';
  const exists = kube(['-n','neon','exec',pods[0].metadata.name,'-c','postgres','--','sh','-c',shell + '"' + sql + '"']).stdout.trim();
  if (exists === '-1') return 0;
  return Number(kube(['-n','neon','exec',pods[0].metadata.name,'-c','postgres','--','sh','-c',shell + '"SELECT count(*) FROM operations WHERE state IN (\'queued\',\'running\',\'retry_wait\')"']).stdout.trim());
}
function adopt(step, content) {
  for (const obj of documents(content)) {
    if (!obj.metadata?.name) continue;
    const ns = clusterScoped(obj.kind) ? null : (obj.metadata.namespace || step.namespace);
    const current = get(obj.kind, obj.metadata.name, ns);
    if (!current) continue;
    const owner = current.metadata.annotations?.['meta.helm.sh/release-name'];
    if (owner === step.release && current.metadata.annotations?.['meta.helm.sh/release-namespace'] === step.namespace) continue;
    if (!flags['adopt-unowned']) throw new Error('Existing resource needs explicit unowned adoption: ' + obj.kind + '/' + obj.metadata.name);
    compatibleAdoption(obj, current);
    writePrivate(path.join(output, `${step.release}-${obj.kind}-${obj.metadata.name}.private.json`), JSON.stringify(current));
    const patch = [
      {op:'test',path:'/metadata/uid',value:current.metadata.uid},
      {op:'test',path:'/metadata/resourceVersion',value:current.metadata.resourceVersion},
    ];
    if (!current.metadata.labels) patch.push({op:'add',path:'/metadata/labels',value:{}});
    if (!current.metadata.annotations) patch.push({op:'add',path:'/metadata/annotations',value:{}});
    for (const [key,value] of [['app.kubernetes.io/managed-by','Helm']]) patch.push({op:'add',path:'/metadata/labels/'+key.replaceAll('/','~1'),value});
    for (const [key,value] of [['meta.helm.sh/release-name',step.release],['meta.helm.sh/release-namespace',step.namespace]]) patch.push({op:'add',path:'/metadata/annotations/'+key.replaceAll('/','~1'),value});
    kube([...(ns ? ['-n',ns] : []),'patch',obj.kind,obj.metadata.name,'--type=json','-p',JSON.stringify(patch)]);
    receipt.steps.push({action:'adopt-unowned',kind:obj.kind,namespace:ns,name:obj.metadata.name,uid:current.metadata.uid});
  }
}
function stopControllers() {
  for (const name of ['neon-control-api','neon-control-worker']) {
    const dep = get('deployment',name,'neon');
    if (!dep) continue;
    restore.push({name,replicas:dep.spec.replicas});
    kube(['-n','neon','scale','deployment/'+name,'--replicas=0']);
    kube(['-n','neon','wait','--for=delete','pod','-l','app.kubernetes.io/instance=neon-control-plane,app.kubernetes.io/component='+name.replace('neon-control-',''),'--timeout=120s'], {timeout:150000});
  }
}
function backupMetadata() {
  const pods = get('pods',null,'neon').items.filter(p => p.metadata.labels?.['app.kubernetes.io/name']==='neon-control-v2-db' && p.status.phase==='Running');
  if (!pods.length) return;
  const partial=path.join(output,'metadata-before.partial.private.sql');
  const complete=path.join(output,'metadata-before.private.sql');
  if(fs.existsSync(complete))throw new Error('Metadata backup destination exists');
  kube(['-n','neon','exec',pods[0].metadata.name,'-c','postgres','--','sh','-c',
    'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U neon_control_v2 -d neon_control_v2 --no-owner --no-acl'], {timeout:180000,stdoutFile:partial});
  const bytes=fs.statSync(partial).size;
  if(bytes===0)throw new Error('Metadata backup is empty; retain partial evidence');
  const sha256=fileDigest(partial);
  fs.renameSync(partial,complete);
  receipt.metadataBackup={sha256,bytes,streamed:true,restoreTested:false};
}
function backupRuntimeState() {
  for (const name of ['neon-control-routes','neon-control-plane-credentials','neon-backend-credential-keys-v1',
    'neon-control-v2-db','neon-controller-db','neon-proxy-auth','neon-proxy-tls','neon-control-hook-auth','neon-object-store']) {
    const obj=get('secret',name,'neon');
    if (obj) writePrivate(path.join(output,name+'.secret.private.json'),JSON.stringify(obj));
  }
  const obj=get('configmap','neon-control-notifications','neon');
  if(obj) writePrivate(path.join(output,'notifications.private.json'),JSON.stringify(obj));
}
function wait(step) {
  for (const item of step.health) {
    const [kind,ns,name] = item.split('/');
    kube(['-n',ns,'rollout','status',kind.toLowerCase()+'/'+name,'--timeout=300s'],{timeout:330000});
  }
  if (step.chart === 'neonvm') kube(['-n','neonvm-system','wait','certificate/neonvm-serving-cert','--for=condition=Ready','--timeout=120s'],{timeout:150000});
}

try {
  if (command === 'plan') {
    console.log(JSON.stringify({version:plan.version,profile:flags.profile,productionQualified:false,
      prerequisites:plan.prerequisites,steps:selected.map(s => ({release:s.release,namespace:s.namespace,chart:s.chart,dependsOn:s.dependsOn}))},null,2));
    process.exit(0);
  }
  if (!['render','inspect','preflight','apply','verify','package'].includes(command)) throw new Error('Expected plan/render/inspect/preflight/apply/verify/package');
  if (fs.existsSync(output)) throw new Error('Attempt directories are immutable; choose a new output');
  privateDirectory(output);
  if (['preflight','apply'].includes(command)) receipt.environment=environment();
  if (command==='apply') {
    if (!flags['maintenance-window']) throw new Error('Apply requires an explicitly reserved --maintenance-window');
    const active=activeOperations();
    if (active!==null && active!==0) throw new Error('Active Operations must finish before upgrade');
    backupMetadata();
    backupRuntimeState();
    stopControllers();
    if ((activeOperations() ?? 0)!==0) throw new Error('An Operation was admitted during maintenance preparation; resume original controllers before retry');
  }
  if (command==='package') {
    for (const directory of fs.readdirSync(path.join(root,'charts')).sort()) {
      const result=helm(['package','charts/'+directory,'--destination',output]);
      receipt.steps.push({action:'package',chart:directory});
      console.log(result.stdout.trim());
    }
    helm(['repo','index',output,'--url','https://github.com/william-lbn/neon-helm/releases/download/v'+plan.version]);
  } else if (command==='verify') {
    for (const step of selected) {wait(step);receipt.steps.push({release:step.release,ready:true});}
    const active=activeOperations();
    if ((active ?? 0)!==0) throw new Error('Active operations remain');
  } else if (command!=='preflight') {
    for (const step of selected) {
      const valueFile=path.join(output,step.chart+'.values.private.json');
      writePrivate(valueFile,JSON.stringify(lockedValues(step,flags['overlay-dir']),null,2));
      const content=rendered(step,valueFile);
      writePrivate(path.join(output,step.chart+'.rendered.private.yaml'),content);
      if(command==='inspect') {
        for(const obj of documents(content)) {
          if(!obj.metadata?.name)continue;
          const ns=clusterScoped(obj.kind)?null:(obj.metadata.namespace||step.namespace);
          const current=get(obj.kind,obj.metadata.name,ns);
          if(!current) {receipt.steps.push({action:'create',kind:obj.kind,namespace:ns,name:obj.metadata.name});continue;}
          const owner=current.metadata.annotations?.['meta.helm.sh/release-name'];
          if(owner!==step.release)compatibleAdoption(obj,current);
          receipt.steps.push({action:owner===step.release?'existing-release':'adopt-unowned',kind:obj.kind,namespace:ns,name:obj.metadata.name,uid:current.metadata.uid});
        }
      }
      if (command==='apply') {
        const status=helm(['status',step.release,'-n',step.namespace,'-o','json'],{allowFailure:true});
        if (status.status===0) {
          writePrivate(path.join(output,step.release+'.previous-values.private.json'),helm(['get','values',step.release,'-n',step.namespace,'-a','-o','json']).stdout);
          writePrivate(path.join(output,step.release+'.previous-manifest.private.yaml'),helm(['get','manifest',step.release,'-n',step.namespace]).stdout);
        }
        adopt(step,content);
        // Atomic rollback cannot undo forward metadata migrations or durable
        // external side effects. Fail with evidence; never force-replace PVCs.
        const result=helm(['upgrade','--install',step.release,'charts/'+step.chart,'-n',step.namespace,
          '--reset-values','-f',valueFile,'--history-max','20','--wait','--timeout','10m'],{timeout:660000});
        writePrivate(path.join(output,step.release+'.upgrade.txt'),result.stdout);
        wait(step);
      }
      receipt.steps.push({release:step.release,chart:step.chart,rendered:true,applied:command==='apply'});
      console.log(step.release+': '+(command==='apply'?'Ready':'rendered'));
    }
  }
  receipt.result='pass';
} catch (error) {
  receipt.result='fail';receipt.error=error.message;process.exitCode=1;
} finally {
  for (const item of restore) {
    try {kube(['-n','neon','scale','deployment/'+item.name,'--replicas='+item.replicas]);}
    catch {receipt.controllerRestoreFailed=true;receipt.result='fail';process.exitCode=1;}
  }
  receipt.finishedAt=new Date().toISOString();
  if (fs.existsSync(output)) fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(receipt,null,2)+'\n',{mode:0o600});
  console.log(JSON.stringify({result:receipt.result,output,productionQualified:false,error:receipt.error}));
}
