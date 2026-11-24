set -eu
export KUBECONFIG=${KUBECONFIG:?Explicit kubeconfig required}
export NEON_E2E_ORG=${1:?Organization ID required}
export NEON_E2E_PG=${2:-17}
export NEON_E2E_CASE=${3:-001}
python3 -B - <<'PY'
import base64,concurrent.futures,http.cookiejar,json,os,pathlib,re,secrets,subprocess,time,urllib.error,urllib.parse,urllib.request
os.umask(0o077);root=pathlib.Path(os.environ['NEON_SITE_ROOT']);pg=int(os.environ['NEON_E2E_PG']);org=os.environ['NEON_E2E_ORG'];case=os.environ['NEON_E2E_CASE']
if not re.fullmatch('[0-9]{3}',case):raise RuntimeError('Invalid E2E case ID')
out=root/('business-pg'+str(pg)+'-'+case)
if out.exists():raise SystemExit('Business request exists; inspect original operation and idempotency key')
if pg not in (17,18) or not re.fullmatch(r'org_[a-z0-9]+',org):raise RuntimeError('Invalid E2E selection')
deployment=json.loads(pathlib.Path(json.loads((root/'site.json').read_text())['deploymentReceipt']).read_text())
if deployment.get('status')!='installed' or any(deployment['steps'].get(k,{}).get('status')!='completed' for k in ('confirm-original-host-cas','gateway-public-trust','control-runtime-ready')):raise RuntimeError('Complete the actual standard installation before acceptance')
entries={e['id']:e for e in json.loads((root/'site.json').read_text())['releases']};e=entries['control'];ns=e['namespace']
def run(*args):return subprocess.check_output(args,text=True,timeout=40)
def kube(*args):return json.loads(run('kubectl',*args,'-o','json'))
def values(id,all=True):
 x=entries[id];return json.loads(run('helm','get','values',x['release'],'-n',x['namespace'],*(['--all'] if all else []),'-o','json'))
current=values('control');auto=values('autoscaler');nodes={n['metadata']['name']:n for n in kube('get','nodes')['items']}
if current['api']['pgTLSMode']!='verify-full':raise RuntimeError('Native management and verified SQL trust must precede acceptance creation')
if not auto['dsga']['enabled'] or not auto['dsga']['scheduler']['enabled']:raise RuntimeError('Host mode must remain enabled')
for name,uid in auto['dsga']['hostIdentities'].items():
 n=nodes[name]
 if n['metadata']['uid']!=uid or not n['metadata'].get('annotations',{}).get('internal.autoscaling.neon.tech/dsga-host-ledger-v1'):raise RuntimeError('Managed Host identity/ledger changed')
catalogSecret=kube('-n',ns,'get','secret',current['dsga']['runtimeCatalogSecret']);catalogs=[]
for data in catalogSecret['data'].values():
 try:catalogs.append(json.loads(base64.b64decode(data)))
 except (ValueError,UnicodeDecodeError):pass
catalog=next(c for c in catalogs if c.get('protocol_version')==3)
refs={current['api']['image']['reference']}
def collect(v):
 if isinstance(v,dict):
  for x in v.values():collect(x)
 elif isinstance(v,list):
  for x in v:collect(x)
 elif isinstance(v,str) and '@sha256:' in v and '/' in v:refs.add(v)
