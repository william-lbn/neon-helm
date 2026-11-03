#!/usr/bin/env python3
"""PG17 Runner硬限的定向离线渲染；不访问集群、不创建VM/Secret。"""
import argparse,copy,hashlib,io,json,pathlib,subprocess,tarfile,time
import yaml
BASELINE="552f6b8e33997f424e87573391b3f1892d68771a"
def must(ok,message):
 if not ok:raise AssertionError(message)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=pathlib.Path,required=True);args=ap.parse_args()
 repo=pathlib.Path(__file__).resolve().parents[3];out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
 base=out/'baseline';base.mkdir()
 raw=subprocess.check_output(['git','-C',str(repo),'archive',BASELINE,'charts/neon-compute'])
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tf:
  must(all(not x.name.startswith('/') and '..' not in pathlib.PurePosixPath(x.name).parts for x in tf.getmembers()),'unsafe archive')
  tf.extractall(base)
 image='render.invalid/guest@sha256:'+'a'*64
 legacy={'experimentalAcknowledged':True,'compute':{'image':image,'tenantId':'1'*32,'timelineId':'2'*32,'existingConfigSecret':'render-only-config'}}
 managed=copy.deepcopy(legacy);managed['network']={'secondary':{'enabled':False}};managed['compute'].update(name='cp-'+'1'*16,existingConfigSecret='cp-'+'1'*16+'-config',startupMode='trusted-runtime-v1',cpu={'min':2,'use':2,'max':2},memory={'slotSize':'1Gi','minSlots':7,'useSlots':7,'maxSlots':8,'minBound':'7Gi','maxBound':'8Gi'},runtime={'executionModel':'trusted-controller-v1','projectId':'render-only-project','endpointId':'ep_'+'1'*16,'incarnation':'3'*32,'computeInstanceId':'cp-'+'1'*16,'runnerImage':'render.invalid/runner@sha256:'+'b'*64,'kernelImage':'render.invalid/kernel@sha256:'+'c'*64,'serviceAccountName':'render-only-account','configMountPath':'/neonvm/config','configFile':'compute-public.json','postgresPort':55432,'podResources':{'limits':{'cpu':'4','memory':'10Gi'},'requests':{'cpu':'2','memory':'10Gi'}}})
 cases=[('legacy-before',base,legacy,None),('legacy-after',repo,legacy,None),('trusted-cap',repo,managed,None)]
 for name,resources,error in [('missing-limits',{},'limits is required'),('missing-cpu',{'limits':{'memory':'10Gi'}},'cpu is required'),('missing-memory',{'limits':{'cpu':'4'}},'memory is required'),('zero-memory',{'limits':{'cpu':'4','memory':'0Gi'}},'Does not match pattern'),('numeric-memory',{'limits':{'cpu':'4','memory':10737418240}},'Expected: string'),('device-copy',{'limits':{'cpu':'4','memory':'10Gi','neonvm/kvm':'1'}},'Additional property neonvm/kvm')]:
  v=copy.deepcopy(managed);v['compute']['runtime']['podResources']=resources
  cases.append((name,repo,v,error))
 receipts=[]
 for name,root,values,error in cases:
  vf=out/(name+'.json');vf.write_text(json.dumps(values,indent=2)+'\n')
  cmd=['helm','template','pod-limits',str(root/'charts/neon-compute'),'-n','render-only','--kube-version','1.31.2','-f',str(vf)]
  p=subprocess.run(cmd,capture_output=True,text=True);(out/(name+'.yaml')).write_text(p.stdout);(out/(name+'.stderr')).write_text(p.stderr)
  must((p.returncode==0)==(error is None),name+': wrong exit '+p.stderr)
  if error:must(error in p.stderr,name+': unrelated refusal '+p.stderr)
  receipts.append({'case':name,'argv':cmd,'exit':p.returncode,'expected_schema_error':error})
 def objects(name):return [d for d in yaml.safe_load_all((out/(name+'.yaml')).read_text()) if d]
 must(objects('legacy-before')==objects('legacy-after'),'legacy resources changed')
 vm=next(d for d in objects('trusted-cap') if d['kind']=='VirtualMachine');spec=vm['spec']
 must(spec['podResources']==managed['compute']['runtime']['podResources'],'resource values were lost or changed')
 must(spec['dsgaBootstrap']['ready'] is False,'must remain held')
 must(spec['guest']['cpus']=={'min':2,'use':2,'max':2},'guest CPU changed')
 must(spec['guest']['memorySlots']=={'min':7,'use':7,'max':8},'guest geometry changed')
 must('extraNetwork' not in spec,'primary-only changed')
 lint=['helm','lint',str(repo/'charts/neon-compute'),'-f',str(out/'trusted-cap.json')]
 p=subprocess.run(lint,capture_output=True,text=True);(out/'lint.log').write_text(p.stdout+p.stderr);must(p.returncode==0,'lint failed')
 result={'status':'PASS_PG17_RUNNER_HARD_LIMIT_RENDER_CONTRACT','cases':receipts,'lint_argv':lint,'lint_exit':p.returncode,'legacy_AST_unchanged':True,'trusted_explicit_cap_CPU4_memory10Gi':True,'held_and_primary_and_guest_geometry_preserved':True,'cluster_write_performed':False,'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'seconds':time.monotonic()-started}
 (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'cases':len(cases),'seconds':result['seconds'],'result':str(out/'result.json')}))
if __name__=='__main__':main()
