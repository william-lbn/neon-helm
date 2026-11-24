import base64,hashlib,http.cookiejar,json,os,pathlib,re,secrets,subprocess,sys,time,urllib.error,urllib.parse,urllib.request,zlib
os.umask(0o077)
pg,caseID,action=sys.argv[1:4]
if pg not in ('17','18') or not re.fullmatch('[0-9]{3}',caseID) or action not in ('inspect','suspend','retry-suspend','status-suspend','observe-suspend','resume','verify','retire'):raise RuntimeError('Invalid lifecycle scope')
root=pathlib.Path(os.environ['NEON_SITE_ROOT']);case=root/('business-pg'+pg+'-'+caseID);out=case/'lifecycle-001'
business=json.loads((case/'receipt.json').read_text());proof=json.loads((case/'sql-001/receipt.json').read_text());activeFile=case/'active-compute.json';active=json.loads(activeFile.read_text()) if activeFile.exists() else {'endpointID':proof['endpointID']}
entries={e['id']:e for e in json.loads((root/'site.json').read_text())['releases']};entry=entries['control'];ns=entry['namespace'];project=business['projectID'];endpoint=active['endpointID'];endpointPath='/api/v1/projects/'+project+'/endpoints/'+endpoint
def run(*args):return subprocess.check_output(args,text=True,timeout=40)
def kube(*args):return json.loads(run('kubectl',*args,'-o','json'))
values=json.loads(run('helm','get','values',entry['release'],'-n',ns,'--all','-o','json'));credential=kube('-n',ns,'get','secret',values['api']['existingSecret']);admin=base64.b64decode(credential['data']['admin-password']).decode().strip();service=kube('-n',ns,'get','service',entry['release']+'-api');base='http://'+service['spec']['clusterIP']+':'+str(service['spec']['ports'][0]['port']);jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar));customer=json.loads((case/'creation-intent.private.json').read_text())['request']['password']
def request(path,body=None,method=None,extra=None):
 headers={'Content-Type':'application/json'};headers.update(extra or {})
 if body is not None:
  csrf=next((c.value for c in jar if c.name=='neon_v2_csrf'),None)
  if csrf:headers['X-CSRF-Token']=csrf
 try:
  with client.open(urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers,method=method),timeout=45) as response:return response.status,dict(response.headers),json.load(response)
 except urllib.error.HTTPError as error:
  try:body=json.loads(error.read(8192))
  except ValueError:body={'code':'non_json'}
  return error.code,dict(error.headers),body
code,_,body=request('/auth/login',{'username':'admin','password':admin})
if code!=200:raise RuntimeError('Public login failed')
code,_,current=request(endpointPath)
if code!=200:raise RuntimeError('Active endpoint unavailable')
if action=='inspect':
 print(json.dumps({'endpointID':endpoint,'state':current['state'],'version':current['version'],'suspensionEnabled':values['dsga'].get('suspensionEnabled',False),'autoSuspensionEnabled':values['dsga'].get('autoSuspensionEnabled',False),'pgTLSMode':values['api']['pgTLSMode']}));raise SystemExit(0)
if not values['dsga'].get('suspensionEnabled'):raise RuntimeError('Enable the standard Helm DSGA suspension driver before lifecycle acceptance')
out.mkdir(mode=0o700,exist_ok=True);receipt=out/'receipt.json';scopeFile=out/'scope.private.json'
if scopeFile.exists():scope=json.loads(scopeFile.read_text());report=json.loads(receipt.read_text())
else:
 vms=kube('-n',ns,'get','virtualmachines.vm.neon.tech','-l','neon-control/endpoint-id='+endpoint)['items']
 if len(vms)!=1:raise RuntimeError('Unique current VM required')
 vm=vms[0];memoryProofs=[json.loads(f.read_text()) for f in case.glob('automatic-memory-[0-9][0-9][0-9]/receipt.json')]
 if not any(m.get('status')=='completed' and m.get('automaticVmMemory')=='PASS' and m.get('vmUID')==vm['metadata']['uid'] for m in memoryProofs):raise RuntimeError('Actual native round trip on this exact VM must pass before lifecycle')
 wrapped=json.loads(vm['metadata']['annotations']['internal.autoscaling.neon.tech/dsga-journal-v1']);raw=zlib.decompressobj().decompress(base64.b64decode(wrapped['data']),2<<20)
 if hashlib.sha256(raw).hexdigest()!=wrapped['sha256']:raise RuntimeError('Original WAL checksum differs')
 journal=json.loads(raw)
 if journal.get('active') is not None:raise RuntimeError('Original resize must settle first')
 scope={'projectID':project,'endpointID':endpoint,'vmUID':vm['metadata']['uid'],'vmName':vm['metadata']['name'],'podName':vm['status']['podName'],'node':vm['status']['node'],'branchID':current['branch_id']};scopeFile.write_text(json.dumps(scope,indent=2)+'\n');(out/'vm-before.private.json').write_text(json.dumps(vm,indent=2)+'\n');(out/'journal-before.private.json').write_text(json.dumps(journal,indent=2)+'\n');report={'status':'inspected','projectID':project,'endpointID':endpoint,'oldVMUID':scope['vmUID'],'businessE2E':'NOT_COMPLETE'}