collect(catalog)
def checkImage(image):
 registry,reference=image.split('/',1);repo,digest=reference.split('@');base='http://'+registry
 if not re.fullmatch(r'[a-zA-Z0-9.-]+:[0-9]+',registry):raise RuntimeError('E2E requires the declared internal registry')
 op=urllib.request.build_opener(urllib.request.ProxyHandler({}));query=urllib.parse.urlencode({'service':'harbor-registry','scope':'repository:'+repo+':pull'})
 with op.open(base+'/service/token?'+query,timeout=20) as response:issued=json.load(response)
 headers={'Authorization':'Bearer '+(issued.get('token') or issued['access_token']),'Accept':'application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.index.v1+json'}
 with op.open(urllib.request.Request(base+'/v2/'+repo+'/manifests/'+digest,headers=headers,method='HEAD'),timeout=20) as response:
  if response.status!=200:raise RuntimeError('Catalog image unavailable')
 return image
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:available=list(executor.map(checkImage,sorted(refs)))
out.mkdir(mode=0o700);(out/'harbor-images.json').write_text(json.dumps({'available':available,'missing':[]},indent=2)+'\n')
report={'status':'submitted','postgresVersion':pg,'harborImagesAvailable':len(available),'organization':org,'businessE2E':'NOT_COMPLETE'}
def save(): (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
save()
if not(current['api']['creationEnabled'] and current['dsga']['createEnabled'] and current['dsga']['suspensionEnabled']):
 (out/'control-before.private.json').write_text(json.dumps(values('control',False),indent=2)+'\n')
 (out/'enable-overlay.json').write_text(json.dumps({'api':{'creationEnabled':True},'dsga':{'createEnabled':True,'suspensionEnabled':True}})+'\n')
 with (out/'upgrade.private.log').open('w') as log:
  result=subprocess.run(['helm','upgrade',e['release'],str(root/e['chart']),'-n',ns,'--reset-values','-f',str(out/'control-before.private.json'),'-f',str(out/'enable-overlay.json'),'--wait','--timeout','5m'],stdout=log,stderr=subprocess.STDOUT,timeout=330)
 if result.returncode:report.update(status='failed',reason='Control creation gate upgrade failed',helmExit=result.returncode);save();print(json.dumps(report));raise SystemExit(1)
secret=kube('-n',ns,'get','secret',current['api']['existingSecret']);password=base64.b64decode(secret['data']['admin-password']).decode().strip()
service=kube('-n',ns,'get','service',e['release']+'-api');base='http://'+service['spec']['clusterIP']+':'+str(service['spec']['ports'][0]['port']);jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
def request(path,body=None,headers=None):
 h={'Content-Type':'application/json'};h.update(headers or {})
 if body is not None:
  csrf=next((c.value for c in jar if c.name=='neon_v2_csrf'),None)
  if csrf:h['X-CSRF-Token']=csrf
 req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=h)
 try:
  with client.open(req,timeout=45) as response:return response.status,dict(response.headers),json.load(response)
 except urllib.error.HTTPError as error:
  data=error.read(8192)
  try:result=json.loads(data)
  except ValueError:result={'error':'non-JSON response'}
  return error.code,dict(error.headers),result
status,headers,login=request('/auth/login',{'username':'admin','password':password})
if status!=200:raise RuntimeError('Public API login failed')
status,headers,caps=request('/api/v1/capabilities')
(out/'capabilities.json').write_text(json.dumps(caps,indent=2)+'\n')
runtime=next(r for r in caps['postgres_runtimes'] if r['postgres_version']==pg and r['create_enabled'])
intent={'organization':org,'idempotencyKey':'helm-e2e-'+secrets.token_hex(16),'request':{'name':'Helm E2E PG'+str(pg)+' '+time.strftime('%H%M%S')+' '+secrets.token_hex(3),'password':secrets.token_urlsafe(24),'default_branch_name':'main','postgres_version':pg,'region_id':runtime['region_id'],'autoscaling':runtime['bounds']}}
(out/'creation-intent.private.json').write_text(json.dumps(intent,indent=2)+'\n')
report.update(status='create-submitted',creationEnabled=True);save()
status,headers,response=request('/api/v1/organizations/'+org+'/projects',intent['request'],{'Idempotency-Key':intent['idempotencyKey']})
(out/'create-response.private.json').write_text(json.dumps({'status':status,'body':response},indent=2)+'\n')
if status!=202:
 report.update(status='create-rejected',httpStatus=status,error=response);save();print(json.dumps(report));raise SystemExit(1)
operation=response['operation'];project=response['resource'];location=headers.get('Location') or headers.get('location') or '/api/v1/projects/'+project['id']+'/operations/'+operation['id']
report.update(status='operation-pending',projectID=project['id'],operationID=operation['id'],operationPath=location);save();print(json.dumps(report),flush=True)
deadline=time.monotonic()+360;last=None
while time.monotonic()<deadline:
 status,headers,state=request(location)
 (out/'operation-latest.private.json').write_text(json.dumps({'httpStatus':status,'body':state},indent=2)+'\n')
 operation=state.get('operation',state);phase=operation.get('state',operation.get('status'))
 if phase!=last:
  print(json.dumps({'operationID':report['operationID'],'status':phase,'httpStatus':status}),flush=True);last=phase
  if phase in ('queued','running','retry_wait','succeeded','completed','failed','cancelled','canceled'):report['operationStatus']=phase;save()
 if phase in ('succeeded','completed','failed','cancelled','canceled'):
  report.update(status='operation-'+phase,operationStatus=phase);save();print(json.dumps(report));break
 time.sleep(5)
else:report.update(status='operation-pending',reason='Bounded observation ended; continue original operation');save();print(json.dumps(report))
PY
