import copy,datetime,json,time,unittest
from standard_partial import PartialInstallation,unused_node,observer_handoff,LEDGER,ORIGIN,GUARD,EXIT,OBSERVER
class NeverInitializedHost(unittest.TestCase):
 def fixture(self):return {'metadata':{'name':'worker','uid':'original','resourceVersion':'1','annotations':{}}},{'node_name':'worker','node_uid':'original'}
 def test_empty_original_can_exit_without_creating_ledger(self):
  node,binding=self.fixture();before=copy.deepcopy(node);unused_node(node,binding);self.assertEqual(before,node)
 def test_changed_uid_and_name_are_rejected(self):
  for key in ('uid','name'):
   node,binding=self.fixture();node['metadata'][key]='replacement'
   with self.subTest(key=key),self.assertRaises(RuntimeError):unused_node(node,binding)
 def test_partial_or_protected_state_is_never_reset(self):
  for key in (LEDGER,ORIGIN,EXIT):
   for value in ('','{broken','original'):
    node,binding=self.fixture();node['metadata']['annotations'][key]=value;before=copy.deepcopy(node)
    with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):unused_node(node,binding)
    self.assertEqual(before,node)
  node,binding=self.fixture();node['metadata']['finalizers']=[GUARD]
  with self.assertRaises(RuntimeError):unused_node(node,binding)
 def test_deleting_original_is_not_accepted(self):
  node,binding=self.fixture();node['metadata']['deletionTimestamp']='2026-11-25T00:00:00Z'
  with self.assertRaises(RuntimeError):unused_node(node,binding)
 def test_observer_handoff_requires_original_uid_and_nonce(self):
  m={'uid':'writer','annotations':{OBSERVER:'nonce'},'finalizers':[OBSERVER,'example.test/keep']};self.assertEqual(observer_handoff(m,['writer'],'nonce'),[OBSERVER])
  for writers,nonce in ((['replacement'],'nonce'),(['writer'],'other')):
   with self.assertRaises(RuntimeError):observer_handoff(m,writers,nonce)
  self.assertEqual(m['finalizers'],[OBSERVER,'example.test/keep'])
 def test_incomplete_observer_metadata_is_not_accepted(self):
  for m in ({'uid':'writer','annotations':{OBSERVER:'nonce'}},{'uid':'writer','finalizers':[OBSERVER]}):
   with self.assertRaises(RuntimeError):observer_handoff(m,['writer'],'nonce')
class ExitFixture:
 def __init__(self):
  self.report={'nonce':'original-nonce','neverInitializedHosts':['worker'],'nodes':{},'writerUIDs':['writer']};self.writes=[];self.intents=[];self.patch_code=200
  self.lease={'metadata':{'uid':'lease-original','annotations':{'internal.autoscaling.neon.tech/dsga-host-lease-v1':'1:original:worker'},'ownerReferences':[{'uid':'original','kind':'Node','controller':True}]},'spec':{'renewTime':datetime.datetime.fromtimestamp(time.time()-100,datetime.timezone.utc).isoformat(),'leaseDurationSeconds':1}}
  self.pods={'items':[{'metadata':{'uid':'writer','deletionTimestamp':'2026-11-25T00:00:00Z'},'spec':{'containers':[{'name':'writer'}]},'status':{'containerStatuses':[{'state':{'terminated':{'exitCode':0}}}]}}]};self.vms={'items':[]}
 def kube(self,*args):
  if 'lease' in args:return self.lease
  if 'virtualmachines.vm.neon.tech' in args:return self.vms
  if 'pods' in args:return self.pods
  raise AssertionError(args)
 def save(self):pass
 def private(self,name,value):self.intents.append((name,copy.deepcopy(value)))
 def api(self,method,path,body,content):self.writes.append(copy.deepcopy(body));return self.patch_code,{}

class PartialExitObservation(unittest.TestCase):
 def fixture(self):
  c=ExitFixture();p=PartialInstallation.__new__(PartialInstallation);p.c=c;node={'metadata':{'name':'worker','uid':'original','resourceVersion':'37','annotations':{'example.test/keep':'unchanged'},'finalizers':['example.test/keep']}};binding={'node_name':'worker','node_uid':'original','namespace':'product','lease_name':'lease-worker','lease_uid':'lease-original'};return p,c,node,binding
 def test_exit_marker_is_only_mutation_and_preserves_foreign_metadata(self):
  p,c,n,b=self.fixture();self.assertTrue(p.end_unused(b,'/nodes/worker',n));self.assertEqual(c.report['nodes']['worker']['mode'],'never-initialized');self.assertEqual(c.report['nodes']['worker']['status'],'domain-ended');self.assertEqual(len(c.writes),1)
  ops=c.writes[0];self.assertEqual([v['op'] for v in ops],['test','test','test','add']);self.assertEqual(ops[0]['value'],'original');self.assertEqual(ops[1]['value'],'37');self.assertEqual(ops[-1]['value']['example.test/keep'],'unchanged');self.assertNotIn(LEDGER,ops[-1]['value']);self.assertNotIn(ORIGIN,ops[-1]['value']);self.assertEqual(n['metadata']['finalizers'],['example.test/keep'])
 def test_unknown_reply_retains_original_intent_and_prevents_replay(self):
  p,c,n,b=self.fixture();c.patch_code=500
  with self.assertRaises(RuntimeError):p.end_unused(b,'/nodes/worker',n)
  self.assertEqual(c.report['nodes']['worker']['status'],'submitted');self.assertEqual(len(c.intents),1)
  with self.assertRaises(RuntimeError):p.end_unused(b,'/nodes/worker',n)
  self.assertEqual(len(c.writes),1)
 def test_replacement_lease_and_live_lease_block_without_write(self):
  for case in ('uid','owner','live'):
   p,c,n,b=self.fixture()
   if case=='uid':c.lease['metadata']['uid']='replacement'
   if case=='owner':c.lease['metadata']['ownerReferences'][0]['uid']='replacement'
   if case=='live':c.lease['spec']['leaseDurationSeconds']=10000
   with self.subTest(case=case),self.assertRaises(RuntimeError):p.end_unused(b,'/nodes/worker',n)
   self.assertEqual(c.writes,[])
 def test_missing_or_running_writer_never_counts_as_exit(self):
  for case in ('missing','running','unknown-container','running-init'):
   p,c,n,b=self.fixture()
   if case=='missing':c.pods['items']=[]
   if case=='running':c.pods['items'][0]['status']['containerStatuses'][0]['state']={'running':{}}
   if case=='unknown-container':c.pods['items'][0]['status']['containerStatuses']=[]
   if case=='running-init':c.pods['items'][0]['status']['initContainerStatuses']=[{'state':{'running':{}}}]
   with self.subTest(case=case),self.assertRaises(RuntimeError):p.end_unused(b,'/nodes/worker',n)
   self.assertEqual(c.writes,[])
 def test_vm_or_runner_and_partial_inventory_block_without_write(self):
  for case in ('vm','runner','partial-pods','partial-vms'):
   p,c,n,b=self.fixture()
   if case=='vm':c.vms['items']=[{'metadata':{'uid':'vm'}}]
   if case=='runner':c.pods['items'][0]['metadata']['ownerReferences']=[{'kind':'VirtualMachine'}]
   if case=='partial-pods':c.pods['metadata']={'continue':'next'}
   if case=='partial-vms':c.vms['metadata']={'continue':'next'}
   with self.subTest(case=case),self.assertRaises(RuntimeError):p.end_unused(b,'/nodes/worker',n)
   self.assertEqual(c.writes,[])
if __name__=='__main__':unittest.main()
