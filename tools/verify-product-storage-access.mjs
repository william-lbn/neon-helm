#!/usr/bin/env node
// Read-only real IAM probe. Retain the Job and receipt for UID-checked retirement.
// The product identity must list its bucket and be denied the database bucket.
import fs from 'node:fs';
import path from 'node:path';
import {parseArgs} from 'node:util';
import {helm, kube, get, pinned, privateDirectory, writePrivate} from './lib.mjs';

const {values} = parseArgs({options:{output:{type:'string'}}});
if(!values.output)throw new Error('--output requires a fresh private evidence directory');
const out=path.resolve(values.output);
if(fs.existsSync(out))throw new Error('Preserve the previous attempt; select a new output directory');
const core=JSON.parse(helm(['get','values','neon-lab','-n','neon','-a','-o','json']).stdout);
const product=core.minio?.productStorage;
if(!core.minio?.enabled||!product?.enabled||!pinned.test(core.minio.mcImage)||
   !/^neon-product-[a-z0-9-]{1,40}$/.test(product.bucket)||
   !/^[a-z0-9][a-z0-9.-]*$/.test(core.minio.bucket)||
   product.bucket===core.minio.bucket||!product.existingSecret||
   product.existingSecret===core.minio.existingSecret)throw new Error('Dedicated product IAM prerequisites are not satisfied');
privateDirectory(out);
const name='storage-access-'+Date.now();
const script=`set -eu
mc --config-dir /tmp/mc alias set probe http://minio:9000 "$PRODUCT_ACCESS_KEY" "$PRODUCT_SECRET_KEY" >/dev/null 2>&1
mc --config-dir /tmp/mc ls probe/${product.bucket} >/dev/null 2>&1
if mc --config-dir /tmp/mc ls probe/${core.minio.bucket} >/tmp/denial 2>&1; then
  echo 'Product identity unexpectedly listed database storage'; exit 1
fi
grep -Eiq 'Access.?Denied|Access Denied' /tmp/denial || { echo 'Expected explicit IAM denial, not a network error'; exit 1; }
echo '{"allowed_product_list":true,"denied_database_list":true,"data_deleted":false}'
`;
const job={apiVersion:'batch/v1',kind:'Job',metadata:{name,namespace:'neon',labels:{'app.kubernetes.io/managed-by':'neon-storage-verification'}},spec:{backoffLimit:0,activeDeadlineSeconds:120,template:{spec:{
  restartPolicy:'Never',automountServiceAccountToken:false,
  securityContext:{runAsNonRoot:true,runAsUser:65532,runAsGroup:65532,fsGroup:65532,seccompProfile:{type:'RuntimeDefault'}},
  containers:[{name:'iam',image:core.minio.mcImage,imagePullPolicy:'IfNotPresent',command:['/bin/sh','-ec'],args:[script],
    env:[{name:'GOMEMLIMIT',value:'128MiB'},{name:'PRODUCT_ACCESS_KEY',valueFrom:{secretKeyRef:{name:product.existingSecret,key:'accessKey'}}},
         {name:'PRODUCT_SECRET_KEY',valueFrom:{secretKeyRef:{name:product.existingSecret,key:'secretKey'}}}],
    resources:{requests:{cpu:'25m',memory:'128Mi'},limits:{cpu:'200m',memory:'512Mi'}},
    securityContext:{allowPrivilegeEscalation:false,readOnlyRootFilesystem:true,capabilities:{drop:['ALL']}},volumeMounts:[{name:'tmp',mountPath:'/tmp'}]}],
  volumes:[{name:'tmp',emptyDir:{sizeLimit:'16Mi'}}]
}}}};
const report={result:'running',linux_only:process.platform==='linux',job:name,data_deleted:false};
const save=()=>fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(report,null,2)+'\n',{mode:0o600});
writePrivate(path.join(out,'job.json'),JSON.stringify(job,null,2)+'\n');save();
try {
  if(process.platform!=='linux')throw new Error('Run the product IAM check on Linux');
  const created=JSON.parse(kube(['create','-f','-','-o','json'],{input:JSON.stringify(job)}).stdout);
  report.job_uid=created.metadata.uid;save();
  const deadline=Date.now()+150000;
  let pods=[];
  while(Date.now()<deadline) {
    const current=get('Job',name,'neon');
    if(!current||current.metadata.uid!==report.job_uid)throw new Error('Verification Job identity changed');
    pods=JSON.parse(kube(['-n','neon','get','pods','-l','job-name='+name,'-o','json']).stdout).items;
    if(pods.length===1&&['Succeeded','Failed'].includes(pods[0].status.phase))break;
    await new Promise(resolve=>setTimeout(resolve,2000));
  }
  if(pods.length!==1||!['Succeeded','Failed'].includes(pods[0].status.phase))throw new Error('IAM probe did not complete; retain its original Job');
  const pod=pods[0];
  if(!pod.metadata.ownerReferences?.some(o=>o.kind==='Job'&&o.uid===report.job_uid))throw new Error('Verification Pod owner changed');
  report.pod={name:pod.metadata.name,uid:pod.metadata.uid,phase:pod.status.phase};save();
  const log=kube(['-n','neon','logs',pod.metadata.name]).stdout;
  writePrivate(path.join(out,'iam.log'),log);
  if(pod.status.phase!=='Succeeded')throw new Error('Product IAM probe failed; retain the original log');
  const checks=JSON.parse(log.trim());
  if(checks.allowed_product_list!==true||checks.denied_database_list!==true||checks.data_deleted!==false)throw new Error('Invalid IAM receipt');
  report.checks=checks;report.result='pass';
} catch(error) {report.result='fail';report.error=error.message;throw error;}
finally {save();}
console.log(JSON.stringify(report));
