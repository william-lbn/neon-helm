import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {root,readJSON,helm,documents,merge,pinned} from './lib.mjs';
const output=path.join(root,'artifacts/helm');fs.mkdirSync(output,{recursive:true});
const results=[];
for(const chart of fs.readdirSync(path.join(root,'charts')).sort()) {
  const profile=readJSON('profiles/lab/'+chart+'.json');
  // Optional static Compute needs actual tenant identities at deployment time.
  // Synthetic IDs are restricted to this offline rendering fixture.
  if(chart==='neon-compute')Object.assign(profile.compute,{tenantId:'1'.repeat(32),timelineId:'2'.repeat(32)});
  const file=path.join(output,chart+'.json');fs.writeFileSync(file,JSON.stringify(profile));
  const args=['charts/'+chart,'-f',file];
  helm(['lint',...args,'--strict']);
  const result=helm(['template',chart,...args,'-n',chart==='neonvm'||chart==='neon-autoscaler'?'default':'neon','--kube-version','1.36.4']);
  const objs=documents(result.stdout);
  for(const obj of objs) {
    assert.notEqual(obj.kind,'Secret','Secrets must remain external');
    if(obj.kind==='PersistentVolumeClaim')assert.equal(obj.metadata.annotations?.['helm.sh/resource-policy'],'keep');
    const containers=obj.spec?.template?.spec?.containers||[];
    for(const c of [...containers,...(obj.spec?.template?.spec?.initContainers||[])])if(c.image)assert.match(c.image,pinned);
  }
  fs.writeFileSync(path.join(output,chart+'.yaml'),result.stdout);
  if(chart==='neon-adapter') {
    const deployment=objs.find(o=>o.kind==='Deployment');
    const pod=deployment.spec.template.spec;
    const container=pod.containers[0];
    assert.equal(deployment.spec.replicas,1);
    assert.equal(deployment.spec.strategy.type,'Recreate');
    assert.deepEqual(container.command,['/opt/neon-control/control-adapter']);
    assert.equal(container.securityContext.runAsUser,65532);
    assert.equal(container.securityContext.readOnlyRootFilesystem,true);
    assert.equal(pod.securityContext.fsGroup,65532);
    assert.equal(container.readinessProbe.httpGet.path,'/readyz');
    assert.equal(objs.filter(o=>o.kind==='ConfigMap').length,0,'Compiled adapter must not mount interpreter source or overwrite receipts');
    assert.equal(pod.volumes.filter(v=>v.secret&&v.secret.defaultMode===288).length,2,'Credentials use separate group-readable projected files');
    assert.equal(container.env.filter(v=>v.name.endsWith('_TOKEN_FILE')).length,2);
    const role=objs.find(o=>o.kind==='Role');
    assert.ok(role.rules.some(r=>r.resources.includes('services/proxy')&&r.resourceNames?.includes('http:storage-controller:1234')&&r.verbs.length===1&&r.verbs[0]==='get'));
    assert.ok(!role.rules.some(r=>r.verbs.includes('delete')),'Adapter must never delete workload or state');
  }
  if(chart==='neon-compute') {
    const retired=path.join(output,chart+'.retired.json');
    fs.writeFileSync(retired,JSON.stringify(merge(profile,{compute:{enabled:false}})));
    const retiredObjects=documents(helm(['template',chart,'charts/'+chart,'-f',retired,'-n','neon','--kube-version','1.36.4']).stdout);
    assert.equal(retiredObjects.filter(obj=>obj.kind==='VirtualMachine').length,0,'Retirement must release the static VM');
    assert.equal(retiredObjects.filter(obj=>obj.kind==='Service').length,1,'Retirement must retain the service identity');
  }
  if(chart==='neon-control-plane') {
    for(const name of ['neon-control-api','neon-control-worker']) {
      const deployment=objs.find(o=>o.kind==='Deployment'&&o.metadata.name===name);
      assert.ok(deployment,'API and Worker must be independently deployed');
      const env=deployment.spec.template.spec.containers[0].env;
      assert.equal(env.find(v=>v.name==='NEON_AUTH_ENABLED')?.value,'true');
      assert.equal(env.find(v=>v.name==='NEON_AUTH_LAB_HTTP')?.value,'true');
      assert.equal(env.find(v=>v.name==='NEON_AUTH_PUBLIC_ORIGIN')?.value,profile.managedAuth.publicOrigin);
      assert.match(env.find(v=>v.name==='NEON_AUTH_RUNTIME_IMAGE')?.value||'',pinned);
      assert.equal(env.find(v=>v.name==='NEON_AUTH_PG_CA_SECRET')?.value,profile.managedAuth.pgCASecret);
      assert.equal(env.find(v=>v.name==='NEON_AUTH_PG_SERVER_NAME')?.value,profile.managedAuth.pgServerName);
    }
  }
  const invalid=path.join(output,chart+'.invalid.json');fs.writeFileSync(invalid,JSON.stringify(merge(profile,{unknownSetting:true})));
  assert.notEqual(helm(['template',chart,'charts/'+chart,'-f',invalid,'--kube-version','1.36.4'],{allowFailure:true}).status,0,'Unknown settings must fail schema validation');
  results.push({chart,lint:'pass',render:'pass',unknownSettingRejected:true,objects:objs.length});
}
for(const [chart,overlay] of [
  ['neon-core',{validation:{labAcknowledged:false}}],
  ['neon-core',{safekeeper:{replicas:2}}],
  ['neon-metadata',{developmentAcknowledged:false}],
  ['neon-adapter',{compatibilityAcknowledged:false}],
  ['neon-adapter',{maxConcurrentWakes:0}],
  ['neon-adapter',{maxConcurrentWakes:65}],
  ['neon-adapter',{wakeTimeout:'301s'}],
  ['neon-adapter',{pageserverNodeID:0}],
  ['neon-control-plane',{api:{pitrEnabled:true,creationEnabled:false}}],
  ['neon-control-plane',{managedAuth:{labHTTP:false}}],
  ['neon-control-plane',{managedAuth:{runtimeImage:'williamluckyli/control-auth:latest'}}],
  ['neon-control-plane',{managedAuth:{pgCASecret:''}}],
  ['neonvm',{controller:{qemuDiskCacheSettings:'cache.no-flush=on',labAcknowledged:false}}],
]) {
  const file=path.join(output,chart+'.negative.json');fs.writeFileSync(file,JSON.stringify(merge(readJSON('profiles/lab/'+chart+'.json'),overlay)));
  assert.notEqual(helm(['template',chart,'charts/'+chart,'-f',file,'--kube-version','1.36.4'],{allowFailure:true}).status,0,'Unsafe configuration must fail: '+chart);
}
fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({result:'pass',charts:results,negativeCases:13,productionQualified:false},null,2)+'\n');
console.log(JSON.stringify({result:'pass',charts:results.length,negativeCases:13}));
