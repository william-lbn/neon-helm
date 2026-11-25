set -eu
export PYTHONPATH="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)${PYTHONPATH:+:$PYTHONPATH}"
export KUBECONFIG=${KUBECONFIG:?Explicit kubeconfig required}
export NEON_E2E_PG=${1:?Major required} NEON_E2E_CASE=${2:?Case required}
python3 -B - <<'PY'
import base64,concurrent.futures,datetime,decimal,hashlib,http.cookiejar,json,math,os,pathlib,re,subprocess,time,urllib.error,urllib.parse,urllib.request,zlib,yaml
from standard_contract import verify_images
os.umask(0o077);pg=int(os.environ['NEON_E2E_PG']);caseID=os.environ['NEON_E2E_CASE'];attempt=os.environ.get('NEON_MEMORY_ATTEMPT','003')
if pg not in (17,18) or not all(re.fullmatch('[0-9]{3}',s) for s in (caseID,attempt)):raise RuntimeError('Invalid acceptance case')
root=pathlib.Path(os.environ['NEON_SITE_ROOT']);case=root/('business-pg'+str(pg)+'-'+caseID);out=case/('automatic-memory-'+attempt)
if out.exists():raise SystemExit('Original load exists; inspect its running state, never replay unknown requests')
business=json.loads((case/'receipt.json').read_text());sqlProof=json.loads((case/'sql-001/receipt.json').read_text())
active=json.loads((case/'active-compute.json').read_text()) if (case/'active-compute.json').exists() else {'endpointID':sqlProof['endpointID']}
sqlProof=dict(sqlProof,endpointID=active['endpointID'])
if business.get('operationStatus')!='succeeded' or sqlProof.get('sql')!='PASS':raise RuntimeError('Public creation and verified SQL must pass first')
entries={e['id']:e for e in json.loads((root/'site.json').read_text())['releases']};entry=entries['control'];ns=entry['namespace']
def run(*args):return subprocess.check_output(args,text=True,timeout=40)
def kube(*args):return json.loads(run('kubectl',*args,'-o','json'))
def quantity(value):
 match=re.fullmatch(r'([0-9.]+)(Ki|Mi|Gi|Ti|K|M|G|T)?',str(value));factors={'Ki':1<<10,'Mi':1<<20,'Gi':1<<30,'Ti':1<<40,'K':10**3,'M':10**6,'G':10**9,'T':10**12,None:1}
 if not match:raise RuntimeError('Unsupported exact memory quantity')
 return int(decimal.Decimal(match[1])*factors[match[2]])