def save():receipt.write_text(json.dumps(report,indent=2)+'\n')
save()
if action in ('suspend','retry-suspend','resume','retire'):
 refs=set(json.loads((case/'harbor-images.json').read_text())['available']);refs.add(values['api']['image']['reference'])
 auto=entries['autoscaler'];autoValues=json.loads(run('helm','get','values',auto['release'],'-n',auto['namespace'],'--all','-o','json'));refs.update(autoValues['images'].values())
 for ref in sorted(refs):
  registry,part=ref.split('/',1);repo,digest=part.split('@');registryURL='http://'+registry;opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));query=urllib.parse.urlencode({'service':'harbor-registry','scope':'repository:'+repo+':pull'})
  with opener.open(registryURL+'/service/token?'+query,timeout=20) as response:issued=json.load(response)
  with opener.open(urllib.request.Request(registryURL+'/v2/'+repo+'/manifests/'+digest,method='HEAD',headers={'Authorization':'Bearer '+(issued.get('token') or issued['access_token']),'Accept':'application/vnd.oci.image.manifest.v1+json,application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json'}),timeout=20) as response:
   if response.status!=200:raise RuntimeError('Required Harbor image unavailable')
 report[action+'HarborImagesAvailable']=len(refs);save()
def settlement(uid,podName,nodeName,label):
 node=kube('get','node',nodeName);model=json.loads(node['metadata']['annotations']['internal.autoscaling.neon.tech/dsga-host-ledger-v1']);vms=kube('-n',ns,'get','virtualmachines.vm.neon.tech')['items'];pods=kube('-n',ns,'get','pods')['items'];held=[h for h in model['holds'] if h['plan']['request']['key']['instance']['vm_uid']==uid];placements=[p for p in model.get('placements',[]) if p.get('vm_uid')==uid];result={'vmGone':not any(v['metadata']['uid']==uid for v in vms),'runnerGone':not any(p['metadata']['name']==podName for p in pods),'remainingHolds':len(held),'remainingPlacements':len(placements),'vmUID':uid,'node':nodeName};result['hostSettled']=result['vmGone'] and result['runnerGone'] and not held and not placements;(out/(label+'-settlement.json')).write_text(json.dumps(result,indent=2)+'\n');(out/(label+'-node.private.json')).write_text(json.dumps(node,indent=2)+'\n')
 if not result['hostSettled']:raise RuntimeError('Original Host capacity has not settled')
 return result
def submit(stage,suffix,payload,method='POST'):
 stageDir=out/stage
 if stageDir.exists():raise SystemExit('Original '+stage+' intent exists; inspect its Operation instead of repeating')
 stageDir.mkdir(mode=0o700);extra={'If-Match':'"'+str(current['version'])+'"','Idempotency-Key':'helm-lifecycle-'+stage+'-'+secrets.token_hex(16)};(stageDir/'intent.private.json').write_text(json.dumps({'path':endpointPath+suffix,'body':payload,'headers':extra,'method':method},indent=2)+'\n');report['status']=stage+'-submitted';save();code,headers,body=request(endpointPath+suffix,payload,method,extra);(stageDir/'response.private.json').write_text(json.dumps({'httpStatus':code,'body':body},indent=2)+'\n')
 if code!=202:report.update(status=stage+'-rejected',errorCode=body.get('code'),httpStatus=code);save();print(json.dumps(report));raise SystemExit(1)
 op=body['operation']['id'];location=headers.get('Location') or headers.get('location') or '/api/v1/projects/'+project+'/operations/'+op;report[stage+'Operation']=op;save();print(json.dumps(report),flush=True);deadline=time.monotonic()+900
 while time.monotonic()<deadline:
  code,_,body=request(location);(stageDir/'operation-latest.private.json').write_text(json.dumps({'httpStatus':code,'body':body},indent=2)+'\n');operation=body.get('operation',body);state=operation.get('state')
  if code==200 and state in ('succeeded','failed','cancelled','canceled'):
   report[stage+'Status']=state;report['status']=stage+'-'+state;save();print(json.dumps(report),flush=True)
   if state!='succeeded':raise SystemExit(1)
   return
  time.sleep(5)
 report['status']=stage+'-pending';save();raise SystemExit('Continue observing the original Operation')
def confirmSuspension():
 code,_,body=request('/api/v1/projects/'+project+'/operations/'+report['suspendOperation']);op=body.get('operation',body)
 if code!=200 or op.get('id')!=report['suspendOperation'] or op.get('state')!='succeeded':raise RuntimeError('Original suspension has not succeeded')
 report.update(suspendStatus='succeeded');report['suspensionSettlement']=settlement(scope['vmUID'],scope['podName'],scope['node'],'suspend');code,_,item=request(endpointPath)
 if code!=200 or item['state']!='suspended':raise RuntimeError('Public endpoint did not become suspended')
 report['status']='suspended-and-settled';save();print(json.dumps(report))
