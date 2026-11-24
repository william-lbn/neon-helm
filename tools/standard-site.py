#!/usr/bin/env python3
"""全新站点的有界初始化。Helm管理工作负载，原Controller/Owner管理运行身份与预算。"""
import argparse,base64,copy,decimal,fcntl,hashlib,json,os,pathlib,re,secrets,subprocess,time,urllib.parse,urllib.request
import yaml

def digest(data):return hashlib.sha256(data).hexdigest()
def quantity(value):
 match=re.fullmatch(r'([+]?(?:\d+(?:\.\d*)?|\.\d+))([eE][+-]?\d+|[KMGTPE]i|[numkMGTPE])?',str(value))
 if not match:raise ValueError('Invalid positive Kubernetes memory quantity')
 number=decimal.Decimal(match[1]);suffix=match[2] or '';binary={'Ki':10,'Mi':20,'Gi':30,'Ti':40,'Pi':50,'Ei':60};powers={'':0,'n':-9,'u':-6,'m':-3,'k':3,'M':6,'G':9,'T':12,'P':15,'E':18}
 number*=decimal.Decimal(2)**binary[suffix] if suffix in binary else decimal.Decimal(10)**(int(suffix[1:]) if suffix.startswith(('e','E')) and len(suffix)>1 else powers[suffix])
 if number<=0 or number!=int(number) or number>2**63-1:raise ValueError('Memory must be positive integral int64 bytes')
 return int(number)

