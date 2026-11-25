#!/usr/bin/env python3
"""独占Neon站点的正式停域和卸载；所有变更绑定原对象UID，不强制删除VM。"""
import argparse,base64,copy,datetime,fcntl,hashlib,http.client,ipaddress,json,os,pathlib,re,secrets,socket,subprocess,time,urllib.parse,urllib.request
import yaml
from standard_contract import OperationContract,atomic_json,private_state,lock_state,safe_path,verify_images

LEDGER='internal.autoscaling.neon.tech/dsga-host-ledger-v1'
ORIGIN='internal.autoscaling.neon.tech/dsga-host-origin-v1'
NODE_GUARD='autoscaling.neon.tech/dsga-host-ledger-protection'
POD_GUARD='autoscaling.neon.tech/dsga-host-pod-protection'
EXIT_MARKER='internal.autoscaling.neon.tech/dsga-host-decommission-v1'
def sha(data):return hashlib.sha256(data).hexdigest()
def escaped(key):return key.replace('~','~0').replace('/','~1')

class UnixHTTP(http.client.HTTPConnection):
 def __init__(self,path):super().__init__('localhost',timeout=45);self.path=path
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(self.timeout);self.sock.connect(self.path)

class Cleanup:
 def __init__(self,args):
  os.umask(0o077);self.args=args;self.readonly=args.action=='inspect';self.file=safe_path(args.site);self.config=json.loads(self.file.read_text());self.state=private_state(args.state,self.readonly)
  self.lock=lock_state(self.state,self.readonly);self.receipt=safe_path(self.state/'receipt.json');self.ns=self.config['namespaces'];self.entries=self.config['releases'];self.helm=os.environ.get('HELM_BIN','helm');self.proxy=None
  if self.readonly:
   self.report=json.loads(self.receipt.read_text());return
  os.environ['KUBECONFIG']=self.config['kubeconfig']
  kubeconfig=pathlib.Path(self.config['kubeconfig'])
  if not kubeconfig.is_absolute() or not kubeconfig.is_file() or len(self.config['name'])>63 or not re.fullmatch('[a-z0-9]([-a-z0-9]*[a-z0-9])?',self.config['name']):raise RuntimeError('Explicit absolute kubeconfig and valid site name required')
  self.report=json.loads(self.receipt.read_text()) if self.receipt.exists() else {'site':self.config['name'],'inputSHA256':sha(self.file.read_bytes()),'status':'new','nonce':secrets.token_hex(16),'steps':{},'nodes':{},'deleted':[],'dataErased':False}
  if self.report['inputSHA256']!=sha(self.file.read_bytes()) or args.confirm_site!=self.config['name']:raise RuntimeError('Original exact site confirmation required')
  self.contract=OperationContract(self.file,self.config,self.report,fresh=not self.receipt.exists());self.checkContract()
  self.exclusive=[self.ns[k] for k in ('workload','platform','vmSystem')]
  if len(set(self.exclusive))!=3 or any(n in ('default','kube-system','kube-public','kube-node-lease','cert-manager','neon-cert-manager') for n in self.exclusive):raise RuntimeError('Only explicit dedicated product/platform/NeonVM namespaces can be erased')
  self.save()
 def checkContract(self):self.contract.check(self.kube('get','namespace','kube-system')['metadata']['uid'])
 def save(self):
  if self.readonly:raise RuntimeError('只读检查不能修改卸载收据')
  atomic_json(self.receipt,self.report)
 def private(self,name,value):
  return atomic_json(self.state/name,value)
 def command(self,*a,input=None,timeout=60):
  r=subprocess.run(a,input=input,capture_output=True,timeout=timeout)
  if r.returncode:
   self.private('command-errors/'+str(time.time_ns())+'.private.json',{'argv':list(a),'exit':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace')});raise RuntimeError(str(a[0])+' failed with exit '+str(r.returncode))
  return r.stdout
 def kube(self,*a):return json.loads(self.command('kubectl',*a,'-o','json'))
 def startProxy(self):
  path=self.state/'api.sock'
  if path.exists():raise RuntimeError('Original API proxy socket exists; inspect its owner before reuse')
  self.proxy=subprocess.Popen(['kubectl','proxy','--unix-socket',str(path),'--accept-hosts=^localhost$'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for _ in range(50):
   if path.exists():return
   if self.proxy.poll() is not None:raise RuntimeError('Private API proxy failed')
   time.sleep(.1)
  raise RuntimeError('Private API proxy not ready')
 def close(self):
  if self.proxy:
   self.proxy.terminate()
   try:self.proxy.wait(timeout=10)
   except subprocess.TimeoutExpired:self.proxy.kill();self.proxy.wait()
   path=self.state/'api.sock'
   if path.exists():path.unlink()
 def api(self,method,path,body=None,contentType='application/json'):
  c=UnixHTTP(str(self.state/'api.sock'))
  try:
   c.request(method,path,body=None if body is None else json.dumps(body).encode(),headers={'Content-Type':contentType});r=c.getresponse();raw=r.read();value=json.loads(raw) if raw else {};return r.status,value
  finally:c.close()
 def phase(self,name,action):
  self.checkContract()
  old=self.report['steps'].get(name)
  if old and old['status']=='completed':return
  if old:
   if self.args.resume_phase!=name or name not in ('end-native-host-domains','verify-clean-empty-state'):raise RuntimeError('Original phase '+name+' unresolved; inspect original object results')
   self.report.setdefault('reconciliations',[]).append({'phase':name,'unix':time.time(),'previous':copy.deepcopy(old),'mode':'observe-original-node-markers-before-continuing-unsubmitted-hosts'});self.save();action();old['status']='completed';self.save();print(json.dumps({'phase':name,'status':'completed','originalIntentContinued':True}),flush=True);return
  self.report['steps'][name]={'status':'submitted','unix':time.time()};self.save();action();self.report['steps'][name]['status']='completed';self.save();print(json.dumps({'phase':name,'status':'completed'}),flush=True)
 def deleteOriginal(self,path,uid):
  code,obj=self.api('GET',path)
  if code==404:return
  if code!=200 or obj['metadata']['uid']!=uid:raise RuntimeError('Original delete target changed')
  options={'apiVersion':'v1','kind':'DeleteOptions','propagationPolicy':'Background','preconditions':{'uid':uid,'resourceVersion':obj['metadata']['resourceVersion']}}
  self.private('delete-intents/'+sha(path.encode())+'.json',{'path':path,'options':options});code,result=self.api('DELETE',path,options)
  if code not in (200,202,404):raise RuntimeError('Original UID-conditional deletion not confirmed')
  self.report['deleted'].append({'path':path,'uid':uid});self.save()
 def metadata(self,dump=False):
  values=json.loads((self.state/'helm-values.private.json').read_text());entry=self.entries['metadata'];name=values['metadata'].get('fullnameOverride','neon-control-v2-db');pods=self.kube('-n',entry['namespace'],'get','pods','-l','app.kubernetes.io/name='+name)['items'];pods=[p for p in pods if p['status']['phase']=='Running' and not p['metadata'].get('deletionTimestamp')]
  if len(pods)!=1:raise RuntimeError('Unique original metadata database Pod required')
  script='export PGPASSWORD="$POSTGRES_PASSWORD"; export PGOPTIONS="-c statement_timeout=30000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=30000"; '
  if dump:script+='exec pg_dump --no-owner --no-acl --format=custom -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
  else:script+='exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT count(*) FROM operations WHERE state IN (\'queued\',\'running\',\'retry_wait\')"'
  output=self.command('kubectl','-n',entry['namespace'],'exec',pods[0]['metadata']['name'],'-c','postgres','--','sh','-ec',script,timeout=90)
  if dump:
   path=self.state/'archive/metadata-before.private.dump';path.parent.mkdir(parents=True,exist_ok=True)
   with path.open('xb') as file:file.write(output)
   self.report['metadataArchive']={'path':str(path),'sha256':sha(output),'bytes':len(output)};self.save();return
  if output.strip()!=b'0':raise RuntimeError('Active control-plane Operations must complete through their original workflow')
 def plan(self):
  if self.kube('get','virtualmachines.vm.neon.tech','-A')['items']:raise RuntimeError('Retire all Computes through original public Operations first')
  releases=json.loads(self.command(self.helm,'list','-A','-o','json'));selected=[];manifests={};values={}
  for id,e in self.entries.items():
   if not any(r['name']==e['release'] and r['namespace']==e['namespace'] for r in releases):raise RuntimeError('Selected release missing before cleanup planning')
   values[id]=json.loads(self.command(self.helm,'get','values',e['release'],'-n',e['namespace'],'--all','-o','json'));manifests[id]=[d for d in yaml.safe_load_all(self.command(self.helm,'get','manifest',e['release'],'-n',e['namespace'])) if isinstance(d,dict)];selected.append({'id':id,**e})
  self.private('helm-values.private.json',values);self.private('helm-manifests.private.json',manifests);nodes=self.kube('get','nodes');pods=self.kube('get','pods','-A');leases=self.kube('get','leases','-A');self.private('nodes-before.private.json',nodes);self.private('pods-before.private.json',pods);self.private('leases-before.private.json',leases)
  cluster=self.kube('get','namespace','kube-system')['metadata']['uid'];bindings=[r['binding'] for r in values['autoscaler']['dsga']['scheduler']['nodes']]
  for binding in bindings:
   n=next(n for n in nodes['items'] if n['metadata']['name']==binding['node_name']);m=json.loads(n['metadata']['annotations'][LEDGER])
   if n['metadata']['uid']!=binding['node_uid'] or m['holds'] or any(p.get('managed') or p.get('vm_uid') for p in m['placements']):raise RuntimeError('Original Host still has Compute capacity')
  ae=self.entries['autoscaler'];objects=manifests['autoscaler'];owners=set()
  for obj in objects:
   if obj.get('kind') in ('DaemonSet','Deployment'):
    ns=obj['metadata'].get('namespace',ae['namespace']);actual=self.kube('-n',ns,'get',obj['kind'],obj['metadata']['name']);owners.add(actual['metadata']['uid'])
  for rs in self.kube('get','replicasets','-A')['items']:
   if any(r['uid'] in owners for r in rs['metadata'].get('ownerReferences',[])):owners.add(rs['metadata']['uid'])
  writers=[p for p in pods['items'] if any(r['uid'] in owners for r in p['metadata'].get('ownerReferences',[]))]
  if not writers or any(POD_GUARD not in p['metadata'].get('finalizers',[]) for p in writers):raise RuntimeError('Original protected capacity writer inventory incomplete')
  pvcs=self.kube('get','pvc','-A')['items'];volumes=[];nodeMap={n['metadata']['name']:n for n in nodes['items']};storageRoots=self.config.get('storageRoots',[])
  if not storageRoots:raise RuntimeError('Explicit storageRoots required for physical Retain-volume cleanup')
  for pv in self.kube('get','pv')['items']:
   claim=pv['spec'].get('claimRef',{})
   if claim.get('namespace') not in self.exclusive:continue
   pvc=next((x for x in pvcs if x['metadata']['namespace']==claim['namespace'] and x['metadata']['name']==claim['name'] and x['metadata']['uid']==claim['uid']),None)
   if pvc is None or pvc['metadata'].get('annotations',{}).get('meta.helm.sh/release-name') not in [e['release'] for e in selected]:raise RuntimeError('PV lacks original selected Neon PVC ownership')
   host=pv['spec'].get('hostPath',{}).get('path') or pv['spec'].get('local',{}).get('path');parent=str(pathlib.PurePosixPath(host).parent) if host else '';child=pathlib.PurePosixPath(host).name if host else ''
   expected=pv['metadata']['name']+'_'+claim['namespace']+'_'+claim['name']
   if parent not in storageRoots or child!=expected or not re.fullmatch('[a-z0-9_.-]+',child) or not pv['metadata']['name'].startswith('pvc-'+claim['uid']):raise RuntimeError('Volume path is not an explicit original PVC child of a declared storage root')
   terms=pv['spec'].get('nodeAffinity',{}).get('required',{}).get('nodeSelectorTerms',[])
   if len(terms)!=1 or len(terms[0].get('matchExpressions',[]))!=1:raise RuntimeError('Single original local PV node affinity required')
   expression=terms[0]['matchExpressions'][0]
   if expression['key']!='kubernetes.io/hostname' or expression['operator']!='In' or len(expression['values'])!=1:raise RuntimeError('Exact local PV hostname required')
   node=nodeMap[expression['values'][0]];volumes.append({'pv':pv,'pvc':pvc,'root':parent,'child':child,'node':node['metadata']['name'],'nodeUID':node['metadata']['uid']})
  namespaceRefs={ns:self.kube('get','namespace',ns)['metadata']['uid'] for ns in self.exclusive};self.private('volume-plan.private.json',volumes);self.private('original-writers.private.json',writers);self.private('bindings.json',bindings)
  for ns in self.exclusive:
   self.private('archive/'+ns+'-secrets.private.json',self.kube('-n',ns,'get','secrets'));self.private('archive/'+ns+'-configmaps.private.json',self.kube('-n',ns,'get','configmaps'))
  network=[]
  for d in manifests['neonvm']:
   if d.get('kind')=='DaemonSet' and d['metadata'].get('labels',{}).get('app.kubernetes.io/component')=='vxlan-controller':
    ns=d['metadata'].get('namespace',self.ns['vmSystem']);actual=self.kube('-n',ns,'get','daemonset',d['metadata']['name']);uid=actual['metadata']['uid'];original=[p for p in pods['items'] if any(r['uid']==uid for r in p['metadata'].get('ownerReferences',[]))];nad=self.kube('-n',ns,'get','network-attachment-definition','neonvm-overlay-for-pods');cidr=str(ipaddress.ip_network(json.loads(nad['spec']['config'])['ipam']['range'],strict=True))
    network.append({'daemonSet':actual,'pods':original,'cidr':cidr,'image':next(c['image'] for c in actual['spec']['template']['spec']['containers'] if c['name']=='vxlan-controller'),'nodes':[{'name':p['spec']['nodeName'],'uid':nodeMap[p['spec']['nodeName']]['metadata']['uid']} for p in original]})
  self.private('legacy-network.private.json',network)
  shared=[]
  for kind in ('deployments','daemonsets'):
   for obj in self.kube('get',kind,'-A')['items']:
    m=obj['metadata'];status=obj.get('status',{});desired=obj['spec'].get('replicas',1) if kind=='deployments' else status.get('desiredNumberScheduled',0);ready=status.get('availableReplicas',0) if kind=='deployments' else status.get('numberReady',0)
    if m['namespace'] not in self.exclusive and m['uid'] not in owners and desired>0 and ready>=desired:shared.append({'kind':kind,'namespace':m['namespace'],'name':m['name'],'uid':m['uid']})
  self.private('shared-platform-before.json',shared)
  crds=[c for c in self.kube('get','crds')['items'] if c['metadata']['name'] in ('virtualmachines.vm.neon.tech','virtualmachinemigrations.vm.neon.tech','ippools.vm.neon.tech')];self.private('crds-before.private.json',crds);self.metadata();self.metadata(dump=True);self.report.update(status='planned',clusterUID=cluster,bindings=bindings,writerUIDs=[p['metadata']['uid'] for p in writers],namespaces=namespaceRefs,volumeCount=len(volumes),selectedReleases=selected);self.save()
 def stopWriters(self):
  # 先停止业务生产者；不伪造成功Operation，也不清任何VM/预算来源。
  entry=self.entries['control'];docs=json.loads((self.state/'helm-manifests.private.json').read_text())['control'];self.metadata()
  for d in docs:
   if d.get('kind')=='Deployment':self.command('kubectl','-n',d['metadata'].get('namespace',entry['namespace']),'scale','deployment/'+d['metadata']['name'],'--replicas=0')
  deadline=time.monotonic()+180
  while time.monotonic()<deadline:
   producers=self.kube('-n',entry['namespace'],'get','pods','-l','app.kubernetes.io/instance='+entry['release'])['items']
   if all(p['metadata'].get('deletionTimestamp') and len(p['status'].get('containerStatuses',[]))==len(p['spec']['containers']) and all('terminated' in c.get('state',{}) for c in p['status'].get('containerStatuses',[])) for p in producers):break
   time.sleep(3)
  else:raise RuntimeError('Original control-plane producers have not confirmed normal termination')
  self.metadata()
  if self.kube('get','virtualmachines.vm.neon.tech','-A')['items']:raise RuntimeError('VM appeared before domain shutdown')
  entry=self.entries['autoscaler'];self.command(self.helm,'uninstall',entry['release'],'-n',entry['namespace'],'--timeout','5m',timeout=330)
  deadline=time.monotonic()+240
  while time.monotonic()<deadline:
   current=self.kube('get','pods','-A');byUID={p['metadata']['uid']:p for p in current['items']};ready=True
   for uid in self.report['writerUIDs']:
    p=byUID.get(uid);statuses=p.get('status',{}).get('containerStatuses',[]) if p else []
    if not p or not p['metadata'].get('deletionTimestamp') or len(statuses)!=len(p['spec']['containers']) or any('terminated' not in c.get('state',{}) for c in statuses):ready=False
   if ready:return
   time.sleep(3)
  raise RuntimeError('Original capacity writer exit not confirmed; preserve protected Pods')
 def snapshot(self,pending):return {'nodes':self.kube('get','nodes'),'pods':self.kube('get','pods','-A'),'leases':self.kube('get','leases','-A'),'vms':self.kube('get','virtualmachines.vm.neon.tech','-A'),'hosts':pending,'writerUIDs':self.report['writerUIDs'],'observedUnix':int(time.time())}
 def endDomains(self):
  if self.kube('get','namespace','kube-system')['metadata']['uid']!=self.report['clusterUID']:raise RuntimeError('Cluster target changed')
  # 正常停写后原Lease仍有有限有效期；只等待到期，不篡改Owner或到期时间。
  deadline=time.monotonic()+180
  while True:
   leases=self.kube('get','leases','-A')['items'];pending=[]
   for b in self.report['bindings']:
    lease=next(l for l in leases if l['metadata']['namespace']==b['namespace'] and l['metadata']['name']==b['lease_name'])
    if lease['metadata']['uid']!=b['lease_uid']:raise RuntimeError('Original Host Lease changed')
    spec=lease['spec'];renew=datetime.datetime.fromisoformat(spec['renewTime'].replace('Z','+00:00')).timestamp()
    if time.time()<=renew+spec['leaseDurationSeconds']+2:pending.append(b['node_name'])
   if not pending:break
   if time.monotonic()>deadline:raise RuntimeError('Original Host Lease has not naturally expired')
   time.sleep(2)
  for binding in self.report['bindings']:
   name=binding['node_name'];path='/api/v1/nodes/'+urllib.parse.quote(name,safe='');code,node=self.api('GET',path)
   if code!=200 or node['metadata']['uid']!=binding['node_uid']:raise RuntimeError('Original Node changed')
   existing=self.report['nodes'].get(name);annotations=node['metadata'].get('annotations',{})
   if existing and annotations.get(EXIT_MARKER)==existing['marker'] and LEDGER not in annotations and ORIGIN not in annotations:self.report['nodes'][name]['status']='domain-ended';self.save();continue
   if existing:raise RuntimeError('Original Node CAS unresolved; do not refresh an unknown write')
   pending=[b for b in self.report['bindings'] if self.report['nodes'].get(b['node_name'],{}).get('status')!='domain-ended'];snapshot=self.snapshot(pending);file=self.private('domain-snapshots/'+name+'.private.json',snapshot)
   # 只读SDK门拒绝所有未结清/未知事实；原Lease自然到期后才可结束整个域。
   self.command(self.args.host_check,str(file));fresh=next(n for n in snapshot['nodes']['items'] if n['metadata']['name']==name);m=fresh['metadata'];marker=json.dumps({'nonce':self.report['nonce'],'nodeUID':m['uid'],'leaseUID':binding['lease_uid'],'ledgerSHA256':sha(m['annotations'][LEDGER].encode())},separators=(',',':'));self.report['nodes'][name]={'status':'submitted','marker':marker,'sourceRV':m['resourceVersion']};self.save()
   patch=[{'op':'test','path':'/metadata/uid','value':m['uid']},{'op':'test','path':'/metadata/resourceVersion','value':m['resourceVersion']},{'op':'test','path':'/metadata/annotations/'+escaped(LEDGER),'value':m['annotations'][LEDGER]},{'op':'test','path':'/metadata/annotations/'+escaped(ORIGIN),'value':m['annotations'][ORIGIN]},{'op':'test','path':'/metadata/finalizers','value':m['finalizers']},{'op':'add','path':'/metadata/annotations/'+escaped(EXIT_MARKER),'value':marker},{'op':'remove','path':'/metadata/annotations/'+escaped(LEDGER)},{'op':'remove','path':'/metadata/annotations/'+escaped(ORIGIN)},{'op':'replace','path':'/metadata/finalizers','value':[f for f in m['finalizers'] if f!=NODE_GUARD]}];self.private('node-intents/'+name+'.json',patch);code,result=self.api('PATCH',path,patch,'application/json-patch+json')
   if code!=200:raise RuntimeError('Original Node CAS not confirmed; inspect its original marker')
   self.report['nodes'][name]['status']='domain-ended';self.save()
 def handoffOrdinary(self):
  if any(v.get('status')!='domain-ended' for v in self.report['nodes'].values()) or len(self.report['nodes'])!=len(self.report['bindings']):raise RuntimeError('End every original Host domain before ordinary handoff')
  if self.kube('get','virtualmachines.vm.neon.tech','-A')['items']:raise RuntimeError('VM exists during ordinary handoff')
  nodes={b['node_name'] for b in self.report['bindings']}
  for p in self.kube('get','pods','-A')['items']:
   if p['spec'].get('nodeName') not in nodes:continue
   m=p['metadata']
   if any(r.get('kind')=='VirtualMachine' for r in m.get('ownerReferences',[])):raise RuntimeError('Never hand off a Runner or force its finalizer')
   annotations=m.get('annotations',{});keys=[k for k in annotations if k.startswith('internal.autoscaling.neon.tech/dsga-host-')];finalizers=m.get('finalizers',[])
   if POD_GUARD not in finalizers and not keys:continue
   patch=[{'op':'test','path':'/metadata/uid','value':m['uid']},{'op':'test','path':'/metadata/resourceVersion','value':m['resourceVersion']}]
   for key in keys:patch.extend([{'op':'test','path':'/metadata/annotations/'+escaped(key),'value':annotations[key]},{'op':'remove','path':'/metadata/annotations/'+escaped(key)}])
   if POD_GUARD in finalizers:patch.extend([{'op':'test','path':'/metadata/finalizers','value':finalizers},{'op':'replace','path':'/metadata/finalizers','value':[f for f in finalizers if f!=POD_GUARD]}])
   self.private('pod-handoff/'+m['uid']+'.json',{'namespace':m['namespace'],'name':m['name'],'patch':patch});code,result=self.api('PATCH','/api/v1/namespaces/'+m['namespace']+'/pods/'+m['name'],patch,'application/json-patch+json')
   if code!=200:raise RuntimeError('Original ordinary Pod handoff changed; inspect before continuing')
  for b in self.report['bindings']:self.deleteOriginal('/apis/coordination.k8s.io/v1/namespaces/'+b['namespace']+'/leases/'+b['lease_name'],b['lease_uid'])
 def verifyImage(self,image):
  verify_images(self.config,[image])
 def cleanupNamespace(self):
  if self.report.get('hostCleanupNamespace'):return self.report['hostCleanupNamespace']['name']
  name='neon-host-clean-'+self.report['nonce'][:10];obj={'apiVersion':'v1','kind':'Namespace','metadata':{'name':name,'labels':{'pod-security.kubernetes.io/enforce':'privileged','neon.tech/cleanup-intent':self.report['nonce']}}};self.private('host-cleanup-namespace-intent.json',obj);code,actual=self.api('POST','/api/v1/namespaces',obj)
  if code!=201:raise RuntimeError('Original host cleanup namespace creation unconfirmed')
  self.report['hostCleanupNamespace']={'name':name,'uid':actual['metadata']['uid']};self.save();return name
 def hostJob(self,name,node,image,script,volumes,mounts,network=False,env=None):
  actual=self.kube('get','node',node['name'])
  if actual['metadata']['uid']!=node['uid']:raise RuntimeError('Original cleanup Node was replaced')
  self.verifyImage(image);namespace=self.cleanupNamespace();job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':namespace,'labels':{'neon.tech/cleanup-intent':self.report['nonce']}},'spec':{'backoffLimit':0,'activeDeadlineSeconds':180,'template':{'metadata':{'labels':{'neon.tech/cleanup-intent':self.report['nonce']}},'spec':{'nodeName':node['name'],'hostNetwork':network,'dnsPolicy':'ClusterFirstWithHostNet' if network else 'ClusterFirst','automountServiceAccountToken':network,'restartPolicy':'Never','tolerations':[{'operator':'Exists'}],'containers':[{'name':'cleanup','image':image,'command':['sh','-ec',script],'env':env or [],'resources':{'requests':{'cpu':'10m','memory':'32Mi'},'limits':{'cpu':'300m','memory':'96Mi'}},'securityContext':{'runAsUser':0,'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL'],'add':['NET_ADMIN','NET_RAW'] if network else ['DAC_OVERRIDE']},'seccompProfile':{'type':'RuntimeDefault'}},'volumeMounts':mounts+[{'name':'tmp','mountPath':'/tmp'}]}],'volumes':volumes+[{'name':'tmp','emptyDir':{}}]}}}}
  self.private('host-jobs/'+name+'.json',job);code,actual=self.api('POST','/apis/batch/v1/namespaces/'+namespace+'/jobs',job)
  if code!=201:raise RuntimeError('Original host cleanup Job submission unconfirmed; inspect it')
  self.report.setdefault('hostJobs',[]).append({'name':name,'uid':actual['metadata']['uid'],'node':node['name'],'nodeUID':node['uid']});self.save()
  self.command('kubectl','-n',namespace,'wait','--for=condition=complete','job/'+name,'--timeout=200s',timeout=220);log=self.command('kubectl','-n',namespace,'logs','job/'+name,'-c','cleanup');(self.state/('host-jobs/'+name+'.log')).write_bytes(log)
  if b'"hostArtifactsAbsent":true' not in log:raise RuntimeError('Independent host artifact verification missing')
 def cleanupHosts(self):
  if self.kube('get','virtualmachines.vm.neon.tech','-A')['items']:raise RuntimeError('Retire every VM before host artifact cleanup')
  originalWriters=set(self.report['writerUIDs'])
  if any(p['metadata']['uid'] in originalWriters for p in self.kube('get','pods','-A')['items']):raise RuntimeError('Original capacity writer Pods still present after handoff')
  networks=json.loads((self.state/'legacy-network.private.json').read_text())
  for i,net in enumerate(networks):
   d=net['daemonSet'];m=d['metadata'];self.deleteOriginal('/apis/apps/v1/namespaces/'+m['namespace']+'/daemonsets/'+m['name'],m['uid']);uids={p['metadata']['uid'] for p in net['pods']};deadline=time.monotonic()+120
   while time.monotonic()<deadline:
    if not any(p['metadata']['uid'] in uids for p in self.kube('get','pods','-A')['items']):break
    time.sleep(2)
   else:raise RuntimeError('Original VXLAN writer has not terminated')
   script='''set -eu
if test -e /sys/class/net/neon-vxlan0; then ip -d link show dev neon-vxlan0 | grep -Eq 'vxlan id 100( |$)'; fi
if test -e /sys/class/net/neon-br0; then
 test -d /sys/class/net/neon-br0/bridge
 for p in /sys/class/net/neon-br0/brif/*; do test ! -e "$p" || test "${p##*/}" = neon-vxlan0; done
fi
iptables -w 5 -t nat -S > /tmp/nat-before
while IFS= read -r line; do
 case "$line" in
 "-N NEON-EXTRANET"|"-A NEON-EXTRANET -s $NEON_ORIGINAL_CIDR -j ACCEPT"|"-A NEON-EXTRANET -d $NEON_ORIGINAL_CIDR -j ACCEPT"|"-A POSTROUTING -d $NEON_ORIGINAL_CIDR -j NEON-EXTRANET") ;;
 *NEON-EXTRANET*) echo 'Unexpected ownership of legacy Neon chain' >&2; exit 1 ;;
 esac
done < /tmp/nat-before
while iptables -w 5 -t nat -C POSTROUTING -d "$NEON_ORIGINAL_CIDR" -j NEON-EXTRANET 2>/dev/null; do iptables -w 5 -t nat -D POSTROUTING -d "$NEON_ORIGINAL_CIDR" -j NEON-EXTRANET; done
vxlan-controller -delete
test ! -e /sys/class/net/neon-vxlan0
test ! -e /sys/class/net/neon-br0
iptables -w 5 -t nat -S > /tmp/nat-after
if grep -q NEON-EXTRANET /tmp/nat-after; then exit 1; fi
printf '{"hostArtifactsAbsent":true}\\n'
'''
   for j,node in enumerate(net['nodes']):self.hostJob('network-'+str(i)+'-'+str(j),node,net['image'],script,[{'name':'xtables','hostPath':{'path':'/run/xtables.lock','type':'FileOrCreate'}}],[{'name':'xtables','mountPath':'/run/xtables.lock'}],True,[{'name':'NEON_ORIGINAL_CIDR','value':net['cidr']}])
  values=json.loads((self.state/'helm-values.private.json').read_text());agent=values['autoscaler']['dsga']['agent'];sockets=[agent[k] for k in ('resourceReadSocket','controlSocket') if agent.get(k,{}).get('enabled')];lines=['set -eu']
  for s in sockets:
   path=s['hostDirectory'];name=s['name']
   if not re.fullmatch('/run/[a-zA-Z0-9_.-]+',path) or not re.fullmatch('[a-zA-Z0-9_.-]+',name):raise RuntimeError('Only declared direct /run private socket paths are supported')
   p='/host-run/'+path.removeprefix('/run/');lines.append('p='+p+'; if test -e "$p" || test -L "$p"; then test ! -L "$p"; test -d "$p"; test "$(stat -c %u:%a "$p")" = 0:700; for f in "$p"/* "$p"/.[!.]* "$p"/..?*; do if test -e "$f" || test -L "$f"; then test "$f" = "$p/'+name+'"; fi; done; host-decommission-check socket-closed "$p/'+name+'"; if test -S "$p/'+name+'"; then rm -- "$p/'+name+'"; fi; rmdir -- "$p"; fi')
  lines.append('printf \'{"hostArtifactsAbsent":true}\\n\'')
  for i,b in enumerate(self.report['bindings']):self.hostJob('sockets-'+str(i),{'name':b['node_name'],'uid':b['node_uid']},self.config['toolsImage'],'\n'.join(lines),[{'name':'host-run','hostPath':{'path':'/run','type':'Directory'}}],[{'name':'host-run','mountPath':'/host-run'}])
  # 原域已正式结束，只清本次写入的退出标记；不触碰共享平台标签。
  for b in self.report['bindings']:
   path='/api/v1/nodes/'+b['node_name'];code,n=self.api('GET',path);m=n['metadata'];expected=self.report['nodes'][b['node_name']]['marker']
   if code!=200 or m['uid']!=b['node_uid'] or m.get('annotations',{}).get(EXIT_MARKER)!=expected:raise RuntimeError('Original domain end marker changed')
   patch=[{'op':'test','path':'/metadata/uid','value':m['uid']},{'op':'test','path':'/metadata/resourceVersion','value':m['resourceVersion']},{'op':'test','path':'/metadata/annotations/'+escaped(EXIT_MARKER),'value':expected},{'op':'remove','path':'/metadata/annotations/'+escaped(EXIT_MARKER)}]
   # 旧发行合同的派生标签只在原快照和原完整池可共同证明时清除，新安装不再生成它。
   legacy='neon.tech/pg17-memory-pool';before=next(n for n in json.loads((self.state/'nodes-before.private.json').read_text())['items'] if n['metadata']['uid']==m['uid']);value=before['metadata'].get('labels',{}).get(legacy)
   if value is not None:
    if value!='-'.join(sorted(x['node_name'] for x in self.report['bindings'])) or m.get('labels',{}).get(legacy)!=value:raise RuntimeError('Legacy derived pool label ownership changed or is unknown')
    patch.extend([{'op':'test','path':'/metadata/labels/'+escaped(legacy),'value':value},{'op':'remove','path':'/metadata/labels/'+escaped(legacy)}])
   self.private('node-marker-cleanup/'+b['node_name']+'.json',patch);code,result=self.api('PATCH',path,patch,'application/json-patch+json')
   if code!=200:raise RuntimeError('Original marker cleanup unconfirmed')
  ref=self.report.get('hostCleanupNamespace')
  if ref:self.deleteOriginal('/api/v1/namespaces/'+ref['name'],ref['uid'])
 def uninstall(self):
  # 逆依赖顺序；AS已在正式停域阶段退出，其他release继续使用原生Helm删除。
  for id in ('control','runtime-access','gateway','pageserver','core','adapter','metadata','neonvm'):
   e=self.entries[id];self.command(self.helm,'uninstall',e['release'],'-n',e['namespace'],'--wait','--timeout','5m',timeout=330)
  for ns,uid in self.report['namespaces'].items():self.deleteOriginal('/api/v1/namespaces/'+ns,uid)
  for crd in json.loads((self.state/'crds-before.private.json').read_text()):self.deleteOriginal('/apis/apiextensions.k8s.io/v1/customresourcedefinitions/'+crd['metadata']['name'],crd['metadata']['uid'])
  self.report['status']='kubernetes-uninstalled-data-pending';self.save()
 def eraseData(self):
  if not self.args.erase_data:raise RuntimeError('Physical data erasure requires the explicit --erase-data action input')
  if self.report.get('status')!='kubernetes-uninstalled-data-pending':raise RuntimeError('Uninstall original workloads before erasing their data')
  values=json.loads((self.state/'helm-values.private.json').read_text())
  if not values['core']['minio']['enabled']:raise RuntimeError('External S3 requires its declared provider cleanup hook; this profile erases only its dedicated built-in MinIO volumes')
  deadline=time.monotonic()+240
  while time.monotonic()<deadline:
   statuses=[self.api('GET','/api/v1/namespaces/'+ns)[0] for ns in self.report['namespaces']]
   if all(s==404 for s in statuses):break
   time.sleep(3)
  else:raise RuntimeError('Original dedicated namespaces have not finished normal deletion')
  image=values['core']['global']['initImage'];registry=self.config['registry']
  if not re.fullmatch(re.escape(registry)+r'/[a-zA-Z0-9/_-]+@sha256:[a-f0-9]{64}',image):raise RuntimeError('A pinned site Harbor cleanup image is required')
  repo,pin=image.split('/',1)[1].split('@');base='http://'+registry;opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));query=urllib.parse.urlencode({'service':'harbor-registry','scope':'repository:'+repo+':pull'})
  with opener.open(base+'/service/token?'+query,timeout=20) as response:issued=json.load(response)
  with opener.open(urllib.request.Request(base+'/v2/'+repo+'/manifests/'+pin,method='HEAD',headers={'Authorization':'Bearer '+(issued.get('token') or issued['access_token']),'Accept':'application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json'}),timeout=20) as response:
   if response.status!=200:raise RuntimeError('Cleanup image is absent from Harbor')
  namespace='neon-clean-'+self.report['nonce'][:12];obj={'apiVersion':'v1','kind':'Namespace','metadata':{'name':namespace,'labels':{'pod-security.kubernetes.io/enforce':'privileged','neon.tech/cleanup-intent':self.report['nonce']}}};self.private('erase-namespace-intent.json',obj);code,created=self.api('POST','/api/v1/namespaces',obj)
  if code!=201:raise RuntimeError('Original cleanup namespace creation not confirmed')
  self.report['cleanupNamespace']={'name':namespace,'uid':created['metadata']['uid']};self.report['erasedVolumes']=[];self.save()
  volumes=json.loads((self.state/'volume-plan.private.json').read_text());pods=self.kube('get','pods','-A')['items']
  for i,item in enumerate(volumes):
   pv=item['pv'];pvc=item['pvc'];node=self.kube('get','node',item['node'])
   if node['metadata']['uid']!=item['nodeUID']:raise RuntimeError('Original local PV node was replaced')
   if any(p['metadata']['namespace']==pvc['metadata']['namespace'] and any(v.get('persistentVolumeClaim',{}).get('claimName')==pvc['metadata']['name'] for v in p['spec'].get('volumes',[])) for p in pods):raise RuntimeError('Original volume remains referenced by a Pod')
   name='erase-'+str(i).zfill(3);child=item['child']
   if not re.fullmatch('[a-z0-9_.-]+',child) or '/' in child or item['root'] not in self.config['storageRoots']:raise RuntimeError('Physical target escaped the declared volume plan')
   script='''set -eu
test -d /host-data
p="/host-data/$NEON_ORIGINAL_VOLUME_CHILD"
test ! -L "$p"
if test -e "$p"; then
 test -d "$p"
 test "$(readlink -f "$p")" = "$p"
 rm -rf -- "$p"
fi
test ! -e "$p"
printf '{"originalVolumeDataAbsent":true}\\n'
'''
   job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':namespace,'labels':{'neon.tech/cleanup-intent':self.report['nonce']}},'spec':{'backoffLimit':0,'activeDeadlineSeconds':240,'template':{'metadata':{'labels':{'neon.tech/cleanup-intent':self.report['nonce']}},'spec':{'nodeName':item['node'],'restartPolicy':'Never','automountServiceAccountToken':False,'containers':[{'name':'erase','image':image,'command':['sh','-ec',script],'env':[{'name':'NEON_ORIGINAL_VOLUME_CHILD','value':child}],'resources':{'requests':{'cpu':'10m','memory':'16Mi'},'limits':{'cpu':'200m','memory':'64Mi'}},'securityContext':{'runAsUser':0,'runAsGroup':0,'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL'],'add':['DAC_OVERRIDE']},'seccompProfile':{'type':'RuntimeDefault'}},'volumeMounts':[{'name':'original-storage-root','mountPath':'/host-data'}]}],'volumes':[{'name':'original-storage-root','hostPath':{'path':item['root'],'type':'Directory'}}]}}}}
   self.private('erase-jobs/'+name+'.json',job);code,created=self.api('POST','/apis/batch/v1/namespaces/'+namespace+'/jobs',job)
   if code!=201:raise RuntimeError('Original physical cleanup Job outcome unknown; inspect it, never submit a new deletion')
   jobUID=created['metadata']['uid'];self.report.setdefault('cleanupJobs',[]).append({'name':name,'uid':jobUID,'pvUID':pv['metadata']['uid']});self.save();self.command('kubectl','-n',namespace,'wait','--for=condition=complete','job/'+name,'--timeout=260s',timeout=280);log=self.command('kubectl','-n',namespace,'logs','job/'+name,'-c','erase');(self.state/('erase-jobs/'+name+'.log')).write_bytes(log)
   if json.loads(log).get('originalVolumeDataAbsent') is not True:raise RuntimeError('Original volume erasure not confirmed')
   self.deleteOriginal('/api/v1/persistentvolumes/'+pv['metadata']['name'],pv['metadata']['uid']);self.report['erasedVolumes'].append({'pv':pv['metadata']['name'],'pvUID':pv['metadata']['uid'],'nodeUID':item['nodeUID'],'path':item['root']+'/'+child,'jobUID':jobUID});self.save()
  self.deleteOriginal('/api/v1/namespaces/'+namespace,self.report['cleanupNamespace']['uid']);self.report.update(status='data-erased-final-verification-pending',dataErased=True);self.save()
 def verifyEmpty(self):
  if not self.report.get('dataErased') or len(self.report.get('erasedVolumes',[]))!=self.report['volumeCount']:raise RuntimeError('Original physical volume cleanup is incomplete')
  releases=json.loads(self.command(self.helm,'list','-A','--all','-o','json'))
  if any(r['name']==e['release'] and r['namespace']==e['namespace'] for r in releases for e in self.entries.values()):raise RuntimeError('Selected Helm release remains')
  originalNamespaces=list(self.report['namespaces'])+[v['name'] for k,v in self.report.items() if k in ('cleanupNamespace','hostCleanupNamespace')];deadline=time.monotonic()+180
  while True:
   remaining=[ns for ns in originalNamespaces if self.api('GET','/api/v1/namespaces/'+ns)[0]!=404]
   if not remaining:break
   if time.monotonic()>deadline:raise RuntimeError('Original dedicated or cleanup namespace remains')
   time.sleep(2)
  for n in self.kube('get','nodes')['items']:
   m=n['metadata']
   if any(k in m.get('annotations',{}) for k in (LEDGER,ORIGIN,EXIT_MARKER)) or NODE_GUARD in m.get('finalizers',[]) or 'neon.tech/pg17-memory-pool' in m.get('labels',{}):raise RuntimeError('Original Host domain residue remains')
   if not any(c['type']=='Ready' and c['status']=='True' for c in n['status']['conditions']):raise RuntimeError('Shared cluster Node is not Ready')
  for p in self.kube('get','pods','-A')['items']:
   if POD_GUARD in p['metadata'].get('finalizers',[]) or any(k.startswith('internal.autoscaling.neon.tech/dsga-host-') for k in p['metadata'].get('annotations',{})):raise RuntimeError('Original ordinary Pod protection residue remains')
  if any(p['spec'].get('claimRef',{}).get('namespace') in self.exclusive for p in self.kube('get','pv')['items']):raise RuntimeError('Original dedicated PV remains')
  for c in json.loads((self.state/'crds-before.private.json').read_text()):
   if self.api('GET','/apis/apiextensions.k8s.io/v1/customresourcedefinitions/'+c['metadata']['name'])[0]!=404:raise RuntimeError('Exclusive Neon CRD remains')
  for obj in json.loads((self.state/'shared-platform-before.json').read_text()):self.command('kubectl','-n',obj['namespace'],'rollout','status',obj['kind']+'/'+obj['name'],'--timeout=60s',timeout=80)
  self.verifyImage(self.config['toolsImage']);self.report.update(status='clean-and-verified',sharedPlatformPreserved=True,harborAvailable=True);self.save();print(json.dumps({'status':self.report['status'],'erasedVolumes':len(self.report['erasedVolumes']),'sharedPlatformPreserved':True}))

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['plan','stop-host-writers','end-host-domains','handoff-ordinary','cleanup-host-artifacts','uninstall','erase-data','verify-empty','inspect']);p.add_argument('--site',required=True);p.add_argument('--state',required=True);p.add_argument('--confirm-site',required=True);p.add_argument('--host-check',default='host-decommission-check');p.add_argument('--erase-data',action='store_true');p.add_argument('--resume-phase',choices=['end-native-host-domains','verify-clean-empty-state']);args=p.parse_args();cleanup=Cleanup(args)
 try:
  if args.action=='inspect':print(json.dumps(cleanup.report));return
  if args.action=='plan':cleanup.phase('inventory-and-original-scope',cleanup.plan);return
  if cleanup.report.get('status')=='new':raise RuntimeError('Create the complete original cleanup plan first')
  cleanup.startProxy();steps={'stop-host-writers':('stop-capacity-writers',cleanup.stopWriters),'end-host-domains':('end-native-host-domains',cleanup.endDomains),'handoff-ordinary':('return-ordinary-pods-to-kubernetes',cleanup.handoffOrdinary),'cleanup-host-artifacts':('clean-original-host-artifacts',cleanup.cleanupHosts),'uninstall':('uninstall-original-releases',cleanup.uninstall),'erase-data':('erase-original-volume-data',cleanup.eraseData),'verify-empty':('verify-clean-empty-state',cleanup.verifyEmpty)};name,action=steps[args.action];required={'stop-host-writers':'inventory-and-original-scope','end-host-domains':'stop-capacity-writers','handoff-ordinary':'end-native-host-domains','cleanup-host-artifacts':'return-ordinary-pods-to-kubernetes','uninstall':'clean-original-host-artifacts','erase-data':'uninstall-original-releases','verify-empty':'erase-original-volume-data'}[args.action]
  if cleanup.report['steps'].get(required,{}).get('status')!='completed':raise RuntimeError('Complete the original prerequisite phase '+required)
  cleanup.phase(name,action)
 finally:cleanup.close()
if __name__=='__main__':main()
