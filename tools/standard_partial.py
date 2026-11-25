"""未开放控制面的部分安装退出：保留原收据，不初始化或重置账本来凑齐卸载条件。"""
import datetime,hashlib,json,pathlib,time
from standard_contract import OperationContract,private_state,lock_state,safe_path

LEDGER='internal.autoscaling.neon.tech/dsga-host-ledger-v1'
ORIGIN='internal.autoscaling.neon.tech/dsga-host-origin-v1'
GUARD='autoscaling.neon.tech/dsga-host-ledger-protection'
EXIT='internal.autoscaling.neon.tech/dsga-host-decommission-v1'
OBSERVER='neon.tech/cleanup-writer-observation'
POD_GUARD='autoscaling.neon.tech/dsga-host-pod-protection'

def unused_node(node,binding):
 m=node['metadata'];a=m.get('annotations',{})
 if m['name']!=binding['node_name'] or m['uid']!=binding['node_uid'] or m.get('deletionTimestamp'):raise RuntimeError('原未初始化 Node 身份变化')
 if any(k in a for k in (LEDGER,ORIGIN,EXIT)) or GUARD in m.get('finalizers',[]):raise RuntimeError('原 Host 存在账本或残缺保护状态，不能按未初始化退出')

def observer_handoff(metadata,writer_uids,nonce):
 finalizers=metadata.get('finalizers',[]);annotations=metadata.get('annotations',{})
 if OBSERVER not in finalizers and OBSERVER not in annotations:return []
 if metadata['uid'] not in writer_uids or annotations.get(OBSERVER)!=nonce or OBSERVER not in finalizers:raise RuntimeError('退出观察保护不属于本次原写者，禁止清理')
 return [OBSERVER]

def original_namespace_status(name,uid,observed,report):
 # 正常卸载完成后 Namespace 应当消失；必须同时有原 UID 删除回执和当前 404。
 # 不能按同名接管重建的 Namespace，也不能把早于卸载的意外消失视为完成。
 if observed is not None:
  if observed['metadata']['uid']!=uid:raise RuntimeError('独占命名空间已被重建，禁止接续原退出')
  return
 completed=report.get('steps',{}).get('uninstall-original-releases',{}).get('status')=='completed'
 deleted=any(d.get('path')=='/api/v1/namespaces/'+name and d.get('uid')==uid for d in report.get('deleted',[]))
 if not completed or not deleted:raise RuntimeError('命名空间缺失但没有原完成删除证明')

