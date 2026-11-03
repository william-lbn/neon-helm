#!/usr/bin/env python3
"""两个聚焦OFFLINE-RENDER检查：不连接Kubernetes、不创建对象、不读取凭据。"""
from pathlib import Path
import argparse,copy,hashlib,io,json,shutil,subprocess,tarfile,time
import yaml
BASELINE='552f6b8e33997f424e87573391b3f1892d68771a'
REPO=Path(__file__).resolve().parents[3]
def fixture():
 # 全部镜像都是明确无运行用途的占位；没有生产digest/地址、密码、token或私钥。
 image=lambda role:'offline-render.invalid/neon/'+role+'@sha256:'+'a'*64
 return {'validation':{'labAcknowledged':True,'requirePinnedImages':True},'global':{'initImage':image('busybox'),'componentImages':{k:image(k) for k in ['pageserver','safekeeper','storageBroker','storageController','proxy']}},'minio':{'image':image('minio'),'mcImage':image('mc'),'existingSecret':'offline-render-object-store','region':'us-east-1'},'storageController':{'enabled':True,'managePageserver':True,'devMode':True,'hookUrl':'http://offline-render-adapter.invalid:8080/','hookTokenSecret':'offline-render-hook','existingSecret':'offline-render-controller-db','dbImage':image('postgres')},'compute':{'enabled':False},'proxy':{'enabled':False,'legacyApiEnabled':False,'image':'','authEndpoint':'http://offline-render-adapter.invalid:8080/cplane/','authSecret':'offline-render-proxy-auth','tlsSecret':'offline-render-proxy-tls'},'placement':{'allowedNodeNames':['worker-117','worker-118','worker-119']}}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--group',choices=['all','proxy','controller'],default='all');a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);chart=REPO/'charts/neon-core';start=time.monotonic();rows=[]
 def render(c,v,name,error=None):
  vf=out/(name+'.json');vf.write_text(json.dumps(v,indent=2)+'\n');cmd=['helm','template','offline-render',str(c),'-n','offline-render','--kube-version','1.31.2','-f',str(vf)];z=subprocess.run(cmd,capture_output=True);(out/(name+'.stdout')).write_bytes(z.stdout);(out/(name+'.stderr')).write_bytes(z.stderr);rows.append({'case':name,'exit':z.returncode,'expected_error':error})
  if error:
   assert z.returncode!=0 and error.encode() in z.stderr,name+' unrelated rejection';return None
  assert z.returncode==0,name+' render failed';return [d for d in yaml.safe_load_all(z.stdout) if d]
 if a.group in ['all','proxy']:
  v=fixture();v['proxy']['enabled']=True;docs=render(chart,v,'proxy-external-without-legacy-image');assert any(d['kind']=='Deployment' and d['metadata']['name']=='proxy' for d in docs);assert not any(d['metadata']['name']=='proxy-api' for d in docs)
  v['proxy']['legacyApiEnabled']=True;v['compute'].update(enabled=True,allowLabAutoBootstrap=True,image={'digest':'offline-render.invalid/never-deployed@sha256:'+'b'*64});render(chart,v,'proxy-legacy-missing-image','proxy.image must pin')
 if a.group in ['all','controller']:
  # 不依赖/data：原默认AST比较的基线直接来自同一仓库已提交历史。
  raw=subprocess.check_output(['git','-C',str(REPO),'archive',BASELINE,'charts/neon-core']);base=out/'baseline';base.mkdir()
  with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
   assert all(not x.name.startswith('/') and '..' not in Path(x.name).parts for x in tf.getmembers());tf.extractall(base,filter='data')
  v=fixture();before=render(base/'charts/neon-core',v,'controller-default-before');after=render(chart,v,'controller-default-after');assert before==after,'default AST changed'
  v['storageController']['nodeSelector']={'kubernetes.io/hostname':'worker-119'};selected=render(chart,v,'controller119');dep=next(x for x in selected if x['kind']=='Deployment' and x['metadata']['name']=='storage-controller');ns=dep['spec']['template']['spec']['nodeSelector'];assert ns['kubernetes.io/hostname']=='worker-119';assert ns['neon.tech/pg17-memory-pool']=='worker-117-worker-118-worker-119';ns.pop('kubernetes.io/hostname');assert selected==after,'another component/default field changed'
  for name,selector in [('schema116',{'kubernetes.io/hostname':'ubuntu'}),('schemaPool',{'neon.tech/pg17-memory-pool':'override'})]:
   x=fixture();x['storageController']['nodeSelector']=selector;render(chart,x,name,'storageController.nodeSelector')
  # 仅负例复制chart移除schema，核模板本身的拒绝；生产chart与schema没有被修改。
  guarded=out/'template-guard-only';shutil.copytree(chart,guarded);(guarded/'values.schema.json').unlink()
  for name,selector in [('template116',{'kubernetes.io/hostname':'ubuntu'}),('templateOS',{'kubernetes.io/os':'windows'})]:
   x=fixture();x['storageController']['nodeSelector']=selector;render(guarded,x,name,'pool/os/arch cannot be overridden')
 vf=out/'lint-values.json';vf.write_text(json.dumps(fixture()));z=subprocess.run(['helm','lint',str(chart),'--strict','-f',str(vf)],capture_output=True);(out/'lint.log').write_bytes(z.stdout+z.stderr);assert z.returncode==0
 result={'status':'PASS_OFFLINE_RENDER_ONLY_NOT_RUNTIME','group':a.group,'render_calls':rows,'lint_exit':0,'seconds':time.monotonic()-start,'fixture_scope':'OFFLINE-RENDER placeholders only; no production image/runtime fact','cluster_connections':False,'objects_created':False,'credentials_read':False,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()};(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':result['status'],'render_calls':len(rows),'result':str(out/'result.json')}))
if __name__=='__main__':main()
