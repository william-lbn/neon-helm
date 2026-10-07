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
  if(chart==='neon-compute') {
    const retired=path.join(output,chart+'.retired.json');
    fs.writeFileSync(retired,JSON.stringify(merge(profile,{compute:{enabled:false}})));
    const retiredObjects=documents(helm(['template',chart,'charts/'+chart,'-f',retired,'-n','neon','--kube-version','1.36.4']).stdout);
    assert.equal(retiredObjects.filter(obj=>obj.kind==='VirtualMachine').length,0,'Retirement must release the static VM');
    assert.equal(retiredObjects.filter(obj=>obj.kind==='Service').length,1,'Retirement must retain the service identity');
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
  ['neon-control-plane',{api:{pitrEnabled:true,creationEnabled:false}}],
  ['neonvm',{controller:{qemuDiskCacheSettings:'cache.no-flush=on',labAcknowledged:false}}],
]) {
  const file=path.join(output,chart+'.negative.json');fs.writeFileSync(file,JSON.stringify(merge(readJSON('profiles/lab/'+chart+'.json'),overlay)));
  assert.notEqual(helm(['template',chart,'charts/'+chart,'-f',file,'--kube-version','1.36.4'],{allowFailure:true}).status,0,'Unsafe configuration must fail: '+chart);
}
fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({result:'pass',charts:results,negativeCases:6,productionQualified:false},null,2)+'\n');
console.log(JSON.stringify({result:'pass',charts:results.length,negativeCases:6}));
