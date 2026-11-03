#!/usr/bin/env python3
"""既有Agent full-control UDS定向render；无集群访问，无资格/Lease创建。"""
import argparse,copy,hashlib,io,json,pathlib,subprocess,tarfile,time
import yaml
BASELINE="0820655a100ed648a6bf7fd151813b242f003c6f"
def require(ok,message):
 if not ok:raise AssertionError(message)
def objects(path):
 docs=[x for x in yaml.safe_load_all(path.read_text()) if x];data={(x["kind"],x["metadata"].get("namespace",""),x["metadata"]["name"]):x for x in docs};require(len(data)==len(docs),"duplicate resource");return data
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--output",type=pathlib.Path,required=True);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);chart=pathlib.Path(__file__).resolve().parents[1];repo=chart.parents[1];start=time.monotonic()
 archive=subprocess.check_output(["git","-C",str(repo),"archive",BASELINE,"charts/neon-autoscaler"]);baseline=out/"baseline";baseline.mkdir()
 with tarfile.open(fileobj=io.BytesIO(archive))as tf:
  for x in tf.getmembers():require(not x.name.startswith("/") and ".." not in pathlib.PurePosixPath(x.name).parts,"unsafe baseline path")
  tf.extractall(baseline)
 old=baseline/"charts/neon-autoscaler";image="render.invalid/component@sha256:"+"a"*64;off={"experimentalAcknowledged":True,"images":{"agent":image,"scheduler":image}};on=copy.deepcopy(off)
 # 仅复用原pod-protection-rbac.py的渲染fixture形状；这些LeaseUID不是实际来源，不发API。
 nodes=json.loads((chart/"files/pg17-node-identities.json").read_text())["allowedNodeUIDs"];profile={"id":"render-only-budget","scheduler_name":"autoscale-scheduler","vm_overhead_bytes":str(3<<30),"pod_overhead_bytes":str(16<<20)};sha=hashlib.sha256(json.dumps(profile,separators=(",",":")).encode()).hexdigest();rows=[]
 for i,(name,uid)in enumerate(nodes.items()):
  system=str((8 if name=="worker-118" else 4)<<30);rows.append({"binding":{"node_name":name,"node_uid":uid,"namespace":"neon","lease_name":"render-only-host-"+name,"lease_uid":"00000000-0000-0000-0000-"+str(i+1).zfill(12)},"profile":profile,"system_bytes":system,"kubernetes_budget":{"protocol_version":1,"scope":"kubernetes-node-memory-budget-v1","node_name":name,"node_uid":uid,"capacity_bytes":str(24<<30),"allocatable_bytes":str(24<<30),"system_reservation_bytes":system,"profile_sha256":sha}})
 read={"enabled":True,"hostDirectory":"/run/neon-dsga-pg17-resource","mountDirectory":"/run/neon-dsga-pg17-resource","name":"resource.sock"};full={"enabled":True,"hostDirectory":"/run/neon-dsga-pg17-control","mountDirectory":"/run/neon-dsga-pg17-control","name":"control.sock"}
 on["dsga"]={"enabled":True,"agent":{"gatewayURL":"https://render.invalid:8444","managementCASecret":"render-only-public-ca","resourceReadSocket":read},"scheduler":{"nodes":rows,"podProtectionNamespaces":["kube-system","neon-cert-manager","neonvm-system"]}}
 enabled=copy.deepcopy(on);enabled["dsga"]["agent"]["controlSocket"]=full
 cases=[("default-before",old,off,None),("default-after",chart,off,None),("reader-before",old,on,None),("reader-after",chart,on,None),("full-control",chart,enabled,None)]
 def bad(name,path,value,reason):
  f=copy.deepcopy(enabled);target=f
  for key in path[:-1]:target=target[key]
  target[path[-1]]=value;cases.append((name,chart,f,reason))
 disabled=copy.deepcopy(enabled);disabled["dsga"]["enabled"]=False;disabled["dsga"]["agent"]["resourceReadSocket"]["enabled"]=False;cases.append(("reject-dsga-off",chart,disabled,"full control socket requires DSGA enabled"))
 bad("reject-dangerous-path",["dsga","agent","controlSocket","hostDirectory"],"/etc","canonical private")
 bad("reject-traversal",["dsga","agent","controlSocket","mountDirectory"],"/run/neon-dsga-a/../b","canonical private")
 bad("reject-host-collision",["dsga","agent","controlSocket","hostDirectory"],read["hostDirectory"],"separate and non-overlapping")
 bad("reject-mount-collision",["dsga","agent","controlSocket","mountDirectory"],read["mountDirectory"],"separate and non-overlapping")
 bad("reject-ancestor-collision",["dsga","agent","resourceReadSocket","hostDirectory"],full["hostDirectory"]+"/reader","separate and non-overlapping")
 bad("reject-socket-path",["dsga","agent","controlSocket","name"],"../control.sock","short original socket filename")
 bad("reject-boolean-string",["dsga","agent","controlSocket","enabled"],"true","Expected: boolean")
 results=[]
 for name,root,values,reason in cases:
  vf=out/(name+".json");vf.write_text(json.dumps(values,indent=2)+"\n");cmd=["helm","template","control-uds-contract",str(root),"-n","default","--kube-version","1.31.2","-f",str(vf)];r=subprocess.run(cmd,capture_output=True,text=True);(out/(name+".yaml")).write_text(r.stdout);(out/(name+".stderr")).write_text(r.stderr);require((r.returncode==0)==(reason is None),name+": "+r.stderr)
  if reason:require(reason in r.stderr,name+": unrelated failure")
  results.append({"case":name,"argv":cmd,"exit":r.returncode,"expected_error":reason})
 require(objects(out/"default-before.yaml")==objects(out/"default-after.yaml"),"default off AST changed");before=objects(out/"reader-before.yaml");after=objects(out/"reader-after.yaml");require(before==after,"enabled reader/full-off AST changed")
 actual=objects(out/"full-control.yaml");cmkey=("ConfigMap","kube-system","autoscaler-agent-config");conf=json.loads(actual[cmkey]["data"]["config.json"]);oldconf=json.loads(after[cmkey]["data"]["config.json"]);require(conf["dsga"]["controlSocketPath"]=="/run/neon-dsga-pg17-control/control.sock","full socket config mismatch");require(conf["dsga"]["resourceReadSocketPath"]==oldconf["dsga"]["resourceReadSocketPath"],"reader changed");del conf["dsga"]["controlSocketPath"];require(conf==oldconf,"other config changed");actual[cmkey]["data"]=copy.deepcopy(after[cmkey]["data"])
 dskey=("DaemonSet","kube-system","autoscaler-agent");pod=actual[dskey]["spec"]["template"]["spec"];oldpod=after[dskey]["spec"]["template"]["spec"];vol=next(x for x in pod["volumes"]if x["name"]=="dsga-owner-control");require(vol=={"name":"dsga-owner-control","hostPath":{"path":full["hostDirectory"],"type":"Directory"}},"unexpected hostPath");pod["volumes"].remove(vol);mount=next(x for x in pod["containers"][0]["volumeMounts"]if x["name"]=="dsga-owner-control");require(mount=={"name":"dsga-owner-control","mountPath":full["mountDirectory"]},"unexpected mount");pod["containers"][0]["volumeMounts"].remove(mount)
 a=actual[dskey]["spec"]["template"]["metadata"].get("annotations",{});b=after[dskey]["spec"]["template"]["metadata"].get("annotations",{});require(set(a)==set(b),"annotation keys changed");require(all(k=="checksum/runtime-config" for k in a if a[k]!=b[k]),"unrelated annotation changed");actual[dskey]["spec"]["template"]["metadata"]["annotations"]=copy.deepcopy(b);require(actual==after,"unrelated resource/selector/RBAC changed")
 cmd=["helm","lint",str(chart),"--strict","-f",str(out/"full-control.json")];r=subprocess.run(cmd,capture_output=True,text=True);(out/"lint.stdout").write_text(r.stdout);(out/"lint.stderr").write_text(r.stderr);require(r.returncode==0,"lint failed: "+r.stdout+r.stderr)
 result={"status":"PASS_FULL_CONTROL_UDS_FOCUSED_RENDER","baseline_commit":BASELINE,"cases":results,"render_commands":len(cases),"lint_exit":r.returncode,"default_off_AST_equal":True,"DSGA_reader_enabled_full_off_AST_equal":True,"enabled_only_adds_control_path_volume_mount_and_checksum":True,"reader_api_and_path_unchanged":True,"no_new_RBAC_network_or_Node_changes":True,"render_fixture_only_not_real_Lease_or_qualification":True,"cluster_write_performed":False,"script_sha256":hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),"seconds":time.monotonic()-start};(out/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"status":result["status"],"commands":len(cases),"result":str(out/"result.json"),"seconds":result["seconds"]}))
if __name__=="__main__":main()