class PartialInstallation:
 def __init__(self,cleanup,state,tools):
  self.lock=None
  try:self._initialize(cleanup,state,tools)
  except BaseException:
   # 前置校验失败时也归还只读文件锁，避免反复诊断时持有失效句柄。
   if self.lock is not None:self.lock.close()
   raise
 def _initialize(self,cleanup,state,tools):
  self.c=cleanup;self.state=private_state(state,True);self.lock=lock_state(self.state,True);self.file=safe_path(self.state/'receipt.json');self.raw=self.file.read_bytes();self.original=json.loads(self.raw);self.tools=safe_path(tools);self.activation=safe_path(self.state/'host-activation-values.private.json');self.activation_raw=self.activation.read_bytes();self.bindings=[n['binding'] for n in json.loads(self.activation_raw)['dsga']['scheduler']['nodes']]
  original=self.original
  if original.get('status')!='incomplete' or original.get('businessE2E')!='NOT_RUN' or any(name.startswith('helm-control') or name=='control-runtime-ready' for name in original['steps']):raise RuntimeError('部分退出仅支持原控制面从未提交、业务从未开始的安装；其他站点必须正常退役')
  if original.get('inputSHA256')!=hashlib.sha256(cleanup.file.read_bytes()).hexdigest():raise RuntimeError('原安装站点输入不匹配')
  # 合同以文件所在目录定位；CLI 接收目录，内部必须使用原合同文件作为锚点。
  self.contract=OperationContract(cleanup.file,cleanup.config,original,tools=self.tools/'standard_contract.py');self.check()
  namespaces={r['name']:r['uid'] for r in original.get('createdResources',[]) if r['kind']=='Namespace'}
  for name in cleanup.exclusive:
   if name not in namespaces:raise RuntimeError('独占命名空间不属于本次原安装，禁止部分退出')
   if cleanup.report.get('steps',{}).get('uninstall-original-releases',{}).get('status')=='completed':
    raw=cleanup.command('kubectl','get','namespace',name,'--ignore-not-found','-o','json');observed=json.loads(raw) if raw.strip() else None
   else:observed=cleanup.kube('get','namespace',name)
   original_namespace_status(name,namespaces[name],observed,cleanup.report)
  if original['steps'].get('helm-autoscaler-host-activation',{}).get('status')!='completed':raise RuntimeError('原 Host 激活 Helm 结果未确认，禁止推断部分退出范围')
  source={'state':str(self.state),'tools':str(self.tools),'receiptSHA256':hashlib.sha256(self.raw).hexdigest(),'activationSHA256':hashlib.sha256(self.activation_raw).hexdigest(),'clusterUID':original['clusterUID'],'controlPlaneNeverSubmitted':True}
  if cleanup.report.get('partialInstallationSource',source)!=source:raise RuntimeError('原部分安装退出来源变化')
  cleanup.report['partialInstallationSource']=source
 def check(self):
  if self.file.read_bytes()!=self.raw or self.activation.read_bytes()!=self.activation_raw:raise RuntimeError('原安装收据或 Host 绑定变化，禁止继续另一个退出操作')
  self.contract.check(self.c.report['clusterUID'])
 def missing_release(self,name):return name=='control'
 def classify(self,nodes,bindings):
  if bindings!=self.bindings:raise RuntimeError('现场 Host 绑定与原冻结安装不一致')
  never=[]
  for b in bindings:
   node=next(n for n in nodes['items'] if n['metadata']['name']==b['node_name']);m=node['metadata'];raw=m.get('annotations',{}).get(LEDGER)
   if m['uid']!=b['node_uid']:raise RuntimeError('原 Host Node UID 变化')
   if not raw:unused_node(node,b);never.append(b['node_name']);continue
   model=json.loads(raw)
   if model['binding']!=b or model['holds'] or any(p.get('managed') or p.get('vm_uid') for p in model['placements']):raise RuntimeError('原 Host 尚有 Compute 持有或绑定变化')
  self.c.report['neverInitializedHosts']=never
 def metadata(self):
  c=self.c;values=json.loads((c.state/'helm-values.private.json').read_text());entry=c.entries['metadata'];name=values['metadata'].get('fullnameOverride','neon-control-v2-db');pods=c.kube('-n',entry['namespace'],'get','pods','-l','app.kubernetes.io/name='+name)['items'];pods=[p for p in pods if p['status']['phase']=='Running' and not p['metadata'].get('deletionTimestamp')]
  if len(pods)!=1:raise RuntimeError('原元数据库 Pod 未确认')
  prefix='export PGPASSWORD="$POSTGRES_PASSWORD"; export PGOPTIONS="-c statement_timeout=30000 -c lock_timeout=3000"; '
  def sql(query):return c.command('kubectl','-n',entry['namespace'],'exec',pods[0]['metadata']['name'],'-c','postgres','--','sh','-ec',prefix+'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "'+query+'"',timeout=60).strip()
  exists=sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='operations'")
  if exists not in (b'0',b'1'):raise RuntimeError('原 Operations 表状态未确认')
  if exists==b'1' and sql('SELECT count(*) FROM operations')!=b'0':raise RuntimeError('已有业务 Operation，禁止部分安装退出')
 def protect_writers(self):
  c=self.c
  for original in json.loads((c.state/'original-writers.private.json').read_text()):
   m=original['metadata'];path='/api/v1/namespaces/'+m['namespace']+'/pods/'+m['name'];code,pod=c.api('GET',path)
   if code!=200 or pod['metadata']['uid']!=m['uid'] or pod['metadata'].get('deletionTimestamp'):raise RuntimeError('原容量写者在退出观察前变化')
   actual=pod['metadata'];finalizers=actual.get('finalizers',[]);annotations=actual.get('annotations',{})
   if POD_GUARD in finalizers:continue
   if OBSERVER in finalizers or OBSERVER in annotations:raise RuntimeError('已有另一退出观察意图，不能收养')
   # 仅保留原 Pod 直至正常终止可被观察，不授予任何容量，也不创建 Node 账本。
   patch=[{'op':'test','path':'/metadata/uid','value':m['uid']},{'op':'test','path':'/metadata/resourceVersion','value':actual['resourceVersion']},{'op':'add','path':'/metadata/finalizers','value':finalizers+[OBSERVER]},{'op':'add','path':'/metadata/annotations','value':dict(annotations,**{OBSERVER:c.report['nonce']})}]
   c.private('writer-observation/'+m['uid']+'.json',{'path':path,'patch':patch});code,result=c.api('PATCH',path,patch,'application/json-patch+json')
   if code!=200 or result['metadata']['uid']!=m['uid'] or OBSERVER not in result['metadata'].get('finalizers',[]):raise RuntimeError('原写者退出观察保护写入未确认；只读查询原意图，不能重放')
 def end_unused(self,binding,path,node):
  c=self.c;name=binding['node_name']
  if name not in c.report['neverInitializedHosts']:return False
  if name in c.report['nodes']:raise RuntimeError('原未初始化 Host 退出意图已存在，禁止重放')
  unused_node(node,binding)
  lease=c.kube('-n',binding['namespace'],'get','lease',binding['lease_name']);lm=lease['metadata'];owners=lm.get('ownerReferences',[])
  if lm['uid']!=binding['lease_uid'] or lm.get('annotations',{}).get('internal.autoscaling.neon.tech/dsga-host-lease-v1')!='1:'+binding['node_uid']+':'+name or len(owners)!=1 or owners[0].get('uid')!=binding['node_uid'] or owners[0].get('kind')!='Node' or owners[0].get('controller') is not True:raise RuntimeError('原未初始化 Host Lease 绑定变化')
  spec=lease['spec'];renew=datetime.datetime.fromisoformat(spec['renewTime'].replace('Z','+00:00')).timestamp()
  if spec['leaseDurationSeconds']<=0 or time.time()<=renew+spec['leaseDurationSeconds']+2:raise RuntimeError('原未初始化 Host Lease 尚未自然到期')
  vms=c.kube('get','virtualmachines.vm.neon.tech','-A')
  if vms.get('metadata',{}).get('continue') or vms['items']:raise RuntimeError('未初始化域退出时 VM 空集未确认')
  pods=c.kube('get','pods','-A');actual={p['metadata']['uid']:p for p in pods['items']}
  if pods.get('metadata',{}).get('continue') or len(actual)!=len(pods['items']) or any(o.get('kind')=='VirtualMachine' for p in pods['items'] for o in p['metadata'].get('ownerReferences',[])):raise RuntimeError('完整原 Pod 清单或 Runner 空集未确认')
  for uid in c.report['writerUIDs']:
   p=actual.get(uid);statuses=p.get('status',{}).get('containerStatuses',[]) if p else []
   if not p or not p['metadata'].get('deletionTimestamp') or len(statuses)!=len(p['spec']['containers']) or any('terminated' not in s.get('state',{}) for s in statuses) or any('running' in s.get('state',{}) for s in p.get('status',{}).get('initContainerStatuses',[])):raise RuntimeError('原写者正常退出未被确认，Pod 消失不能替代退出证明')
  # 调用方已证明全部写者正常终止、原 Lease 自然到期且 VM 集为空。
  # 仅加本次退出标记；不伪造曾存在的账本，也不删除任何 Origin/账本。
  m=node['metadata'];a=m.get('annotations',{});marker=json.dumps({'nonce':c.report['nonce'],'nodeUID':m['uid'],'leaseUID':binding['lease_uid'],'mode':'never-initialized'},separators=(',',':'))
  patch=[{'op':'test','path':'/metadata/uid','value':m['uid']},{'op':'test','path':'/metadata/resourceVersion','value':m['resourceVersion']},{'op':'test','path':'/metadata/annotations','value':a},{'op':'add','path':'/metadata/annotations','value':dict(a,**{EXIT:marker})}]
  c.report['nodes'][name]={'status':'submitted','mode':'never-initialized','marker':marker,'sourceRV':m['resourceVersion']};c.save();c.private('node-intents/'+name+'.json',patch);code,result=c.api('PATCH',path,patch,'application/json-patch+json')
  if code!=200:raise RuntimeError('原未初始化 Host 退出标记 CAS 未确认；保留原意图')
  c.report['nodes'][name]['status']='domain-ended';c.save();return True