if action=='suspend':
 if current['state']!='active':raise RuntimeError('Active endpoint required')
 submit('suspend','/suspend',{});confirmSuspension()
elif action=='retry-suspend':
 operation=report['suspendOperation'];location='/api/v1/projects/'+project+'/operations/'+operation;code,_,body=request(location);op=body.get('operation',body)
 if code!=200 or op.get('id')!=operation or op.get('state')!='failed' or not op.get('retryable'):raise RuntimeError('Only the original retryable failed suspension can be retried')
 retryID=os.environ.get('NEON_LIFECYCLE_RETRY','001')
 if not re.fullmatch('[0-9]{3}',retryID):raise RuntimeError('Explicit bounded retry number required')
 attempt=out/('suspend-retry-'+retryID)
 if attempt.exists():raise SystemExit('Original suspension retry exists; inspect it instead of replaying')
 attempt.mkdir(mode=0o700);(attempt/'intent.json').write_text(json.dumps({'operationID':operation,'vmUID':scope['vmUID'],'action':'retry-original-suspension'},indent=2)+'\n');code,_,body=request(location+'/retry',{});(attempt/'response.private.json').write_text(json.dumps({'httpStatus':code,'body':body},indent=2)+'\n')
 if code!=202:raise RuntimeError('Original suspension retry was rejected')
 report.update(status='suspend-retry-pending',suspendStatus=body.get('operation',body).get('state','retry_wait'));save();deadline=time.monotonic()+900
 while time.monotonic()<deadline:
  code,_,body=request(location);(attempt/'operation-latest.private.json').write_text(json.dumps({'httpStatus':code,'body':body},indent=2)+'\n');op=body.get('operation',body)
  if code==200:report.update(suspendStatus=op.get('state'),lastObservedUnix=time.time());save()
  if code==200 and op.get('state') in ('succeeded','failed','cancelled','canceled'):
   report.update(suspendStatus=op['state'],status='suspend-'+op['state']);save()
   if op['state']!='succeeded':print(json.dumps(report));raise SystemExit(1)
   confirmSuspension();break
  time.sleep(5)
 else:raise SystemExit('Continue observing the original suspension retry')
elif action=='status-suspend':
 code,_,body=request('/api/v1/projects/'+project+'/operations/'+report['suspendOperation']);op=body.get('operation',body)
 if code!=200 or op.get('id')!=report['suspendOperation']:raise RuntimeError('Original suspension state unavailable')
 report.update(suspendStatus=op.get('state'),lastObservedUnix=time.time());save();print(json.dumps({k:op.get(k) for k in ('id','state','retryable','steps')}))
elif action=='observe-suspend':confirmSuspension()
elif action=='resume':
 if report.get('suspendStatus')!='succeeded' or current['state']!='suspended':raise RuntimeError('Original suspension must complete first')
 settlement(scope['vmUID'],scope['podName'],scope['node'],'resume-precondition');submit('resume','/resume',{})
elif action=='verify':
 if report.get('resumeStatus')!='succeeded' or current['state']!='active':raise RuntimeError('Original resume must complete first')
 code,_,body=request(endpointPath+'/query',{'password':customer,'sql':"SELECT current_setting('server_version_num')::integer,count(*)::integer,sum(id)::bigint,md5(string_agg(payload, ',' ORDER BY id)),pg_current_wal_lsn()::text FROM public.helm_acceptance"});(out/'resumed-data.json').write_text(json.dumps({'httpStatus':code,'body':body},indent=2)+'\n')
 if code!=200 or body['rows'][0][1:4]!=[proof['rowCount'],proof['sumID'],proof['dataChecksum']] or int(body['rows'][0][0])//10000!=int(pg):raise RuntimeError('Original data was not verified after resume')
 vms=kube('-n',ns,'get','virtualmachines.vm.neon.tech','-l','neon-control/endpoint-id='+endpoint)['items']
 if len(vms)!=1 or vms[0]['metadata']['uid']==scope['vmUID']:raise RuntimeError('Resume requires a new native incarnation')
 vm=vms[0];report.update(status='completed',suspendResume='PASS',resumedVMUID=vm['metadata']['uid'],resumedVMName=vm['metadata']['name'],resumedNode=vm['status']['node'],rowCount=body['rows'][0][1],dataChecksum=body['rows'][0][3],walLSN=body['rows'][0][4]);(out/'resumed-vm.private.json').write_text(json.dumps(vm,indent=2)+'\n');activeFile.write_text(json.dumps({'projectID':project,'endpointID':endpoint,'vmUID':vm['metadata']['uid'],'origin':'lifecycle-001'},indent=2)+'\n');save();print(json.dumps(report))
elif action=='retire':
 if report.get('suspendResume')!='PASS':raise RuntimeError('Complete resume verification before final retirement')
 vm=json.loads((out/'resumed-vm.private.json').read_text());submit('retire','',{'confirm_selector':current['selector']},'DELETE');report['retirementSettlement']=settlement(vm['metadata']['uid'],vm['status']['podName'],vm['status']['node'],'retire');report.update(status='retired-and-settled',retirement='PASS');save();print(json.dumps(report))
