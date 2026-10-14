import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {root,readJSON,helm,documents,merge,pinned} from './lib.mjs';
const output=path.join(root,'artifacts/helm');fs.mkdirSync(output,{recursive:true});
const results=[];
const functionsFixture={enabled:true,existingConfigSecret:'functions-common-ci',existingIssuerSecret:'functions-issuer-ci',proxyCASecret:'proxy-public-ca-ci',proxyCAKey:'ca.crt'};
const s3Fixture={enabled:true,origin:'http://192.168.146.100:30893',region:'us-east-2',labHTTP:true,serviceType:'NodePort',nodePort:30893};
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
  if(chart==='neon-control-plane') {
    const enabled=merge(profile,{functions:functionsFixture});
    const enabledFile=path.join(output,'functions-preview.json');fs.writeFileSync(enabledFile,JSON.stringify(enabled));
    const rendered=helm(['template','neon-control','charts/'+chart,'-f',enabledFile,'-n','neon','--kube-version','1.36.4']);
    const docs=documents(rendered.stdout);
    const api=docs.find(o=>o.kind==='Deployment'&&o.metadata.name==='neon-control-api');
    const worker=docs.find(o=>o.kind==='Deployment'&&o.metadata.name==='neon-control-worker');
    const web=docs.find(o=>o.kind==='Deployment'&&o.metadata.name==='neon-control-web');
    assert(api&&worker&&web);
    for(const deployment of [api,web]) {
      assert(!(deployment.spec.template.spec.volumes||[]).some(v=>v.secret?.secretName==='functions-issuer-ci'),'Issuer private keys must never be mounted into API/Web');
    }
    const issuer=worker.spec.template.spec.volumes.find(v=>v.name==='functions-issuer');
    assert.equal(issuer.secret.secretName,'functions-issuer-ci');
    assert.deepEqual(issuer.secret.items.map(i=>i.key),['guest-ca.key','artifact-tls.crt','artifact-tls.key']);
    for(const deployment of [api,worker]) {
      const env=deployment.spec.template.spec.containers[0].env;
      assert.equal(env.find(v=>v.name==='NEON_FUNCTIONS_PREVIEW_ENABLED')?.value,'true');
      assert.equal(env.find(v=>v.name==='NEON_FUNCTIONS_CONFIG_FILE')?.value,'/run/functions-common/config.json');
    }
    const service=docs.find(o=>o.kind==='Service'&&o.metadata.name==='neon-control-functions-artifact');
    assert.equal(service.spec.type,'ClusterIP');assert.equal(service.spec.selector['app.kubernetes.io/component'],'worker');
    assert.deepEqual(service.spec.ports,[{name:'artifact-tls',port:8790,targetPort:'artifact-tls'}]);
    const retirement=docs.find(o=>o.kind==='Role'&&o.metadata.name==='neon-control-functions-retirement');
    assert.deepEqual(retirement?.rules,[{apiGroups:[''],resources:['services'],verbs:['delete']}]);
    const binding=docs.find(o=>o.kind==='RoleBinding'&&o.metadata.name===retirement.metadata.name);
    assert.deepEqual(binding?.subjects,[{kind:'ServiceAccount',name:'neon-control-worker',namespace:'neon'}]);
    assert.deepEqual(binding?.roleRef,{apiGroup:'rbac.authorization.k8s.io',kind:'Role',name:retirement.metadata.name});
    assert(!objs.some(o=>o.metadata.name==='neon-control-functions-retirement'),'Disabled Functions must not grant Service deletion');
    fs.writeFileSync(path.join(output,'functions-preview.yaml'),rendered.stdout);
    const publicHTTP={enabled:true,origin:'http://192.168.146.101:30892',labHTTP:true,serviceType:'NodePort',nodePort:30892};
    const publicFile=path.join(output,'functions-public.json');
    fs.writeFileSync(publicFile,JSON.stringify(merge(enabled,{managedAuth:{publicOrigin:'http://192.168.146.100:30788'},functions:{publicHTTP}})));
    const publicRender=helm(['template','neon-control','charts/'+chart,'-f',publicFile,'-n','neon','--kube-version','1.36.4']);
    const publicDocs=documents(publicRender.stdout);
    const publicService=publicDocs.find(o=>o.kind==='Service'&&o.metadata.name==='neon-control-functions-http');
    assert.equal(publicService.spec.type,'NodePort');
    assert.deepEqual(publicService.spec.ports,[{name:'functions-http',port:8792,targetPort:'functions-http',nodePort:30892}]);
    assert.equal(publicService.spec.selector['app.kubernetes.io/component'],'api');
    const publicAPI=publicDocs.find(o=>o.kind==='Deployment'&&o.metadata.name==='neon-control-api');
    assert.equal(publicAPI.spec.template.spec.containers[0].env.find(e=>e.name==='NEON_FUNCTIONS_PUBLIC_ORIGIN')?.value,publicHTTP.origin);
    fs.writeFileSync(path.join(output,'functions-public.yaml'),publicRender.stdout);
    const s3File=path.join(output,'storage-s3.json');
    fs.writeFileSync(s3File,JSON.stringify(merge(profile,{backendCredentials:{enabled:true},objectStorage:{s3:s3Fixture}})));
    const s3Render=helm(['template','neon-control','charts/'+chart,'-f',s3File,'-n','neon','--kube-version','1.36.4']);
    const s3Docs=documents(s3Render.stdout);
    const s3Service=s3Docs.find(o=>o.kind==='Service'&&o.metadata.name==='neon-control-s3');
    assert.equal(s3Service.spec.selector['app.kubernetes.io/component'],'api');
    assert.deepEqual(s3Service.spec.ports,[{name:'s3',port:8793,targetPort:'s3',nodePort:30893}]);
    const s3API=s3Docs.find(o=>o.kind==='Deployment'&&o.metadata.name==='neon-control-api');
    assert.equal(s3API.spec.template.spec.containers[0].env.find(e=>e.name==='NEON_S3_PUBLIC_ORIGIN')?.value,s3Fixture.origin);
    assert(!objs.some(o=>o.kind==='Service'&&o.metadata.name==='neon-control-s3'),'Disabled S3 must not expose a listener Service');
    fs.writeFileSync(path.join(output,'storage-s3.yaml'),s3Render.stdout);
  }
  if(chart==='neon-core') {
    const hooks=objs.filter(o=>o.kind==='Job'&&o.metadata.annotations?.['helm.sh/hook']);
    for(const hook of hooks) {
      assert.equal(hook.metadata.annotations['meta.helm.sh/release-name'],'neon-core');
      assert.equal(hook.metadata.annotations['meta.helm.sh/release-namespace'],'neon');
      assert.equal(hook.metadata.labels['app.kubernetes.io/managed-by'],'Helm');
    }
    const product=hooks.find(o=>o.metadata.name==='neon-core-product-storage-init');
    assert.ok(product,'Enabled profile requires the dedicated bucket bootstrap');
    const pod=product.spec.template.spec,container=pod.containers[0];
    assert.equal(pod.automountServiceAccountToken,false);
    assert.equal(container.securityContext.readOnlyRootFilesystem,true);
    assert.equal(container.resources.limits.memory,'512Mi');
    assert.equal(container.env.find(v=>v.name==='GOMEMLIMIT').value,'128MiB');
    const root=container.env.find(v=>v.name==='MINIO_ROOT_PASSWORD').valueFrom.secretKeyRef.name;
    assert.notEqual(container.env.find(v=>v.name==='PRODUCT_SECRET_KEY').valueFrom.secretKeyRef.name,root);
    assert.ok(!container.args[0].includes('"s3:*"'),'Product policy cannot grant wildcard actions');
  }
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
    const observer=objs.find(o=>o.kind==='Role'&&o.metadata.name==='neon-control-worker-observer');
    assert.ok(observer,'Independent retirement requires Worker-only Pod observation');
    assert.deepEqual(observer.rules,[{apiGroups:[''],resources:['pods'],verbs:['get','list']}]);
    const binding=objs.find(o=>o.kind==='RoleBinding'&&o.metadata.name==='neon-control-worker-observer');
    assert.equal(binding.roleRef.name,observer.metadata.name);
    assert.deepEqual(binding.subjects,[{kind:'ServiceAccount',name:'neon-control-worker',namespace:'neon'}]);
    const apiRole=objs.find(o=>o.kind==='Role'&&o.metadata.name==='neon-control-api');
    assert.deepEqual(apiRole.rules.find(r=>r.apiGroups.includes('')&&r.resources.includes('pods')).verbs,['get']);
    for(const role of objs.filter(o=>o.kind==='Role'))for(const rule of role.rules) {
      if(rule.apiGroups.includes('')&&rule.resources.includes('pods'))
        assert.ok(rule.verbs.every(v=>['get','list','watch'].includes(v)),'No Pod mutation may be granted for retirement observation');
    }
    const combined=documents(helm(['template',chart,...args,'-n','neon','--set','worker.enabled=false','--kube-version','1.36.4']).stdout);
    assert.ok(!combined.some(o=>o.metadata.name==='neon-control-worker-observer'),'Disabled Worker must not retain its observer RBAC');
    assert.deepEqual(combined.find(o=>o.kind==='Role'&&o.metadata.name==='neon-control-api').rules.find(r=>r.apiGroups.includes('')&&r.resources.includes('pods')).verbs,['get','list']);
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
  ['neon-control-plane',{objectStorage:{enabled:true,existingSecret:''}}],
  ['neon-control-plane',{objectStorage:{enabled:false,s3:s3Fixture}}],
  ['neon-control-plane',{backendCredentials:{enabled:false},objectStorage:{s3:s3Fixture}}],
  ['neon-control-plane',{objectStorage:{s3:{...s3Fixture,origin:'http://192.168.146.100:30893/path'}}}],
  ['neon-control-plane',{objectStorage:{s3:{...s3Fixture,origin:'http://user@192.168.146.100:30893'}}}],
  ['neon-control-plane',{objectStorage:{s3:{...s3Fixture,labHTTP:false}}}],
  ['neon-control-plane',{functions:{enabled:true}}],
  ['neon-control-plane',{functions:functionsFixture,worker:{enabled:false}}],
  ['neon-control-plane',{functions:functionsFixture,objectStorage:{enabled:false}}],
  ['neon-control-plane',{functions:functionsFixture,api:{replicaCount:2}}],
  ['neon-control-plane',{functions:functionsFixture,worker:{replicaCount:2}}],
  ['neon-control-plane',{managedAuth:{publicOrigin:'http://192.168.146.100:30788'},functions:{...functionsFixture,publicHTTP:{enabled:true,origin:'http://192.168.146.100:30892',labHTTP:true}}}],
  ['neon-control-plane',{functions:{...functionsFixture,publicHTTP:{enabled:true,origin:'http://192.168.146.101:30892/path',labHTTP:true}}}],
  ['neon-control-plane',{functions:{enabled:false,publicHTTP:{enabled:true}}}],
  ['neon-control-plane',{managedAuth:{publicOrigin:'http://192.168.146.100:30788'},functions:{...functionsFixture,publicHTTP:{enabled:true,origin:'http://192.168.146.101:30892',labHTTP:false}}}],
  ['neon-core',{minio:{productStorage:{enabled:true,existingSecret:''}}}],
  ['neon-core',{minio:{bucket:'neon-product-blobs'}}],
  ['neonvm',{controller:{qemuDiskCacheSettings:'cache.no-flush=on',labAcknowledged:false}}],
]) {
  const file=path.join(output,chart+'.negative.json');fs.writeFileSync(file,JSON.stringify(merge(readJSON('profiles/lab/'+chart+'.json'),overlay)));
  assert.notEqual(helm(['template',chart,'charts/'+chart,'-f',file,'--kube-version','1.36.4'],{allowFailure:true}).status,0,'Unsafe configuration must fail: '+chart);
}
fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({result:'pass',charts:results,negativeCases:30,functionsPreviewRender:'pass',functionsPublicRender:'pass',s3CoreRender:'pass',workerOnlyIssuer:'pass',productionQualified:false},null,2)+'\n');
console.log(JSON.stringify({result:'pass',charts:results.length,negativeCases:30,functionsPreviewRender:'pass',functionsPublicRender:'pass',s3CoreRender:'pass'}));
