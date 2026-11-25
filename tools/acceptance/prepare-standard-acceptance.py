#!/usr/bin/env python3
"""从本次真实安装回执建立验收目录，并通过公开API创建新组织。"""
import argparse,base64,hashlib,http.cookiejar,json,os,pathlib,secrets,subprocess,sys,urllib.request
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from standard_contract import input_manifest
p=argparse.ArgumentParser();p.add_argument('--site',required=True);p.add_argument('--deployment',required=True);p.add_argument('--out',required=True);a=p.parse_args();os.umask(0o077)
siteFile=pathlib.Path(a.site).resolve();site=json.loads(siteFile.read_text());receiptFile=pathlib.Path(a.deployment).resolve();receipt=json.loads(receiptFile.read_text());out=pathlib.Path(a.out).resolve()
if receipt['status']!='installed' or receipt['site']!=site['name'] or receipt['inputSHA256']!=hashlib.sha256(siteFile.read_bytes()).hexdigest():raise RuntimeError('Actual standard installation and its exact original input must complete first')
out.mkdir(mode=0o700);entries=[dict(v,id=k,chart=str((siteFile.parent/v['chart']).resolve())) for k,v in site['releases'].items()];(out/'site.json').write_text(json.dumps({'releases':entries,'deploymentReceipt':str(receiptFile),'siteConfig':str(siteFile)},indent=2)+'\n');os.environ['KUBECONFIG']=site['kubeconfig'];entry=site['releases']['control']
def kube(*args):return json.loads(subprocess.check_output(['kubectl',*args,'-o','json'],timeout=40))
if receipt.get('inputSet')!=input_manifest(siteFile,site) or receipt.get('clusterUID')!=kube('get','namespace','kube-system')['metadata']['uid']:raise RuntimeError('本次验收必须使用完整输入锁与原目标集群，不能采用历史收据')
values=json.loads(subprocess.check_output(['helm','get','values',entry['release'],'-n',entry['namespace'],'--all','-o','json'],timeout=40));secret=kube('-n',entry['namespace'],'get','secret',values['api']['existingSecret'])
for kind,name,actual in [('Namespace',entry['namespace'],kube('get','namespace',entry['namespace'])),('Secret',values['api']['existingSecret'],secret),('Secret',values['dsga']['runtimeCatalogSecret'],kube('-n',entry['namespace'],'get','secret',values['dsga']['runtimeCatalogSecret']))]:
 original=next(r for r in receipt['createdResources'] if r['kind']==kind and r['name']==name and (kind=='Namespace' or r['namespace']==entry['namespace']))
 if actual['metadata']['uid']!=original['uid']:raise RuntimeError('Acceptance receipt refers to a different installation incarnation')
admin=base64.b64decode(secret['data']['admin-password']).decode().strip();service=kube('-n',entry['namespace'],'get','service',entry['release']+'-api');base='http://'+service['spec']['clusterIP']+':'+str(service['spec']['ports'][0]['port']);jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
with client.open(urllib.request.Request(base+'/auth/login',data=json.dumps({'username':'admin','password':admin}).encode(),headers={'Content-Type':'application/json'}),timeout=40) as r:
 if r.status!=200:raise RuntimeError('Public login failed')
name='Standard Helm acceptance '+secrets.token_hex(6);intent={'name':name};(out/'organization-intent.json').write_text(json.dumps(intent)+'\n');headers={'Content-Type':'application/json','X-CSRF-Token':next(c.value for c in jar if c.name=='neon_v2_csrf')}
with client.open(urllib.request.Request(base+'/api/v1/organizations',data=json.dumps(intent).encode(),headers=headers),timeout=40) as r:
 if r.status!=201:raise RuntimeError('Public organization creation unconfirmed')
 organization=json.load(r)
(out/'organization.json').write_text(json.dumps(organization,indent=2)+'\n');print(json.dumps({'status':'acceptance-prepared','organization':organization['id'],'out':str(out),'deploymentReceipt':str(receiptFile)}))
