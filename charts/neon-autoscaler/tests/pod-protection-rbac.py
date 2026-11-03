#!/usr/bin/env python3
"""仅复验DSGA额外3namespace Pod保护Role；不访问集群、不签发身份。"""
import argparse,copy,hashlib,json,pathlib,subprocess,time
import yaml
def must(value,message):
 if not value:raise AssertionError(message)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=pathlib.Path,required=True);args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);chart=pathlib.Path(__file__).resolve().parents[1];started=time.monotonic()
 image='render.invalid/component@sha256:'+'a'*64
 off={'experimentalAcknowledged':True,'images':{'agent':image,'scheduler':image}}
 on=copy.deepcopy(off);nodes=json.loads((chart/'files/pg17-node-identities.json').read_text())['allowedNodeUIDs'];profile={'id':'render-only-budget','scheduler_name':'autoscale-scheduler','vm_overhead_bytes':str(3<<30),'pod_overhead_bytes':str(16<<20)};digest=hashlib.sha256(json.dumps(profile,separators=(',',':')).encode()).hexdigest();rows=[]
 for i,(name,uid) in enumerate(nodes.items()):
  system=str((8 if name=='worker-118' else 4)<<30)
  rows.append({'binding':{'node_name':name,'node_uid':uid,'namespace':'neon','lease_name':'render-only-host-'+name,'lease_uid':'00000000-0000-0000-0000-'+str(i+1).zfill(12)},'profile':profile,'system_bytes':system,'kubernetes_budget':{'protocol_version':1,'scope':'kubernetes-node-memory-budget-v1','node_name':name,'node_uid':uid,'capacity_bytes':str(24<<30),'allocatable_bytes':str(24<<30),'system_reservation_bytes':system,'profile_sha256':digest}})
 wanted=['kube-system','neon-cert-manager','neonvm-system'];on['dsga']={'enabled':True,'agent':{'gatewayURL':'https://render.invalid:8444','managementCASecret':'render-only-public-ca'},'scheduler':{'nodes':rows,'podProtectionNamespaces':wanted}}
 cases=[('default-off',off,None),('explicit-three',on,None)]
 for name,values,reason in [('forbidden-namespace',['kube-system','neon-cert-manager','default'],'must be one of'),('duplicate',['kube-system','kube-system','neonvm-system'],'unique'),('incomplete',['kube-system'],'at least 3'),('wrong-type','kube-system','Expected: array')]:
  fixture=copy.deepcopy(on);fixture['dsga']['scheduler']['podProtectionNamespaces']=values;cases.append((name,fixture,reason))
 records=[]
 for name,values,reason in cases:
  vf=out/(name+'.json');vf.write_text(json.dumps(values,indent=2)+chr(10));cmd=['helm','template','rbac-contract',str(chart),'-n','default','--kube-version','1.31.2','-f',str(vf)];p=subprocess.run(cmd,capture_output=True,text=True);(out/(name+'.yaml')).write_text(p.stdout);(out/(name+'.stderr')).write_text(p.stderr);must((p.returncode==0)==(reason is None),name+': wrong exit '+p.stderr)
  if reason:must(reason in p.stderr,name+': unrelated refusal '+p.stderr)
  records.append({'case':name,'argv':cmd,'exit':p.returncode,'expected_error':reason})
 def objects(name):return [x for x in yaml.safe_load_all((out/(name+'.yaml')).read_text()) if x]
 def roles(name):return [x for x in objects(name) if x.get('metadata',{}).get('name')=='neon-dsga-scheduler-pod-protection']
 must(not roles('default-off'),'off changed privileges');actual=roles('explicit-three');must(len(actual)==6,'Role+Binding count differs')
 def scheduler(name):return next(x for x in objects(name) if x['kind']=='Deployment' and x['metadata']['name']=='autoscale-scheduler')
 must('strategy' not in scheduler('default-off')['spec'],'legacy rollout changed')
 strategy=scheduler('explicit-three')['spec']['strategy'];must(strategy['type']=='Recreate' and strategy.get('rollingUpdate') is None,'DSGA rollout may create a double scheduler peak')
 for ns in wanted:
  role=next(x for x in actual if x['kind']=='Role' and x['metadata']['namespace']==ns);must(role['rules']==[{'apiGroups':[''],'resources':['pods'],'verbs':['get','patch']}],'privilege grew')
  binding=next(x for x in actual if x['kind']=='RoleBinding' and x['metadata']['namespace']==ns);must(binding['subjects']==[{'kind':'ServiceAccount','name':'autoscale-scheduler','namespace':'kube-system'}],'subject differs');must(binding['roleRef']['name']==role['metadata']['name'],'wrong role')
 source=next(x for x in objects('explicit-three') if x['kind']=='ConfigMap' and x['metadata']['name']=='scheduler-plugin-config');runtime=json.loads(source['data']['autoscale-enforcer-config.json']);must(all('initialize_at_resource_version' not in n for n in runtime['dsgaHost']['nodes']),'render must not authorize bootstrap')
 result={'status':'PASS_THREE_NAMESPACE_POD_PROTECTION_RENDER','cases':records,'Role_count':3,'RoleBinding_count':3,'new_role_verbs':['get','patch'],'new_role_resources':['pods'],'default_off_no_new_privilege':True,'no_initialize_RV_in_fixture':True,'cluster_write_performed':False,'render_fixture_only_not_actual_leases':True,'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'seconds':time.monotonic()-started};(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+chr(10));print(json.dumps({'status':result['status'],'cases':len(cases),'result':str(out/'result.json'),'seconds':result['seconds']}))
if __name__=='__main__':main()
