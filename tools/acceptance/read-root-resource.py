import datetime,http.client,json,os,pathlib,socket,stat,sys,urllib.parse
path,vmuid=sys.argv[1:3]
if not pathlib.Path(path).is_absolute() or os.path.realpath(path)!=path:raise RuntimeError('Canonical original socket required')
before=os.stat(path)
if not stat.S_ISSOCK(before.st_mode) or before.st_uid!=0 or before.st_mode&0o077:raise RuntimeError('Original private root socket required')
class UnixConnection(http.client.HTTPConnection):
 def connect(self):
  self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(self.timeout);self.sock.connect(path)
def unique(pairs):
 result={}
 for key,value in pairs:
  if key in result:raise ValueError('Duplicate response field')
  result[key]=value
 return result
def request(method,url,body=None):
 connection=UnixConnection('dsga-agent',timeout=15)
 try:
  connection.request(method,url,body=None if body is None else json.dumps(body).encode(),headers={} if body is None else {'Content-Type':'application/json'})
  response=connection.getresponse();raw=response.read((2<<20)+1)
  if response.status!=200 or response.getheader('Cache-Control')!='no-store' or len(raw)>2<<20:raise RuntimeError('Original read unconfirmed')
  return json.loads(raw,object_pairs_hook=unique)
 finally:connection.close()
owner=request('GET','/dsga/v1/owner?vm_uid='+urllib.parse.quote(vmuid,safe=''))
if owner['protocol_version']!=1 or owner['instance']['vm_uid']!=vmuid or int(owner['owner_epoch'])<1:raise RuntimeError('Original Owner changed')
# resource_state是正式SDK的只读动作；不发送begin、resize、repair或任何重放选择。
result=request('POST','/dsga/v1/command',{'protocol_version':1,'instance':owner['instance'],'expected_owner_epoch':owner['owner_epoch'],'action':'resource_state'})
if result['protocol_version']!=1 or result['instance']!=owner['instance'] or result['owner_epoch']!=owner['owner_epoch']:raise RuntimeError('Original Owner changed during read')
view=result['resource_state'];after=os.stat(path)
if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino) or view['identity']['vm_uid']!=vmuid:raise RuntimeError('Original socket or Guest changed')
print(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'instance':owner['instance'],'ownerEpoch':owner['owner_epoch'],'onlineShrinkProtocol':view.get('online_shrink_protocol_version'),'normalQuotaProtocol':view.get('normal_quota_protocol_version'),'actual':{k:v for k,v in view['actual'].items() if k in ('memory_max_bytes','memory_current_bytes','guest_mem_total_bytes','swap_max_bytes','swap_current_bytes','cgroup_populated')},'heldLimits':None if view.get('held') is None else view['held'].get('limits'),'bootstrapLimits':view['bootstrap'].get('limits')}))
