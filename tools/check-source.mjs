import fs from 'node:fs';
import path from 'node:path';
import {root,readJSON,validatePlan,validateControlImagesLock,pinned,digest,documents} from './lib.mjs';
const failures=[];
function walk(dir) {
  return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e => {
    if(['.git','node_modules','artifacts','.local','dist'].includes(e.name))return [];
    const file=path.join(dir,e.name);
    if(e.isSymbolicLink())throw new Error('Source symlinks are not allowed');
    return e.isDirectory()?walk(file):[file];
  });
}
const files=walk(root);
for(const file of files) {
  const name=path.relative(root,file).replaceAll('\\','/');
  if(/\.(pem|key|dump|etl|db|pyc|ps1|tgz)$/.test(name)||/\.private\.|(^|\/)\.env/.test(name))failures.push('Private artifact '+name);
  // Two disabled legacy laboratory compatibility tools remain for old deployments.
  // The active Proxy/Storage adapter must be the compiled, source-locked Go image.
  if(name.endsWith('.py')&&!['charts/neon-core/files/compute_resizer.py','charts/neon-core/files/proxy_api.py'].includes(name))failures.push('Verification Python '+name);
  const value=fs.readFileSync(file,'utf8');
  if(/-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{24,}|sk-[A-Za-z0-9]{32,}/.test(value))failures.push('Credential pattern '+name);
}
const plan=validatePlan(readJSON('stack/stack.json'));
if(!/^locks\/control-plane-[a-f0-9]{7}\.json$/.test(plan.controlImagesLock||''))failures.push('Missing current control image lock');
else {
  const control=readJSON('profiles/lab/neon-control-plane.json');
  try{validateControlImagesLock(readJSON(plan.controlImagesLock),{
    api:control.api.image.reference,web:control.web.image.reference,auth:control.managedAuth.runtimeImage,
    dataapi:control.dataAPI.gatewayImage,postgrest:control.dataAPI.postgrestImage,
    gateway:readJSON('profiles/lab/compute-management-gateway.json').image.reference,
    adapter:readJSON('profiles/lab/neon-adapter.json').image,
  });}catch{failures.push('Control source/image lock disagrees with active profiles');}
}
if(readJSON('package.json').version!==plan.version)failures.push('Release package/stack version drift');
for(const chart of [...plan.steps.map(s=>s.chart),...plan.optionalCharts]) {
  for(const name of ['Chart.yaml','values.yaml','values.schema.json','.helmignore'])if(!fs.existsSync(path.join(root,'charts',chart,name)))failures.push('Missing '+chart+'/'+name);
  const meta=documents(fs.readFileSync(path.join(root,'charts',chart,'Chart.yaml'),'utf8'))[0];
  if(meta.name!==chart||meta.version!==plan.version)failures.push('Chart identity/version drift '+chart);
}
for(const name of fs.readdirSync(path.join(root,'profiles/lab'))) {
  const profile=readJSON('profiles/lab/'+name);
  const refs=JSON.stringify(profile).match(/[^"\s]+@sha256:[a-f0-9]{64}/g)||[];
  if(!refs.length||refs.some(ref=>!pinned.test(ref)||ref.includes('example.invalid')))failures.push('Invalid image lock '+name);
}
const adapter=readJSON('locks/adapter.json');
if(adapter.language!=='go'||adapter.source!=='https://github.com/william-lbn/control-plane'||!/^([a-f0-9]{40})$/.test(adapter.source_commit)||!pinned.test(adapter.image)||adapter.image!==readJSON('profiles/lab/neon-adapter.json').image)failures.push('Go adapter source/image drift');
if(failures.length)throw new Error(failures.join('\n'));
console.log(JSON.stringify({result:'pass',files:files.length,charts:10,productionQualified:false}));
