#!/usr/bin/env python3
"""只验证本次默认关闭RBAC、精确权限及旧PodSpec不变；不访问真实集群。"""
import argparse, pathlib, subprocess, tempfile, json, hashlib, tarfile, io
import yaml
p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--output',required=True);p.add_argument('--base',default='c7b162270da6c074cd888322639c5c99756c8fbd');a=p.parse_args();repo=pathlib.Path(a.repo).resolve();out=pathlib.Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True)
fixture={'experimentalAcknowledged':True,'controller':{'labAcknowledged':True,'replicas':1},'network':{'secondary':{'enabled':False}},'images':{k:'127.0.0.1:5001/test/'+k+'@sha256:'+'a'*64 for k in ['controller','runner','vxlanController']}}
def render(chart,values,name,success=True):
 vp=out/(name+'.json');vp.write_text(json.dumps(values,indent=2)+'\n');cmd=['helm','template','neonvm',str(chart),'-n','default','--kube-version','1.31.2','-f',str(vp)];x=subprocess.run(cmd,capture_output=True,text=True);(out/(name+'.stderr')).write_text(x.stderr);(out/(name+'.yaml')).write_text(x.stdout)
 if success:assert x.returncode==0,(name,x.stderr);return [x for x in yaml.safe_load_all(x.stdout) if x]
 assert x.returncode!=0 and ('managedMemoryRetirement' in x.stderr or 'namespaces' in x.stderr),(name,x.stderr)
def key(x):return (x['kind'],x['metadata'].get('namespace',''),x['metadata']['name'])
def objects(xs):return {key(x):x for x in xs}
with tempfile.TemporaryDirectory(prefix='neonvm-retire-rbac-') as tmp:
 archive=subprocess.check_output(['git','-C',str(repo),'archive',a.base,'charts/neonvm'])
 with tarfile.open(fileobj=io.BytesIO(archive)) as tf:tf.extractall(tmp,filter='data')
 old=objects(render(pathlib.Path(tmp)/'charts/neonvm',fixture,'original-off'))
 new=objects(render(repo/'charts/neonvm',fixture,'current-off'));assert old==new,'默认off改变旧对象'
 on=json.loads(json.dumps(fixture));on['controller']['managedMemoryRetirement']={'enabled':True,'namespaces':['neon']};current=objects(render(repo/'charts/neonvm',on,'actual-on'));added=set(current)-set(new);assert len(added)==4 and all(current[k]==new[k] for k in new),'启用RBAC改变已有对象/PodSpec'
 cr=current[('ClusterRole','','neonvm-managed-memory-retirement-reader')];assert cr['rules']==[{'apiGroups':[''],'resources':['nodes'],'resourceNames':['worker-117','worker-118','worker-119'],'verbs':['get']},{'apiGroups':[''],'resources':['nodes'],'verbs':['list']}]
 role=current[('Role','neon','neonvm-managed-memory-retirement-sources')];assert role['rules']==[{'apiGroups':[''],'resources':['configmaps'],'verbs':['get','list','patch','delete']}]
 for kind,ns,name in added:
  x=current[(kind,ns,name)]
  if kind.endswith('Binding'):assert x['subjects']==[{'kind':'ServiceAccount','name':'neonvm-controller','namespace':'neonvm-system'}]
 for name,names in [('empty',[]),('invalid',['BAD']),('duplicate',['neon','neon'])]:
  bad=json.loads(json.dumps(on));bad['controller']['managedMemoryRetirement']['namespaces']=names;render(repo/'charts/neonvm',bad,'reject-'+name,False)
 lint=subprocess.run(['helm','lint',str(repo/'charts/neonvm'),'-f',str(out/'actual-on.json'),'--set','compatibility.allowUntestedKubernetes=true','--strict'],capture_output=True,text=True);(out/'lint.log').write_text(lint.stdout+lint.stderr);assert lint.returncode==0
result={'status':'PASS','cases':['default_off_original_object_equivalence','enabled_only_four_RBAC_objects_all_existing_PodSpecs_identical','Node_get_three_only_plus_required_readonly_list','namespace_CM_exact_verbs_and_controller_subject','reject_empty_namespace','reject_invalid_namespace','reject_duplicate_namespace','helm_lint_strict'],'case_count':8,'base':a.base,'kube_version':'1.31.2','cluster_access':False};(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
