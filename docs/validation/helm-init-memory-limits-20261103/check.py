#!/usr/bin/env python3
"""复现入口：python3 docs/validation/helm-init-memory-limits-20261103/check.py --output /data/.../新目录。
依赖已有 helm、PyYAML 及仓库 tools/check-pg17-helm.py；合成镜像仅用于离线检查。
"""
from pathlib import Path
import subprocess,json,os,sys,importlib.util,time,hashlib,decimal,re,datetime
sys.dont_write_bytecode=True
import argparse
parser=argparse.ArgumentParser(description="PG17 三处 init/job 内存接线离线重跑；仅渲染五个相关 chart，不访问集群")
parser.add_argument('--output',type=Path,required=True,help="新建归档目录；保留日志、输入、原结果")
args=parser.parse_args()
p=args.output.resolve();p.mkdir(parents=True,exist_ok=False)
src=Path(__file__).resolve().parents[3]
start=time.monotonic();(p/'logs').mkdir();(p/'fixtures').mkdir()
spec=importlib.util.spec_from_file_location('base',src/'tools/check-pg17-helm.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
empty=p/'offline.kubeconfig';empty.write_text('apiVersion: v1\nkind: Config\nclusters: []\nusers: []\ncontexts: []\ncurrent-context: ""\n');empty.chmod(0o600)
env=dict(os.environ,KUBECONFIG=str(empty),HELM_NO_PLUGINS='1');records=[];seq=0
charts=['neonvm','neon-autoscaler','neon-core','compute-management-gateway','neon-metadata'];values={}
for chart in charts:
 v=json.loads((src/'profiles/lab'/(chart+'.json')).read_text())
 if chart!='neon-metadata':v['placement']={'allowedNodeNames':list(base.NODES)}
 if chart in ['neonvm','neon-autoscaler']:
  v['compatibility']={'expectedKubernetesMinor':'31','allowUntestedKubernetes':False}
  defaults=base.yaml.safe_load((src/'charts'/chart/'values.yaml').read_text());v['images']={key:base.image(chart+'-'+key)for key in defaults['images']}
 if chart=='neonvm':v['controller']['runnerCgroupEnabled']=True
 if chart=='neon-core':
  v=base.merge(v,{'minio':{'image':base.image('minio'),'mcImage':base.image('mc'),'productStorage':{'enabled':False}},'global':{'initImage':base.image('init'),'componentImages':{key:base.image(key)for key in ['pageserver','safekeeper','storageBroker','proxy','storageController']}},'compute':{'enabled':False},'computeResize':{'enabled':False}})
 if chart=='compute-management-gateway':v['image']={'reference':base.image('gateway')}
 if chart=='neon-metadata':v['image']=base.image('metadata')
 values[chart]=v

def helm(chart,v,action='template',failure=False):
 global seq
 seq+=1;fixture=p/'fixtures'/(str(seq)+'-'+chart+'.json');fixture.write_text(json.dumps(v,indent=2)+'\n')
 cmd=['helm',action,str(src/'charts'/chart),'-f',str(fixture)]
 if action=='lint':cmd+=['--strict']
 else:cmd+=['--namespace','neon','--kube-version','1.31.2']
 r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=30)
 (p/'logs'/(str(seq)+'-'+chart+'.stdout')).write_text(r.stdout);(p/'logs'/(str(seq)+'-'+chart+'.stderr')).write_text(r.stderr)
 assert (r.returncode!=0 if failure else r.returncode==0),(cmd,r.stderr[-2000:])
 return [o for o in base.documents(r.stdout)if o]if not failure and action=='template'else r

def memory_positive(q):
 if isinstance(q,(float,int)):return q>0
 m=re.fullmatch(r'([+-]?[0-9]+(?:\.[0-9]+)?)(?:[EPTGMK]i|[EPTGMkKmun]|[eE][+-]?[0-9]+)?',str(q))
 return m is not None and decimal.Decimal(m[1])>0

try:
 for chart,v in values.items():
  helm(chart,v,'lint');objects=helm(chart,v);containers=[]
  if chart!='neon-metadata':base.check_render(objects)
  for obj,pod in base.pod_specs(objects):
   for kind in ['containers','initContainers']:
    for c in pod.get(kind,[]):
     memory=c.get('resources',{}).get('limits',{}).get('memory');assert memory_positive(memory),(chart,obj['metadata']['name'],kind,c['name'],memory)
     containers.append({'workload':obj['kind']+'/'+obj['metadata']['name'],'container_kind':kind,'name':c['name'],'memory_limit':memory})
  assert containers;records.append({'case':'default-full-hard-limits','chart':chart,'status':'PASS','containers':containers})
 for chart,path,name in [('neon-core',['minio','initResources'],'mc'),('neon-core',['pageserver','initResources'],'init-config'),('neonvm',['vxlanController','initResources'],'install-cni')]:
  override=base.merge(values[chart],{path[0]:{path[1]:{'requests':{'cpu':'40m','memory':'64Mi'},'limits':{'cpu':'300m','memory':'256Mi'}}}})
  objs=helm(chart,override);found=[c for o,s in base.pod_specs(objs)for kind in ['containers','initContainers']for c in s.get(kind,[])if c['name']==name]
  assert len(found)==1 and found[0]['resources']=={'requests':{'cpu':'40m','memory':'64Mi'},'limits':{'cpu':'300m','memory':'256Mi'}}
  records.append({'case':'explicit-values-wired','chart':chart,'path':'.'.join(path),'container':name,'status':'PASS'})
  for bad in [0,-1,'0Mi',None]:
   value=base.merge(values[chart],{path[0]:{path[1]:{'limits':{'memory':bad}}}});r=helm(chart,value,failure=True);assert path[1]in r.stderr and 'memory'in r.stderr
   records.append({'case':'invalid-memory-refused','chart':chart,'path':'.'.join(path),'bad':bad,'status':'PASS'})
 result={'status':'PASS','checks':records,'check_count':len(records),'helm_invocations':seq,'seconds':time.monotonic()-start,'deployed':False,'release':False,'K8s_E2E':False,'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
except Exception as e:
 result={'status':'FAIL','checks':records,'error':repr(e),'seconds':time.monotonic()-start,'deployed':False,'release':False,'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(p/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='checks'},ensure_ascii=False),flush=True);raise SystemExit(0 if result['status']=='PASS'else 1)
