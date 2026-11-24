import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';
import YAML from 'yaml';

const root=path.resolve(import.meta.dirname,'..');
const fixture=()=>({image:{reference:'registry.invalid/gateway@sha256:'+'a'.repeat(64)},dsga:{enabled:true,agentNamespace:'system-agents',tlsSecret:'gateway-leaf',pki:{enabled:true,agentCASecret:'agent-public-ca',agentCABundle:'-----BEGIN CERTIFICATE-----\nRENDER_ONLY\n-----END CERTIFICATE-----\n'}}});
function render(v,error,release='site-gateway') {
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'gateway-pki-'));
 try {
  fs.writeFileSync(path.join(dir,'values.json'),JSON.stringify(v));
  const r=spawnSync(process.env.HELM_BIN||'helm',['template',release,'charts/compute-management-gateway','-n','product-new','--kube-version','1.36.6','-f',path.join(dir,'values.json')],{cwd:root,encoding:'utf8',timeout:20000});
  assert.ifError(r.error);
  if(error){assert.notEqual(r.status,0);assert.match(r.stderr,error);return [];}
  assert.equal(r.status,0,r.stderr);return YAML.parseAllDocuments(r.stdout).map(d=>d.toJSON()).filter(Boolean);
 } finally {fs.rmSync(dir,{recursive:true,force:true});}
}
test('dedicated PKI declares a real CA and a separate namespace-bound Gateway identity',()=>{
 const docs=render(fixture()),certs=docs.filter(d=>d.kind==='Certificate');assert.equal(certs.length,2);
 const ca=certs.find(d=>d.spec.isCA),leaf=certs.find(d=>!d.spec.isCA);assert.ok(ca.spec.usages.includes('cert sign'));assert.ok(ca.spec.usages.includes('crl sign'));
 assert.notEqual(ca.spec.secretName,leaf.spec.secretName);assert.notEqual(ca.spec.issuerRef.name,leaf.spec.issuerRef.name);assert.deepEqual(leaf.spec.dnsNames,['*.product-new.svc']);
 const trust=docs.find(d=>d.kind==='Secret');assert.equal(trust.metadata.namespace,'system-agents');assert.deepEqual(Object.keys(trust.data),['ca.crt']);
 const deployment=docs.find(d=>d.kind==='Deployment');assert.equal(deployment.spec.template.spec.volumes.some(v=>v.secret?.secretName===ca.spec.secretName),false);
});
test('root issuance can precede public CA projection without manufacturing a trust anchor',()=>{
 const v=fixture();v.dsga.pki.agentCABundle='';const docs=render(v);assert.equal(docs.filter(d=>d.kind==='Certificate').length,2);assert.equal(docs.some(d=>d.kind==='Secret'),false);
});
test('external management PKI remains available',()=>{
 const v=fixture();v.dsga.pki.enabled=false;assert.equal(render(v).some(d=>['Certificate','Issuer','Secret'].includes(d.kind)),false);
});
test('default PKI names fit Kubernetes limits for a long Helm release',()=>{
 for(const d of render(fixture(),null,'g'.repeat(53)).filter(d=>['Certificate','Issuer'].includes(d.kind))){assert.ok(d.metadata.name.length<=63);if(d.spec.commonName)assert.ok(d.spec.commonName.length<=64);}
});
for(const [name,change,error] of [
 ['disabled DSGA',v=>{v.dsga.enabled=false;},/requires DSGA/],
 ['root Secret reuse',v=>{v.dsga.pki.rootSecretName=v.dsga.tlsSecret;},/must be separate/],
 ['root Certificate reuse',v=>{v.dsga.pki.rootCertificateName=v.dsga.tlsSecret;},/must be separate/],
 ['issuer reuse',v=>{v.dsga.pki.selfSignedIssuerName='same';v.dsga.pki.caIssuerName='same';},/must be separate/],
 ['root private Secret projected to Agent',v=>{v.dsga.pki.agentCASecret='site-gateway-dsga-root-ca';},/separate public/],
 ['private key in Agent bundle',v=>{v.dsga.pki.agentCABundle+=['-----BEGIN','PRIVATE','KEY-----'].join(' ');},/public CA PEM only/],
 ['invalid public Secret name',v=>{v.dsga.pki.agentCASecret='*';},/public CA PEM only/],
])test('PKI rejects '+name,()=>{const v=fixture();change(v);render(v,error);});