cv=json.loads(run('helm','get','values',entry['release'],'-n',ns,'--all','-o','json'))
if cv['api']['pgTLSMode']!='verify-full':raise RuntimeError('Verified Proxy TLS required')
catalogSecret=kube('-n',ns,'get','secret',cv['dsga']['runtimeCatalogSecret']);catalog=next(json.loads(base64.b64decode(v)) for v in catalogSecret['data'].values() if json.loads(base64.b64decode(v)).get('protocol_version')==3);release=next(r for r in catalog['releases'] if int(r['creation']['postgres_version'])==pg);supply=release['creation']['vm']['generic_guest']['supply'];policy=supply['automatic'];low,high=map(lambda t:int(t['vm_memory_bytes']),(supply['targets'][0],supply['targets'][-1]));normalMax=int(supply['targets'][0]['normal_memory_max_bytes'])
vms=kube('-n',ns,'get','virtualmachines.vm.neon.tech','-l','neon-control/endpoint-id='+active['endpointID'])['items']
if len(vms)!=1:raise RuntimeError('Unique active endpoint VM required')
vm=vms[0];vmName=vm['metadata']['name'];vmUID=vm['metadata']['uid'];podName=vm['status']['podName'];pod=kube('-n',ns,'get','pod',podName);podUID=pod['metadata']['uid'];restart=vm['status'].get('restartCount',0)
if active.get('vmUID',vmUID)!=vmUID:raise RuntimeError('Active replacement identity changed')
if quantity(vm['status']['memorySize'])!=low:raise RuntimeError('Wait for original minimum capacity before starting new load')
birth=next(cm for cm in kube('-n',ns,'get','configmaps')['items'] if cm['metadata']['name'].startswith('dsga-b-') and any(o.get('uid')==vmUID for o in cm['metadata'].get('ownerReferences',[])));binding=json.loads(birth['data']['runner.json']);nativeRef=binding['state_claim']
threshold=(normalMax*int(policy['growThresholdPermille'])+999)//1000;perBytes=min(8<<20,max(1<<20,threshold//20));workers=8;rows=math.ceil(perBytes/1024);workMB=32
if workers*perBytes>normalMax//2:raise RuntimeError('Bounded SQL load would exceed half the original normal budget')
metadata=entries['metadata'];metadataDocs=[d for d in yaml.safe_load_all(run('helm','get','manifest',metadata['release'],'-n',metadata['namespace'])) if isinstance(d,dict)];metadataDeployment=next(d for d in metadataDocs if d.get('kind')=='Deployment');selector=','.join(k+'='+v for k,v in metadataDeployment['spec']['selector']['matchLabels'].items());clientPod=next(p for p in kube('-n',metadata['namespace'],'get','pods','-l',selector)['items'] if p['status']['phase']=='Running');clientContainer=next(c for c in clientPod['spec']['containers'] if c['name']==metadataDeployment['spec']['template']['spec']['containers'][0]['name'])
siteConfig=json.loads(pathlib.Path(json.loads((root/'site.json').read_text())['siteConfig']).read_text())
verify_images(siteConfig,set(json.loads((case/'harbor-images.json').read_text())['available']+[clientContainer['image']]))
loadSQL="SET statement_timeout='100s'; SET max_parallel_workers_per_gather=0; SET jit=off; SET work_mem='"+str(workMB)+"MB'; WITH ordered AS MATERIALIZED (SELECT repeat(md5(g::text),32) AS payload FROM generate_series(1,"+str(rows)+") g ORDER BY payload) SELECT count(*)::integer, pg_sleep(65) FROM ordered"
out.mkdir(mode=0o700);(out/'load-intent.json').write_text(json.dumps({'sql':loadSQL,'workers':workers,'declaredNormalMaxBytes':normalMax,'growThresholdBytes':threshold,'estimatedPayloadPerClientBytes':perBytes,'changesToPolicyOrVM':False},indent=2)+'\n')
report={'status':'starting','postgresVersion':pg,'vmUID':vmUID,'podUID':podUID,'node':vm['status']['node'],'minMemoryBytes':low,'maxMemoryBytes':high,'sqlWorkers':workers,'loadTransport':'standard-psql-proxy-verify-full','clientImage':clientContainer['image'],'policyChanged':False,'vmPatchedByTest':False,'businessE2E':'NOT_COMPLETE','guestPhysicalConfirmation':'PENDING_ROOT_WATCH'}
def save():(out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
save();credentials=kube('-n',ns,'get','secret',cv['api']['existingSecret']);password=base64.b64decode(credentials['data']['admin-password']).decode().strip();service=kube('-n',ns,'get','service',entry['release']+'-api');base='http://'+service['spec']['clusterIP']+':'+str(service['spec']['ports'][0]['port']);jar=http.cookiejar.CookieJar();loginClient=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
with loginClient.open(urllib.request.Request(base+'/auth/login',data=json.dumps({'username':'admin','password':password}).encode(),headers={'Content-Type':'application/json'}),timeout=30) as response:response.read()
headers={'Content-Type':'application/json','Cookie':'; '.join(c.name+'='+c.value for c in jar),'X-CSRF-Token':next(c.value for c in jar if c.name=='neon_v2_csrf')};customerPassword=json.loads((case/'creation-intent.private.json').read_text())['request']['password'];endpoint='/api/v1/projects/'+business['projectID']+'/endpoints/'+sqlProof['endpointID']
def query(suffix,sql,timeout=110):
 client=urllib.request.build_opener(urllib.request.ProxyHandler({}));request=urllib.request.Request(base+endpoint+suffix,data=json.dumps({'password':customerPassword,'sql':sql}).encode(),headers=headers)
 try:
  with client.open(request,timeout=timeout) as response:return response.status,json.load(response)
 except urllib.error.HTTPError as error:
  try:body=json.loads(error.read(8192))
  except ValueError:body={'code':'non_json'}
  return error.code,body
def dataCheck(label):
 for attempt in range(8):
  code,body=query('/query',"SELECT count(*)::integer, sum(id)::bigint, md5(string_agg(payload, ',' ORDER BY id)), pg_current_wal_lsn()::text FROM public.helm_acceptance",45)
  (out/(label+'-attempt'+str(attempt)+'.json')).write_text(json.dumps({'httpStatus':code,'body':body},indent=2)+'\n')
  if code==200:
   row=body['rows'][0]
   if row[:3]!=[sqlProof['rowCount'],sqlProof['sumID'],sqlProof['dataChecksum']]:raise RuntimeError('Committed data changed during automatic resize')
   return {'rowCount':row[0],'sumID':row[1],'dataChecksum':row[2],'walLSN':row[3]}
  if not body.get('retryable'):raise RuntimeError('Data verification read refused; inspect original response')
  time.sleep(2)
 raise RuntimeError('Bounded data verification read did not complete')
report['before']=dataCheck('before');report['status']='load-submitted';save();print(json.dumps(report),flush=True)
identityCode,identityBody=query('/query',"SELECT current_database(),current_user",30)
if identityCode!=200:raise RuntimeError('Current endpoint SQL identity unavailable')
database,role=identityBody['rows'][0];publicCA=kube('-n',ns,'get','secret',cv['api']['pgCASecret'])['data']['ca.crt'];selector='ep-'+sqlProof['endpointID'].removeprefix('ep_')
checkCode,checkBody=query('/query',"SELECT count(*)::integer FROM pg_stat_activity WHERE usename=current_user AND datname=current_database() AND pid<>pg_backend_pid() AND state='active'",30)
(out/'prior-load-activity.json').write_text(json.dumps({'httpStatus':checkCode,'body':checkBody},indent=2)+'\n')
if checkCode!=200 or checkBody['rows'][0][0]!=0:raise RuntimeError('Original SQL load may still be active; do not submit another load')
clientScript='''set -eu
umask 077
read -r public_ca
read -r PGPASSWORD
export PGPASSWORD
printf '%s' "$public_ca" | base64 -d > "$1"
trap 'rm -f -- "$1"' EXIT
export PGHOST="$2" PGPORT="$3" PGUSER="$4" PGDATABASE="$5" PGSSLMODE=verify-full PGSSLROOTCERT="$1" PGCONNECT_TIMEOUT=15 PGOPTIONS="endpoint=$6" PGAPPNAME="$8"
psql -X -w -At --set=ON_ERROR_STOP=1 -c "$7"
'''
def load(index):
 time.sleep(index*5)
 try:
  path='/tmp/neon-memory-pg'+str(pg)+'-'+caseID+'-'+attempt+'-'+str(index)+'.ca.crt';app='neon-memory-e2e-'+str(pg)+'-'+caseID+'-'+str(index)
  result=subprocess.run(['kubectl','-n',metadata['namespace'],'exec','-i',clientPod['metadata']['name'],'-c',clientContainer['name'],'--','sh','-ec',clientScript,'--',path,cv['api']['proxyHost'],str(cv['api']['proxyPort']),role,database,selector,loadSQL,app],input=publicCA+'\n'+customerPassword+'\n',capture_output=True,text=True,timeout=110)
  (out/('client-'+str(index)+'.private.log')).write_text(result.stdout+result.stderr)
  passed=result.returncode==0;saved={'exit':result.returncode,'transport':'standard-psql','queryRows':rows,'completed':passed}
 except Exception as error:saved={'outcome':'unconfirmed','errorType':type(error).__name__};passed=False
 (out/('load-'+str(index)+'.json')).write_text(json.dumps(saved,indent=2)+'\n');return passed
grew=False;loaded=False;last=None;deadline=time.monotonic()+780
with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
 futures=[executor.submit(load,index) for index in range(workers)]
 while time.monotonic()<deadline:
  vm=kube('-n',ns,'get','virtualmachines.vm.neon.tech',vmName);currentPod=kube('-n',ns,'get','pod',podName);native=kube('-n',ns,'get','configmap',nativeRef['name'])
  if vm['metadata']['uid']!=vmUID or currentPod['metadata']['uid']!=podUID or vm['status'].get('restartCount',0)!=restart or native['metadata']['uid']!=nativeRef['uid']:raise RuntimeError('Original Compute/Runner identity changed')
  nativeState=json.loads(native['data']['runner.json']);size=quantity(vm['status']['memorySize']);actual=int(nativeState['actual']['actual_bytes']);requested=int(nativeState['actual']['requested_bytes']);stamp=datetime.datetime.now(datetime.timezone.utc).isoformat();observation={'at':stamp,'vmMemoryBytes':size,'runnerActualBytes':actual,'runnerRequestedBytes':requested,'vmUID':vmUID,'podUID':podUID}
  with (out/'native-observations.jsonl').open('a') as file:file.write(json.dumps(observation)+'\n')
  point=(size,actual,requested)
  if point!=last:print('NATIVE_MEMORY',json.dumps(observation),flush=True);last=point
  if not grew and size==high and actual==high and requested==high:
   grew=True;report.update(status='grown',growthAt=stamp,nativeGrowthConfirmed=True);save();report['afterGrowth']=dataCheck('after-growth');save()
  if not loaded and all(f.done() for f in futures):
   passed=all(f.result() for f in futures);loaded=True;report['sqlLoadPassed']=passed;save()
   if not passed:raise RuntimeError('At least one original SQL load failed; inspect its saved outcome')
  if grew and loaded and size==low and actual==low and requested==low:
   wrapped=json.loads(vm['metadata']['annotations']['internal.autoscaling.neon.tech/dsga-journal-v1']);raw=zlib.decompressobj().decompress(base64.b64decode(wrapped['data']),2<<20)
   if hashlib.sha256(raw).hexdigest()!=wrapped['sha256']:raise RuntimeError('Original WAL checksum changed')
   model=json.loads(raw)
   if model['vm_uid']!=vmUID:raise RuntimeError('Original WAL VM changed')
   if model.get('active') is not None:
    report.update(status='waiting-original-settlement');save();time.sleep(5);continue
   if len(model.get('history',[]))<2:raise RuntimeError('Native round trip lacks both original resize records')
   report.update(status='completed',shrinkAt=stamp,nativeShrinkConfirmed=True,automaticVmMemory='PASS');report['afterShrink']=dataCheck('after-shrink')
   (out/'journal-after.private.json').write_text(json.dumps(model,indent=2)+'\n');report['historyCount']=len(model.get('history',[]));save();print(json.dumps(report),flush=True);break
  time.sleep(5)
 else:
  report.update(status='observation-ended',nativeGrowthConfirmed=grew,reason='Continue observing original WAL; do not replay load');save();print(json.dumps(report),flush=True);raise SystemExit(1)
PY
