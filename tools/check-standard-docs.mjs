// 当前中文产品入口的链接、层级和环境耦合检查；历史证据不改写。
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const docs=['README.md','docs/ARCHITECTURE.md','docs/DEPLOYMENT.md','docs/SITE-OVERLAY.md','docs/CLUSTER-PREREQUISITES.md','docs/SOURCE-PROVENANCE.md','docs/TESTING.md','docs/UPGRADE.md','docs/PRODUCTION-GATES.md',...fs.readdirSync(path.join(root,'docs/standard')).filter(n=>n.endsWith('.md')&&!n.startsWith('acceptance-')).map(n=>'docs/standard/'+n)];
const failures=[];
for(const name of docs){
 const file=path.join(root,name),text=fs.readFileSync(file,'utf8');
 if(!/[\u4e00-\u9fff]{2}/u.test(text))failures.push(name+': 缺少中文说明');
 for(const match of text.matchAll(/\[[^\]]*\]\(([^\s)]+)\)/g)){
  let target=match[1];if(/^(?:https?:|#)/.test(target))continue;
  target=decodeURIComponent(target.split('#')[0]);
  if(target&&!fs.existsSync(path.resolve(path.dirname(file),target)))failures.push(name+': 链接不存在 '+target);
 }
}
const profile=path.join(root,'profiles/standard-site');
const site=JSON.parse(fs.readFileSync(path.join(profile,'site.json'),'utf8'));
if(site.registry!=='registry.invalid'||site.name!=='configure-site'||!site.kubeconfig.startsWith('/CONFIGURE/'))failures.push('复用主模板必须使用显式占位值');
function walk(directory){return fs.readdirSync(directory,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(directory,e.name)):[path.join(directory,e.name)]);}
for(const file of walk(profile).filter(f=>f.endsWith('.json'))){
 const text=fs.readFileSync(file,'utf8');JSON.parse(text);
 if(/(?:\b(?:10|172|192)\.(?:\d{1,3}\.){2}\d{1,3}|\/etc\/rancher\/|rke2-lab|neon-standard-lab)/.test(text))failures.push(path.relative(root,file)+': 复用模板含现场值');
}
if(failures.length){process.stderr.write(failures.join('\n')+'\n');process.exit(1);}
console.log(JSON.stringify({status:'pass',chineseEntryDocuments:docs.length,reusableProfileEnvironmentCoupling:'absent'}));
