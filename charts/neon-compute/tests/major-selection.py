#!/usr/bin/env python3
"""仅离线Helm版本选择：17版本契约保持，18明确选择；放置标准化差异单独核对；不访问K8s或冒真实PG18验收。"""
import argparse,copy,hashlib,json,pathlib,subprocess
import yaml

def must(ok,message):
 if not ok:raise AssertionError(message)

def reviewed_placement(output):
 docs=[x for x in yaml.safe_load_all(output) if x]
 for obj in docs:
  if obj["kind"]!="VirtualMachine":continue
  spec=obj["spec"];selector=spec.get("nodeSelector",{});legacy="neon.tech/pg17-memory-pool"
  if legacy not in selector:
   if "affinity" in spec and spec["affinity"] is None:del spec["affinity"]
   continue
  affinity=spec.get("affinity",{});terms=affinity.get("nodeAffinity",{}).get("requiredDuringSchedulingIgnoredDuringExecution",{}).get("nodeSelectorTerms",[])
  must(len(terms)==1 and list(terms[0])==["matchExpressions"] and len(terms[0]["matchExpressions"])==1,"unreviewed legacy affinity")
  expression=terms[0]["matchExpressions"][0];names=expression.get("values",[])
  must(expression=={"key":"kubernetes.io/hostname","operator":"In","values":names} and names and len(names)==len(set(names)) and selector[legacy]=="-".join(sorted(names)),"legacy pool/affinity authority changed")
  del selector[legacy];del spec["affinity"]
 return docs

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--chart',type=pathlib.Path)
 ap.add_argument('--baseline-chart',type=pathlib.Path,required=True)
 ap.add_argument('--output',type=pathlib.Path,required=True)
 ap.add_argument('--helm',default='helm')
 a=ap.parse_args();chart=(a.chart or pathlib.Path(__file__).resolve().parents[1]).resolve()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 guest17='render.invalid/pg17@sha256:'+'a'*64
 guest18='render.invalid/pg18@sha256:'+'d'*64
 legacy={'experimentalAcknowledged':True,'compute':{'image':guest17,'tenantId':'1'*32,'timelineId':'2'*32,'existingConfigSecret':'OFFLINE-config'}}
 managed=copy.deepcopy(legacy);managed['network']={'secondary':{'enabled':False}}
 managed['compute'].update(name='cp-'+'1'*16,existingConfigSecret='cp-'+'1'*16+'-config',startupMode='trusted-runtime-v1',cpu={'min':2,'use':2,'max':2},memory={'slotSize':'1Gi','minSlots':7,'useSlots':7,'maxSlots':8,'minBound':'7Gi','maxBound':'8Gi'},runtime={'executionModel':'trusted-controller-v1','projectId':'OFFLINE-project','endpointId':'ep_'+'1'*16,'incarnation':'3'*32,'computeInstanceId':'OFFLINE-compute','runnerImage':'render.invalid/shared-runner@sha256:'+'b'*64,'kernelImage':'render.invalid/shared-kernel@sha256:'+'c'*64,'serviceAccountName':'offline-account','configMountPath':'/neonvm/config','configFile':'compute-public.json','postgresPort':55432,'podResources':{'limits':{'cpu':'4','memory':'11Gi'},'requests':{'cpu':'2','memory':'11Gi'}}})
 receipts=[]
 def render(name,root,values,success=True,field=None):
  vf=out/(name+'.json');vf.write_text(json.dumps(values,indent=2)+'\n')
  cmd=[a.helm,'template','major-selection',str(root),'-n','offline-major','--kube-version','1.31.2','-f',str(vf)]
  q=subprocess.run(cmd,capture_output=True,text=True)
  (out/(name+'.yaml')).write_text(q.stdout);(out/(name+'.stderr')).write_text(q.stderr)
  receipts.append({'case':name,'exit':q.returncode,'expected_success':success})
  must((q.returncode==0)==success,name+': wrong Helm result')
  if field:must(field in q.stderr,name+': unrelated refusal')
  return q.stdout
 for name,values in [('legacy-default17',legacy),('trusted-default17',managed)]:
  before=render(name+'-before',a.baseline_chart,values)
  after=render(name+'-after',chart,values)
  must(reviewed_placement(before)==reviewed_placement(after),name+': unreviewed default17 change')
 explicit17=copy.deepcopy(managed);explicit17['compute']['pgVersion']=17
 must(reviewed_placement(render('trusted-explicit17-before',a.baseline_chart,explicit17))==reviewed_placement(render('trusted-explicit17-after',chart,explicit17)),'unreviewed explicit17 change')
 must((out/'trusted-default17-after.yaml').read_bytes()==(out/'trusted-explicit17-after.yaml').read_bytes(),'current default and explicit17 differ')
 v18=copy.deepcopy(managed);v18['compute'].update(pgVersion=18,image=guest18)
 output=render('trusted-explicit18',chart,v18)
 vm=next(x for x in yaml.safe_load_all(output)if x and x['kind']=='VirtualMachine')
 must(vm['metadata']['annotations']['neon-control/postgres-major']=='18','18 choice not carried by original manifest')
 must(vm['spec']['guest']['rootDisk']['image']==guest18,'18 guest was silently replaced')
 must('env'not in vm['spec']['guest']and'args'not in vm['spec']['guest'],'18 trusted image received legacy boot override')
 must(vm['spec']['dsgaBootstrap']['ready']is False,'18 must remain held')
 must(vm['spec']['runnerImage']==managed['compute']['runtime']['runnerImage']and vm['spec']['guest']['kernelImage']==managed['compute']['runtime']['kernelImage'],'shared version-independent images were rejected or changed')
 for major in [0,16,19]:
  bad=copy.deepcopy(v18);bad['compute']['pgVersion']=major
  render('unsupported-major-'+str(major),chart,bad,False,'pgVersion')
 bad=copy.deepcopy(v18);bad['compute']['startupMode']='legacy';render('18-legacy-refused',chart,bad,False,'startupMode')
 bad=copy.deepcopy(v18);bad['compute']['image']='';render('18-no-image-refused',chart,bad,False,'Pin compute.image')
 bad=copy.deepcopy(v18);bad['compute']['runtime']['runnerImage']='';render('18-no-runner-refused',chart,bad,False)
 lint=[a.helm,'lint',str(chart),'-f',str(out/'trusted-explicit18.json')]
 q=subprocess.run(lint,capture_output=True,text=True);(out/'lint.log').write_text(q.stdout+q.stderr);must(q.returncode==0,'18 lint failed')
 r={'status':'PASS_PG17_VERSION_CONTRACT_AND_EXPLICIT_PG18_CHART_ONLY','cases':receipts,'historical17_equal_except_reviewed_placement':True,'current_default_and_explicit17_byte_identical':True,'PG18_shared_Runner_Kernel_allowed':True,'all_UID_Source_normal_E_K8s_proof':False,'cluster_API_writes':False,'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
 (out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'cases':len(receipts)}))
if __name__=='__main__':main()
