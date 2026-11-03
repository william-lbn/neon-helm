#!/usr/bin/env python3
"""重跑显式 Host Kubernetes 预算 Helm 接线：--output /data/.../新目录。
复用既有 DSGA fixture/解析器；只离线渲染 autoscaler，不访问集群或签发资格。
"""
from pathlib import Path
import argparse,copy,datetime,hashlib,importlib.util,json,os,subprocess,sys,time
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();(out/'fixtures').mkdir();start=time.monotonic()
spec=importlib.util.spec_from_file_location('dsga_check',root/'tools/check-pg17-dsga.py');dsga=importlib.util.module_from_spec(spec);spec.loader.exec_module(dsga)
base=dsga.base;chart=root/'charts/neon-autoscaler';legacy=dsga.fixture();valid=copy.deepcopy(legacy)
for n in valid['dsga']['scheduler']['nodes']:
 n['system_bytes']='4294967296'
 profile={key:n['profile'][key]for key in ['id','scheduler_name','vm_overhead_bytes','pod_overhead_bytes']}
 digest=hashlib.sha256(json.dumps(profile,separators=(',',':')).encode()).hexdigest()
 n['kubernetes_budget']={'protocol_version':1,'scope':'kubernetes-node-memory-budget-v1','node_name':n['binding']['node_name'],'node_uid':n['binding']['node_uid'],'capacity_bytes':'9007199254740993','allocatable_bytes':'9007199254740993','system_reservation_bytes':n['system_bytes'],'profile_sha256':digest}
empty=out/'offline.kubeconfig';empty.write_text('apiVersion: v1\nkind: Config\nclusters: []\nusers: []\ncontexts: []\ncurrent-context: ""\n');empty.chmod(0o600);env=dict(os.environ,KUBECONFIG=str(empty),HELM_NO_PLUGINS='1');records=[];seq=0

def render(name,value,reject=False):
 global seq
 seq+=1;fixture=out/'fixtures'/(str(seq)+'-'+name+'.json');fixture.write_text(json.dumps(value,indent=2)+'\n')
 r=subprocess.run(['helm','template',str(chart),'-f',str(fixture),'--namespace','kube-system','--kube-version','1.31.2'],capture_output=True,text=True,env=env,timeout=30)
 (out/'logs'/(str(seq)+'-'+name+'.stdout')).write_text(r.stdout);(out/'logs'/(str(seq)+'-'+name+'.stderr')).write_text(r.stderr)
 assert (r.returncode!=0 if reject else r.returncode==0),(name,r.stderr[-2000:])
 records.append({'case':name,'status':'PASS','expected_refusal':reject})
 if reject:return
 cm=next(o for o in base.documents(r.stdout)if o and o.get('kind')=='ConfigMap'and o['metadata']['name']=='scheduler-plugin-config')
 nodes=json.loads(cm['data']['autoscale-enforcer-config.json'])['dsgaHost']['nodes']
 assert nodes==value['dsga']['scheduler']['nodes'],'explicit decimal input changed during Helm rendering'
 return nodes

try:
 nodes=render('legacy-no-policy-preserved',legacy);assert all('kubernetes_budget'not in n for n in nodes)
 nodes=render('explicit-policy-exact-above-2pow53',valid);assert nodes[0]['kubernetes_budget']['capacity_bytes']=='9007199254740993'
 for mode in ['node-name','node-uid','system-reservation','profile-sha','scope','version','capacity-number','capacity-overflow','unknown-field','null-policy']:
  value=copy.deepcopy(valid);n=value['dsga']['scheduler']['nodes'][0];p=n['kubernetes_budget']
  if mode=='node-name':p['node_name']='worker-119'
  elif mode=='node-uid':p['node_uid']='00000000-0000-0000-0000-000000000098'
  elif mode=='system-reservation':p['system_reservation_bytes']='4294967297'
  elif mode=='profile-sha':p['profile_sha256']='a'*64
  elif mode=='scope':p['scope']='absolute-host-kernel-bound'
  elif mode=='version':p['protocol_version']=2
  elif mode=='capacity-number':p['capacity_bytes']=9007199254740993
  elif mode=='capacity-overflow':p['capacity_bytes']='18446744073709551616'
  elif mode=='unknown-field':p['absolute_kernel_bound']=True
  elif mode=='null-policy':n['kubernetes_budget']=None
  render(mode,value,reject=True)
 result={'status':'PASS','checks':records,'seconds':time.monotonic()-start,'helm_invocations':seq,'Scope':'HELM_PRIVATE_INPUT_CONTRACT_MODEL_NOT_LINUX_PLATFORM_CERTIFICATION','deployed':False,'Source':False,'K8s_E2E':False,'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
except Exception as e:result={'status':'FAIL','checks':records,'error':repr(e),'seconds':time.monotonic()-start,'deployed':False}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='checks'}));raise SystemExit(0 if result['status']=='PASS'else 1)
