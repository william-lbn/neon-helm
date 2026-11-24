set -eu
export KUBECONFIG=${KUBECONFIG:?Explicit kubeconfig required}
export NEON_E2E_PG=${1:?PostgreSQL major required} NEON_E2E_CASE=${2:?Case ID required}
python3 -B - <<'PY'
import base64,hashlib,http.cookiejar,json,os,pathlib,re,subprocess,urllib.error,urllib.request
os.umask(0o077);pg=os.environ['NEON_E2E_PG'];case=os.environ['NEON_E2E_CASE']
if pg not in ('17','18') or not re.fullmatch('[0-9]{3}',case):raise RuntimeError('Invalid acceptance case')
root=pathlib.Path(os.environ['NEON_SITE_ROOT']);business=root/('business-pg'+pg+'-'+case);out=business/'sql-001'
if out.exists():raise SystemExit('Original SQL intent exists; inspect receipt, never replay unknown writes')
state=json.loads((business/'receipt.json').read_text());intent=json.loads((business/'creation-intent.private.json').read_text())
if state.get('operationStatus') not in ('succeeded','completed'):raise RuntimeError('Public creation must complete before SQL acceptance')
entry=next(e for e in json.loads((root/'site.json').read_text())['releases'] if e['id']=='control');ns=entry['namespace']
def run(*args):return subprocess.check_output(args,text=True,timeout=40)
def kube(*args):return json.loads(run('kubectl',*args,'-o','json'))
values=json.loads(run('helm','get','values',entry['release'],'-n',ns,'--all','-o','json'))
if values['api']['pgTLSMode']!='verify-full' or not values['api']['pgCASecret']:raise RuntimeError('Verified Proxy TLS must remain enabled')
secret=kube('-n',ns,'get','secret',values['api']['existingSecret']);password=base64.b64decode(secret['data']['admin-password']).decode().strip()
service=kube('-n',ns,'get','service',entry['release']+'-api');base='http://'+service['spec']['clusterIP']+':'+str(service['spec']['ports'][0]['port']);jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
def request(path,body=None):
 headers={'Content-Type':'application/json'}
 if body is not None:
  csrf=next((c.value for c in jar if c.name=='neon_v2_csrf'),None)
  if csrf:headers['X-CSRF-Token']=csrf
 try:
  with client.open(urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=45) as response:return response.status,json.load(response)
 except urllib.error.HTTPError as error:
  try:body=json.loads(error.read(8192))
  except ValueError:body={'error':'non-JSON response'}
  return error.code,body
status,response=request('/auth/login',{'username':'admin','password':password})
if status!=200:raise RuntimeError('Public API login failed')
project=state['projectID'];status,response=request('/api/v1/projects/'+project+'/endpoints')
if status!=200:raise RuntimeError('Public endpoint list unavailable')
endpoints=response.get('items',[]) if isinstance(response,dict) else response
if len(endpoints)!=1:raise RuntimeError('Expected one acceptance endpoint')
endpoint=endpoints[0]['id'];path='/api/v1/projects/'+project+'/endpoints/'+endpoint+'/query';out.mkdir(mode=0o700)
report={'status':'submitted','projectID':project,'endpointID':endpoint,'postgresVersion':int(pg),'pgTLSMode':'verify-full','sql':'NOT_COMPLETE','automaticMemory':'NOT_COMPLETE'}
def save():(out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
def query(name,sql):
 # 每条写入仅提交一次；HTTP未知结果保留原SQL，后续只读确认。
 (out/(name+'.sql')).write_text(sql+'\n');status,body=request(path,{'password':intent['request']['password'],'sql':sql});(out/(name+'.json')).write_text(json.dumps({'httpStatus':status,'body':body},indent=2)+'\n')
 if status!=200:
  report.update(status='failed',failedStep=name,httpStatus=status,errorCode=body.get('code',body.get('error')));save();print(json.dumps(report));raise SystemExit(1)
 return body
save();identity=query('identity',"SELECT current_setting('server_version_num')::integer AS version_num, current_database() AS database, current_user AS role")
row=identity['rows'][0]
if int(row[0])//10000!=int(pg):raise RuntimeError('Actual PostgreSQL version differs')
query('create-table','CREATE TABLE public.helm_acceptance (id bigint PRIMARY KEY, payload text NOT NULL)')
query('insert-data',"INSERT INTO public.helm_acceptance SELECT g, md5(g::text) FROM generate_series(1,10000) g")
data=query('data-before',"SELECT count(*)::integer, sum(id)::bigint, md5(string_agg(payload, ',' ORDER BY id)) FROM public.helm_acceptance")
if data['rows'][0][:2]!=[10000,50005000]:raise RuntimeError('Committed SQL data differs')
report.update(status='completed',sql='PASS',actualVersionNum=row[0],proxyClientTLSMode='verify-full',rowCount=10000,sumID=50005000,dataChecksum=data['rows'][0][2]);save();print(json.dumps(report))
PY