class Site:
 def __init__(self,args):
  os.umask(0o077);self.args=args;self.file=pathlib.Path(args.site).resolve();self.config=json.loads(self.file.read_text());self.base=self.file.parent;self.state=pathlib.Path(args.state).resolve();self.state.mkdir(parents=True,mode=0o700,exist_ok=True)
  if self.state.is_symlink() or self.state.stat().st_uid!=os.getuid() or self.state.stat().st_mode&0o077:raise RuntimeError('Private owned state directory required')
  self.lock=(self.state/'lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.receipt=self.state/'receipt.json';self.identity=digest(self.file.read_bytes())
  self.report=json.loads(self.receipt.read_text()) if self.receipt.exists() else {'apiVersion':'neon-standard-site-receipt/v1','site':self.config['name'],'inputSHA256':self.identity,'status':'prepared','steps':{},'createdResources':[],'businessE2E':'NOT_RUN'}
  if self.report['inputSHA256']!=self.identity:raise RuntimeError('Original site input changed; preserve the original operation')
  if self.config['apiVersion']!='neon-standard-site/v1' or len(self.config['name'])>63 or not re.fullmatch('[a-z0-9]([-a-z0-9]*[a-z0-9])?',self.config['name']):raise RuntimeError('Unsupported named site contract')
  self.ns=self.config['namespaces'];self.entries=self.config['releases'];self.kubeconfig=pathlib.Path(self.config['kubeconfig']);self.helm=os.environ.get('HELM_BIN','helm');self.node=os.environ.get('NEON_NODE_BIN','node');self.domain=self.config['clusterDomain']
  if not re.fullmatch('[a-z0-9]([-a-z0-9.]*[a-z0-9])?',self.domain) or len(self.domain)>253 or '..' in self.domain:raise RuntimeError('Explicit valid clusterDomain required')
  if not self.kubeconfig.is_absolute() or not self.kubeconfig.is_file():raise RuntimeError('Explicit absolute kubeconfig required')
  os.environ['KUBECONFIG']=str(self.kubeconfig)
  if not re.fullmatch('neon-control-[a-z0-9]([-a-z0-9]*[a-z0-9])?',self.ns['platform']) or self.ns['platform']==self.ns['workload']:raise RuntimeError('Current native protocol requires a distinct neon-control-* platform namespace')
  for ns in self.ns.values():
   if len(ns)>63 or not re.fullmatch('[a-z0-9]([-a-z0-9]*[a-z0-9])?',ns):raise RuntimeError('Explicit DNS namespace required')
  self.values={id:json.loads((self.base/e['values']).read_text()) for id,e in self.entries.items()};self.wireNamespaces();self.save()
 def wireNamespaces(self):
  # 系统组件的发行命名空间是协议输入；产品/平台命名空间可以按站点改变。
  if self.ns['agent']!='kube-system' or self.ns['vmSystem']!='neonvm-system':raise RuntimeError('This chart release declares kube-system/neonvm-system for system components')
  ns=self.ns['workload'];platform=self.ns['platform'];auto=self.values['autoscaler'];core=self.values['core'];control=self.values['control'];gateway=self.values['gateway'];access=self.values['runtime-access']
  for id in ('metadata','adapter','core','pageserver','gateway','control'):self.entries[id]['namespace']=ns
  self.entries['runtime-access']['namespace']=platform;auto['dsga']['vmNamespace']=ns;auto['dsga']['agent']['runtimeSelectionNamespace']=platform;gateway['dsga']['agentNamespace']=self.ns['agent'];access.update(workloadNamespace=ns,agentNamespace=self.ns['agent'],hostLeaseNamespace=ns)
  prefix=(platform+'-'+self.entries['runtime-access']['release'])[:48].rstrip('-');control['dsga'].update(runtimeSelectionNamespace=platform,agentNamespace=self.ns['agent'],runtimeAccessRolePrefix=prefix,nodeReadClusterRole=access['nodeReadClusterRole']);control['api']['proxyHost']='proxy.'+ns+'.svc.'+self.domain;control['api']['computeControlHost']=self.entries['gateway']['release']+'.'+ns+'.svc';self.values['pageserver']['config']['clusterDomain']=self.domain
  for value,key in [(control['api'],'computeGatewayURL'),(auto['dsga']['agent'],'gatewayURL')]:
   u=urllib.parse.urlsplit(value[key])
   if u.scheme!='https' or u.port is None:raise RuntimeError('Explicit TLS Gateway port required')
   value[key]='https://'+self.entries['gateway']['release']+'.'+ns+'.svc:'+str(u.port)
  mgmt=core['storageController']['management'];self.values['pageserver']['config']['controllerEndpoint']='https://'+mgmt['serviceName']+'.'+ns+'.svc:'+str(mgmt['port'])+'/upcall/v1/';self.values['neonvm']['controller']['managedMemoryRetirement']['namespaces']=[ns]
 def save(self):
  pending=self.receipt.with_suffix('.pending');pending.write_text(json.dumps(self.report,indent=2,ensure_ascii=False)+'\n');pending.replace(self.receipt)
 def private(self,name,value):
  path=self.state/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');return path
 def command(self,*args,input=None,timeout=60):
  result=subprocess.run(args,input=input,capture_output=True,timeout=timeout)
  if result.returncode:
   self.private('command-errors/'+str(time.time_ns())+'.private.json',{'program':str(args[0]),'exit':result.returncode,'stdout':result.stdout.decode(errors='replace'),'stderr':result.stderr.decode(errors='replace')});raise RuntimeError(str(args[0])+' failed with exit '+str(result.returncode))
  return result.stdout
 def kube(self,*args):return json.loads(self.command('kubectl',*args,'-o','json'))
 def get(self,kind,name,ns=None):
  raw=self.command('kubectl',*(['-n',ns] if ns else []),'get',kind,name,'--ignore-not-found','-o','json');return json.loads(raw) if raw.strip() else None
 def phase(self,name,action):
  old=self.report['steps'].get(name)
  if old:
   if old['status']=='completed':return
   proof=None
   if name=='discover-and-bind-new-hosts' and not list((self.state/'resources').glob('Lease-*.private.json')):proof='no-host-lease-creation-intent-submitted'
   if name=='freeze-first-host-cas' and not (self.state/'host-activation-values.private.json').exists():proof='no-host-activation-input-submitted'
   if self.args.retry_phase!=name or proof is None:raise RuntimeError('Original phase '+name+' is unresolved; inspect its original intent, do not replay')
   self.report.setdefault('reconciliations',[]).append({'phase':name,'previous':copy.deepcopy(old),'proof':proof,'unix':time.time()});del self.report['steps'][name];self.save()
  self.report['steps'][name]={'status':'submitted','submittedUnix':time.time()};self.report['status']='running';self.save()
  try:action()
  except Exception as e:self.report['status']='incomplete';self.report['steps'][name]['errorType']=type(e).__name__;self.save();raise
  self.report['steps'][name].update(status='completed',finishedUnix=time.time());self.save();print(json.dumps({'phase':name,'status':'completed'}),flush=True)
 def create(self,obj):
  m=obj['metadata'];m.setdefault('labels',{})['neon.tech/site-bootstrap']=self.config['name'];self.private('resources/'+obj['kind']+'-'+m.get('namespace','cluster')+'-'+m['name']+'.private.json',obj)
  if self.get(obj['kind'],m['name'],m.get('namespace')):raise RuntimeError('Fresh bootstrap must not adopt existing '+obj['kind']+'/'+m['name'])
  actual=json.loads(self.command('kubectl','create','-f','-','-o','json',input=json.dumps(obj).encode()));self.report['createdResources'].append({'kind':obj['kind'],'namespace':m.get('namespace'),'name':m['name'],'uid':actual['metadata']['uid']});self.save();return actual
 def secret(self,name,data,ns=None,type='Opaque',immutable=False):
  obj={'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':ns or self.ns['workload']},'type':type,'stringData':data}
  if immutable:obj['immutable']=True
  return self.create(obj)
 def preflight(self):
  existing=json.loads(self.command(self.helm,'list','-A','-o','json'))
  if any(any(r['name']==e['release'] and r['namespace']==e['namespace'] for r in existing) for e in self.entries.values()):raise RuntimeError('Fresh install requires all selected releases absent')
  required=['certificates.cert-manager.io','network-attachment-definitions.k8s.cni.cncf.io']
  if self.values['neonvm'].get('network',{}).get('secondary',{}).get('enabled',True):required+=['ippools.whereabouts.cni.cncf.io']
  for crd in required:
   if not self.get('crd',crd):raise RuntimeError('Missing declared platform prerequisite '+crd)
  if self.get('crd','virtualmachines.vm.neon.tech') and self.kube('get','virtualmachines.vm.neon.tech','-A')['items']:raise RuntimeError('Existing VM requires original retirement')
  for n in self.kube('get','nodes')['items']:
   if any(k in n['metadata'].get('annotations',{}) for k in ('internal.autoscaling.neon.tech/dsga-host-ledger-v1','internal.autoscaling.neon.tech/dsga-host-origin-v1','internal.autoscaling.neon.tech/dsga-host-decommission-v1')):raise RuntimeError('Fresh install requires confirmed completion of the original Host domain cleanup')
  if any(v['spec'].get('claimRef',{}).get('namespace')==self.ns['workload'] for v in self.kube('get','persistentvolumes')['items']):raise RuntimeError('Old dedicated PVs remain; finish the original data cleanup before fresh installation')
  for ns in set(self.ns.values())|{e['namespace'] for e in self.entries.values()}:
   if not self.get('namespace',ns):self.create({'apiVersion':'v1','kind':'Namespace','metadata':{'name':ns}})
  self.report['serverVersion']=self.kube('version')['serverVersion']['gitVersion'];self.save()
 def rootCA(self,name):
  directory=self.state/'pki';directory.mkdir(exist_ok=True,mode=0o700);key=directory/(name+'.key');cert=directory/(name+'.crt')
  self.command('openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-days','3650','-subj','/CN='+self.config['name']+' '+name,'-addext','basicConstraints=critical,CA:TRUE,pathlen:0','-addext','keyUsage=critical,keyCertSign,cRLSign','-keyout',str(key),'-out',str(cert));return key,cert
 def credentials(self):
  core=self.values['core'];control=self.values['control'];metadata=self.values['metadata'];pageserver=self.values['pageserver'];adapter=self.values['adapter'];ns=self.ns['workload'];token=lambda:secrets.token_urlsafe(32)
  cpPassword=token();controllerPassword=token();admin=token();self.private('admin.private.json',{'username':'admin','password':admin})
  self.secret(metadata.get('existingSecret','neon-control-v2-db'),{'password':cpPassword});self.secret(control['api']['existingSecret'],{'database-url':'postgresql://'+metadata.get('username','neon_control_v2')+':'+cpPassword+'@'+metadata.get('fullnameOverride','neon-control-v2-db')+':5432/'+metadata.get('database','neon_control_v2')+'?sslmode=disable','admin-password':admin,'idempotency-key':base64.b64encode(secrets.token_bytes(32)).decode()})
  self.secret(core['storageController']['existingSecret'],{'password':controllerPassword,'url':'postgresql://neon_controller:'+controllerPassword+'@controller-db:5432/storage_controller'})
  self.secret(core['minio']['existingSecret'],{'accessKey':'neon'+secrets.token_hex(8),'secretKey':secrets.token_hex(16)});self.secret(core['proxy']['authSecret'],{'proxyToken':token()});self.secret(core['storageController']['hookTokenSecret'],{'token':token()})
  endpoint='http://minio.'+ns+'.svc.'+self.domain+':9000'
  if not self.config.get('allowLabHTTPObjectStorage'):raise RuntimeError('Internal MinIO requires the explicit lab HTTP profile; it is not production TLS acceptance')
  product=core['minio']['productStorage'];access='neon-product-'+secrets.token_hex(12);key=token();config={'endpoint':endpoint,'bucket':product.get('bucket','neon-product-blobs'),'region':core['minio']['region'],'access_key':access,'secret_key':key,'lab_http':True};self.secret(product['existingSecret'],{'accessKey':access,'secretKey':key,'config.json':json.dumps(config)},immutable=True)
  self.secret(adapter['routesSecret'],{'routes.json':'{}'});self.create({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':adapter['notificationsConfigMap'],'namespace':ns},'data':{'receipts.json':'{}'}})
  caKey,caCert=self.rootCA('storage-management');ca=caCert.read_text();mgmt=core['storageController']['management'];self.secret(mgmt['issuerName'],{'tls.key':caKey.read_text(),'tls.crt':ca},type='kubernetes.io/tls');self.create({'apiVersion':'cert-manager.io/v1','kind':'Issuer','metadata':{'name':mgmt['issuerName'],'namespace':ns},'spec':{'ca':{'secretName':mgmt['issuerName']}}})
  sign=self.state/'pki/storage-signing.key';self.command('openssl','genpkey','-algorithm','ED25519','-out',str(sign));public=self.command('openssl','pkey','-in',str(sign),'-pubout').decode()
  def jwt(scope):
   enc=lambda b:base64.urlsafe_b64encode(b).rstrip(b'=');message=enc(b'{"alg":"EdDSA","typ":"JWT"}')+b'.'+enc(json.dumps({'scope':scope},separators=(',',':')).encode());path=self.state/'pki/jwt-input.private';path.write_bytes(message);signature=self.command('openssl','pkeyutl','-sign','-rawin','-inkey',str(sign),'-in',str(path));return (message+b'.'+enc(signature)).decode()
  self.secret(mgmt['authSecret'],{'public_key':public,'pageserver_token':jwt('pageserverapi'),'safekeeper_token':jwt('safekeeperdata'),'peer_token':jwt('admin')});self.secret(adapter['storageManagement']['profile']['credential_secret_name'],{'public_key':public,'ca.crt':ca,'observe_token':jwt('scrubber')});self.secret(mgmt['pageserverUpcallSecret'],{'token':jwt('generations_api'),'ca.crt':ca})
  catalog=json.loads((self.base/self.config['catalogTemplate']).read_text());client=catalog['releases'][0]['creation']['storage']['credential_secret_name'];self.secret(client,{'public_key':public,'ca.crt':ca,'observe_token':jwt('scrubber'),'create_token':jwt('pageserverapi')})
  proxyKey,proxyRoot=self.rootCA('proxy-root');directory=self.state/'pki';key=directory/'proxy.key';csr=directory/'proxy.csr';cert=directory/'proxy.crt';host=control['api']['proxyHost'];ext=directory/'proxy-ext.cnf';ext.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:'+host+',DNS:proxy,DNS:proxy.'+ns+'.svc\n')
  self.command('openssl','req','-new','-newkey','rsa:2048','-nodes','-subj','/CN='+host,'-keyout',str(key),'-out',str(csr));self.command('openssl','x509','-req','-in',str(csr),'-CA',str(proxyRoot),'-CAkey',str(proxyKey),'-CAcreateserial','-days','365','-extfile',str(ext),'-out',str(cert));self.secret(core['proxy']['tlsSecret'],{'tls.key':key.read_text(),'tls.crt':cert.read_text(),'ca.crt':proxyRoot.read_text()},type='kubernetes.io/tls');self.secret(control['api']['pgCASecret'],{'ca.crt':proxyRoot.read_text()})
 def checkImages(self,refs):
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));registry=self.config['registry']
  for ref in sorted(refs):
   if not re.fullmatch(re.escape(registry)+r'/[a-zA-Z0-9/_-]+@sha256:[a-f0-9]{64}',ref):raise RuntimeError('All used images must be pinned in the declared site Harbor')
   repo,digestValue=ref.split('/',1)[1].split('@');base='http://'+registry;query=urllib.parse.urlencode({'service':'harbor-registry','scope':'repository:'+repo+':pull'})
   with opener.open(base+'/service/token?'+query,timeout=20) as r:issued=json.load(r)
   request=urllib.request.Request(base+'/v2/'+repo+'/manifests/'+digestValue,method='HEAD',headers={'Authorization':'Bearer '+(issued.get('token') or issued['access_token']),'Accept':'application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.index.v1+json'})
   with opener.open(request,timeout=20) as r:
    if r.status!=200:raise RuntimeError('Required Harbor image unavailable')
  self.report.setdefault('harborVerified',[]).extend(sorted(refs));self.save()
 def claimBootstrapNamespace(self,doc,entry):
  if doc.get('kind')!='Namespace':return
  name=doc['metadata']['name'];actual=self.get('namespace',name)
  if actual is None:return
  m=actual['metadata'];annotations=m.get('annotations',{});expected={'meta.helm.sh/release-name':entry['release'],'meta.helm.sh/release-namespace':entry['namespace']}
  if all(annotations.get(k)==v for k,v in expected.items()) and m.get('labels',{}).get('app.kubernetes.io/managed-by')=='Helm':return
  if not any(r['kind']=='Namespace' and r['name']==name and r['uid']==m['uid'] for r in self.report['createdResources']) or m.get('labels',{}).get('neon.tech/site-bootstrap')!=self.config['name'] or any(k in annotations and annotations[k]!=v for k,v in expected.items()):raise RuntimeError('Cannot adopt a namespace outside this original bootstrap intent')
  patched=dict(annotations,**expected);patch=[{'op':'test','path':'/metadata/uid','value':m['uid']},{'op':'test','path':'/metadata/resourceVersion','value':m['resourceVersion']},{'op':'test','path':'/metadata/labels/neon.tech~1site-bootstrap','value':self.config['name']},{'op':'add','path':'/metadata/labels/app.kubernetes.io~1managed-by','value':'Helm'},{'op':'add','path':'/metadata/annotations','value':patched}];self.private('namespace-ownership/'+name+'.json',{'originalUID':m['uid'],'patch':patch});self.command('kubectl','patch','namespace',name,'--type=json','-p',json.dumps(patch))
 def helmApply(self,id,stage=None,wait=True):
  e=self.entries[id];valuesFile=self.state/'values'/((stage or id)+'.private.json')
  if valuesFile.exists():
   if json.loads(valuesFile.read_text())!=self.values[id]:raise RuntimeError('Original Helm phase inputs changed; reconcile the frozen operation')
  else:self.private(str(valuesFile.relative_to(self.state)),self.values[id])
  chart=(self.base/e['chart']).resolve();render=self.command(self.helm,'template',e['release'],str(chart),'-n',e['namespace'],'--kube-version',self.report['serverVersion'],'-f',str(valuesFile));docs=[d for d in yaml.safe_load_all(render) if isinstance(d,dict)];refs=set()
  def collect(v):
   if isinstance(v,dict):
    for k,x in v.items():
     if k=='image' and isinstance(x,str):refs.add(x)
     else:collect(x)
   elif isinstance(v,list):
    for x in v:collect(x)
  for doc in docs:collect(doc)
  self.checkImages(refs);phase='helm-'+(stage or id)
  old=self.report['steps'].get(phase)
  if old and old['status']!='completed' and self.args.retry_phase==phase:
   resultFile=self.state/('helm/'+(stage or id)+'-result.json')
   if not resultFile.exists() or json.loads(resultFile.read_text())['exitCode']==0:raise RuntimeError('Retry requires a confirmed failed native Helm process')
   releases=json.loads(self.command(self.helm,'list','-A','--all','-o','json'))
   if any(r['name']==e['release'] and r['namespace']==e['namespace'] for r in releases):raise RuntimeError('Original release exists; reconcile its exact history instead of replaying install')
   self.report.setdefault('reconciliations',[]).append({'phase':phase,'previous':copy.deepcopy(old),'proof':'known-failed-helm-exit-and-release-absent','unix':time.time()});del self.report['steps'][phase];self.save()
  def apply():
   for doc in docs:self.claimBootstrapNamespace(doc,e)
   args=[self.helm,'upgrade','--install',e['release'],str(chart),'-n',e['namespace'],'--reset-values','-f',str(valuesFile),'--timeout','8m']
   if wait:args+=['--wait']
   result=subprocess.run(args,capture_output=True,timeout=520);self.private('helm/'+(stage or id)+'-result.json',{'exitCode':result.returncode,'stdoutSHA256':digest(result.stdout),'stderrSHA256':digest(result.stderr)});(self.state/('helm/'+(stage or id)+'.private.log')).write_bytes(result.stdout+result.stderr)
   if result.returncode:raise RuntimeError('Helm application failed; inspect original release history')
  self.phase(phase,apply)
 def trustGateway(self):
  e=self.entries['gateway'];p=self.values['gateway']['dsga']['pki'];name=p.get('rootSecretName') or (e['release']+'-dsga-root-ca')[:63].rstrip('-');secret=self.kube('-n',e['namespace'],'get','secret',name);ca=base64.b64decode(secret['data']['tls.crt']).decode();cert=self.state/'gateway-root-public.crt';cert.write_text(ca);text=self.command('openssl','x509','-in',str(cert),'-text','-noout').decode()
  if 'CA:TRUE' not in text or 'Certificate Sign' not in text:raise RuntimeError('Gateway trust requires a signing CA')
  p['agentCABundle']=ca;self.private('gateway-trust-values.private.json',self.values['gateway']);self.report['gatewayPublicCASHA256']=digest(ca.encode());self.save()
 def eligibleNodes(self):
  selected=[]
  for n in self.kube('get','nodes')['items']:
   m=n['metadata'];s=n['spec'];status=n['status'];labels=m.get('labels',{})
   if m.get('deletionTimestamp') or s.get('unschedulable') or any(k in labels for k in ('node-role.kubernetes.io/control-plane','node-role.kubernetes.io/master')) or labels.get('kubernetes.io/os')!='linux' or labels.get('kubernetes.io/arch')!='amd64' or any(t.get('effect') in ('NoSchedule','NoExecute') for t in s.get('taints',[])):continue
   kvm=status.get('allocatable',{}).get('neonvm/kvm')
   if not any(c['type']=='Ready' and c['status']=='True' for c in status['conditions']) or kvm is None or quantity(kvm)<1:continue
   if m.get('annotations',{}).get('internal.autoscaling.neon.tech/dsga-host-ledger-v1'):raise RuntimeError('Existing Host domain requires original settlement and decommission')
   selected.append(n)
  if not 1<=len(selected)<=16:raise RuntimeError('Current qualified Host protocol requires 1..16 eligible observed nodes')
  return sorted(selected,key=lambda n:n['metadata']['name'])
 def hosts(self):
  selected=self.eligibleNodes();auto=self.values['autoscaler'];d=auto['dsga'];policy=self.config['hostPolicy'];profile=policy['profile'];profileHash=digest(json.dumps({k:profile[k] for k in ('id','scheduler_name','vm_overhead_bytes','pod_overhead_bytes')},separators=(',',':')).encode());rows=[];identities={}
  for n in selected:
   m=n['metadata'];name=m['name'];uid=m['uid'];lease=self.create({'apiVersion':'coordination.k8s.io/v1','kind':'Lease','metadata':{'name':'neon-dsga-host-'+name,'namespace':self.ns['workload'],'annotations':{'internal.autoscaling.neon.tech/dsga-host-lease-v1':'1:'+uid+':'+name},'ownerReferences':[{'apiVersion':'v1','kind':'Node','name':name,'uid':uid,'controller':True}]},'spec':{}})
   binding={'node_name':name,'node_uid':uid,'namespace':self.ns['workload'],'lease_name':lease['metadata']['name'],'lease_uid':lease['metadata']['uid']};rows.append({'binding':binding,'profile':profile,'system_bytes':policy['systemBytes'],'initialize_at_resource_version':m['resourceVersion'],'kubernetes_budget':{'protocol_version':1,'scope':'kubernetes-node-memory-budget-v1','node_name':name,'node_uid':uid,'capacity_bytes':str(quantity(n['status']['capacity']['memory'])),'allocatable_bytes':str(quantity(n['status']['allocatable']['memory'])),'system_reservation_bytes':policy['systemBytes'],'profile_sha256':profileHash}});identities[name]=uid
  d['hostIdentities']=identities;d['scheduler']['nodes']=rows;d['scheduler']['enabled']=False;pods=self.kube('get','pods','-A')['items'];d['scheduler']['podProtectionNamespaces']=sorted({self.ns['platform']}|{p['metadata']['namespace'] for p in pods if p['spec'].get('nodeName') in identities and p['metadata']['namespace']!=self.ns['workload'] and p['status']['phase'] not in ('Succeeded','Failed')});access=self.values['runtime-access'];access.update(allowedNodes=sorted(identities),hostLeaseNamespace=self.ns['workload'],hostLeaseNames=[r['binding']['lease_name'] for r in rows]);self.private('hosts.private.json',{'autoscaler':auto,'runtime-access':access});self.report['selectedHosts']=[{'name':n['metadata']['name'],'uid':n['metadata']['uid']} for n in selected];self.save()
 def prepareSockets(self):
  auto=self.values['autoscaler'];directories=[v['hostDirectory'] for v in [auto['dsga']['agent']['resourceReadSocket'],auto['dsga']['agent']['controlSocket']] if v['enabled']]
  if any(not re.fullmatch('/run/[a-zA-Z0-9_.-]+',p) for p in directories):raise RuntimeError('Socket bootstrap is limited to explicit private directories directly under /run')
  commands=[]
  for p in directories:
   path='/host-run/'+p.removeprefix('/run/');commands.append('p='+path+'; if test -L "$p"; then exit 1; fi; if test -e "$p"; then test -d "$p"; test "$(stat -c %u:%a "$p")" = 0:700; else mkdir -m 700 "$p"; fi')
  script='set -eu\n'+'\n'.join(commands)+'\nsleep 600\n';labels={'app':'neon-site-socket-bootstrap','neon.tech/site-bootstrap':self.config['name']};ds={'apiVersion':'apps/v1','kind':'DaemonSet','metadata':{'name':'neon-site-socket-bootstrap','namespace':self.ns['platform']},'spec':{'selector':{'matchLabels':{'app':labels['app']}},'template':{'metadata':{'labels':labels},'spec':{'automountServiceAccountToken':False,'nodeSelector':{'kubernetes.io/os':'linux','kubernetes.io/arch':'amd64'},'affinity':{'nodeAffinity':{'requiredDuringSchedulingIgnoredDuringExecution':{'nodeSelectorTerms':[{'matchExpressions':[{'key':'kubernetes.io/hostname','operator':'In','values':[h['name'] for h in self.report['selectedHosts']]}]}]}}},'containers':[{'name':'prepare','image':self.values['core']['global']['initImage'],'command':['sh','-ec',script],'resources':{'requests':{'cpu':'10m','memory':'16Mi'},'limits':{'cpu':'100m','memory':'32Mi'}},'securityContext':{'runAsUser':0,'allowPrivilegeEscalation':False},'volumeMounts':[{'name':'run','mountPath':'/host-run'}]}],'volumes':[{'name':'run','hostPath':{'path':'/run','type':'Directory'}}]}}}}
  self.checkImages({self.values['core']['global']['initImage']});self.create(ds);self.command('kubectl','-n',self.ns['platform'],'rollout','status','daemonset/neon-site-socket-bootstrap','--timeout=120s',timeout=140);self.command('kubectl','-n',self.ns['platform'],'delete','daemonset','neon-site-socket-bootstrap','--wait=true','--timeout=90s',timeout=110)
 def activateHosts(self):
  auto=self.values['autoscaler'];d=auto['dsga'];tool=(pathlib.Path(__file__).resolve().parent/'host-pod-preflight.mjs').as_uri();code='import fs from "node:fs";import {inspectHostPodLimits} from '+json.dumps(tool)+';let input=JSON.parse(fs.readFileSync(0,"utf8"));console.log(JSON.stringify(inspectHostPodLimits(input.pods,input.hosts)));';deadline=time.monotonic()+120
  while True:
   pods=self.kube('get','pods','-A');observed=json.loads(self.command(self.node,'--input-type=module','-e',code,input=json.dumps({'pods':pods,'hosts':sorted(d['hostIdentities'])}).encode()));self.private('host-hard-limits.json',observed)
   if observed['ready']:break
   self.private('host-preflight-history/'+str(time.time_ns())+'.json',observed)
   if time.monotonic()>deadline:raise RuntimeError('Original ordinary Pod hard limits or termination state are not confirmed; inspect host-hard-limits.json')
   time.sleep(3)
  nodes={n['metadata']['name']:n for n in self.kube('get','nodes')['items']}
  for row in d['scheduler']['nodes']:
   n=nodes[row['binding']['node_name']];m=n['metadata']
   if m['uid']!=row['binding']['node_uid'] or m.get('annotations',{}).get('internal.autoscaling.neon.tech/dsga-host-ledger-v1'):raise RuntimeError('First Host initialization requires original unused identity')
   row['initialize_at_resource_version']=m['resourceVersion']
  d['scheduler']['enabled']=True;self.private('host-activation-values.private.json',auto)
 def verifyHosts(self):
  deadline=time.monotonic()+120;expected=self.values['autoscaler']['dsga']['hostIdentities']
  while time.monotonic()<deadline:
   seen={}
   for n in self.kube('get','nodes')['items']:
    m=n['metadata'];raw=m.get('annotations',{}).get('internal.autoscaling.neon.tech/dsga-host-ledger-v1')
    if m['name'] in expected and m['uid']==expected[m['name']] and raw:seen[m['name']]=json.loads(raw)
   if len(seen)==len(expected):self.private('initial-host-ledgers.private.json',seen);return
   time.sleep(3)
  raise RuntimeError('Initial Host CAS not confirmed; preserve original frozen RV')
 def wireStorage(self):
  ns=self.ns['workload'];core=self.values['core'];mgmt=core['storageController']['management'];service=self.kube('-n',ns,'get','service',mgmt['serviceName']);adapter=self.values['adapter'];name=adapter['storageManagement']['profile']['credential_secret_name'];secret=self.kube('-n',ns,'get','secret',name);adapter['storageManagement']['profile'].update(service_uid=service['metadata']['uid'],credential_secret_uid=secret['metadata']['uid']);self.private('adapter-bound-values.private.json',adapter)
 def catalog(self):
  catalog=json.loads((self.base/self.config['catalogTemplate']).read_text());ns=self.ns['workload'];nodes=self.values['runtime-access']['allowedNodes'];mgmt=self.values['core']['storageController']['management'];service=self.kube('-n',ns,'get','service',mgmt['serviceName'])
  for release in catalog['releases']:
   c=release['creation'];storage=c['storage'];storage.update(credential_namespace=ns,service_name=mgmt['serviceName'],service_uid=service['metadata']['uid']);secret=self.kube('-n',ns,'get','secret',storage['credential_secret_name']);storage['credential_secret_uid']=secret['metadata']['uid'];c['namespace']=ns;c['vm']['placement']['allowed_node_names']=nodes;supply=c['vm']['generic_guest']['supply'];supply.update(agent_namespace=self.ns['agent'],platform_namespace=self.ns['platform'],node_read_cluster_role=self.values['runtime-access']['nodeReadClusterRole'],host_leases=[{'namespace':ns,'name':name} for name in self.values['runtime-access']['hostLeaseNames']])
  refs=set()
  def collect(v):
   if isinstance(v,dict):
    for x in v.values():collect(x)
   elif isinstance(v,list):
    for x in v:collect(x)
   elif isinstance(v,str) and '@sha256:' in v:refs.add(v)
  collect(catalog);self.checkImages(refs);self.secret(self.values['control']['dsga']['runtimeCatalogSecret'],{'catalog.json':json.dumps(catalog,separators=(',',':'))});self.private('catalog-bound.private.json',catalog)
 def rollout(self,id):
  e=self.entries[id];manifest=self.command(self.helm,'get','manifest',e['release'],'-n',e['namespace'])
  for doc in yaml.safe_load_all(manifest):
   if isinstance(doc,dict) and doc.get('kind') in ('Deployment','DaemonSet','StatefulSet'):
    ns=doc['metadata'].get('namespace',e['namespace']);self.command('kubectl','-n',ns,'rollout','status',doc['kind'].lower()+'/'+doc['metadata']['name'],'--timeout=300s',timeout=320)
 def reconcileRelease(self,id,attempt):
  if id not in self.entries or not re.fullmatch('[0-9]{3}',attempt):raise RuntimeError('Explicit selected release and reconciliation attempt required')
  phase='helm-'+id;old=self.report['steps'].get(phase);result=self.state/('helm/'+id+'-result.json');frozen=self.state/('values/'+id+'.private.json');entry=self.entries[id]
  if old is None or old['status']=='completed' or not result.exists() or json.loads(result.read_text())['exitCode']==0:raise RuntimeError('Only an original confirmed failed native Helm process can be reconciled')
  history=json.loads(self.command(self.helm,'history',entry['release'],'-n',entry['namespace'],'--max','20','-o','json'));revision=history[-1]
  if revision['status']!='failed':raise RuntimeError('Original Helm revision is not a known failed terminal revision')
  values=json.loads(frozen.read_text());actual=json.loads(self.command(self.helm,'get','values',entry['release'],'-n',entry['namespace'],'-o','json'))
  if actual!=values:raise RuntimeError('Live Helm user inputs differ from the original frozen operation')
  intent='reconcile-'+id+'-'+attempt
  if intent in self.report.get('releaseReconciliations',{}):raise RuntimeError('Original reconciliation exists; inspect it instead of replaying')
  self.report.setdefault('releaseReconciliations',{})[intent]={'status':'submitted','originalPhase':phase,'originalFailedRevision':revision['revision'],'frozenValuesSHA256':digest(frozen.read_bytes()),'unix':time.time()};self.save();self.values[id]=values;self.helmApply(id,id+'-reconcile-'+attempt);self.rollout(id);old.update(status='completed',resolvedBy=intent,originalNativeExit=json.loads(result.read_text())['exitCode']);self.report['releaseReconciliations'][intent]['status']='completed';self.save();print(json.dumps({'status':'reconciled','originalPhase':phase,'reconciliation':intent,'originalFailurePreserved':True}))
 def install(self):
  self.phase('fresh-preflight',self.preflight);self.phase('new-credentials-and-pki',self.credentials)
  # 循环依赖只推迟等待，不用旧UID或降级认证填充；对象始终由其原Helm release创建。
  self.helmApply('metadata');self.helmApply('neonvm');self.helmApply('gateway');self.phase('gateway-public-trust',self.trustGateway)
  if 'gateway-public-trust' in self.report['steps'] and self.report['steps']['gateway-public-trust']['status']=='completed':self.values['gateway']=json.loads((self.state/'gateway-trust-values.private.json').read_text())
  self.helmApply('gateway','gateway-trust');self.helmApply('pageserver','pageserver-pending-dependencies',False)
  ps=self.values['core']['storageController']['externalManagedPageserver'];ps['serviceUID']=self.kube('-n',self.ns['workload'],'get','service',ps['serviceName'])['metadata']['uid'];self.helmApply('core','core-pending-adapter',False);self.phase('bind-new-storage-identities',self.wireStorage);self.values['adapter']=json.loads((self.state/'adapter-bound-values.private.json').read_text());self.helmApply('adapter')
  for id in ('core','pageserver','gateway','metadata','neonvm'):self.phase('rollout-'+id,lambda id=id:self.rollout(id))
  self.phase('discover-and-bind-new-hosts',self.hosts);hosts=json.loads((self.state/'hosts.private.json').read_text());self.values.update(hosts);self.phase('private-owner-socket-directories',self.prepareSockets);self.helmApply('runtime-access');self.helmApply('autoscaler','autoscaler-agent-warmup');self.phase('agent-warmup-ready',lambda:self.rollout('autoscaler'));self.phase('freeze-first-host-cas',self.activateHosts);self.values['autoscaler']=json.loads((self.state/'host-activation-values.private.json').read_text());self.helmApply('autoscaler','autoscaler-host-activation');self.phase('confirm-original-host-cas',self.verifyHosts);self.phase('bind-new-runtime-catalog',self.catalog)
  control=self.values['control'];control['api']['creationEnabled']=True;control['dsga'].update(createEnabled=True,suspensionEnabled=True);self.helmApply('control');self.phase('control-runtime-ready',lambda:self.rollout('control'));self.report.update(status='installed',oldRuntimeLeaseOrServiceIdentityReused=False,existingPhysicalNodeUIDsObserved=True,businessE2E='NOT_RUN');self.save();print(json.dumps({'status':'installed','receipt':str(self.receipt),'businessE2E':'NOT_RUN'}))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['install','inspect','reconcile-helm']);parser.add_argument('--site',required=True);parser.add_argument('--state',required=True);parser.add_argument('--retry-phase');parser.add_argument('--release-id');parser.add_argument('--recovery-id');args=parser.parse_args();site=Site(args)
 if args.action=='install':site.install()
 elif args.action=='reconcile-helm':site.reconcileRelease(args.release_id,args.recovery_id)
 else:print(json.dumps({'status':site.report['status'],'steps':site.report['steps'],'receipt':str(site.receipt)},ensure_ascii=False))
if __name__=='__main__':main()
