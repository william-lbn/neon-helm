#!/usr/bin/env python3
"""Scheduler hostname定向离线渲染；不连接集群、不apply、不修改镜像。"""
import argparse,copy,hashlib,io,json,pathlib,subprocess,tarfile,time
import yaml
BASELINE="552f6b8e33997f424e87573391b3f1892d68771a"
VALUES={"experimentalAcknowledged":True,"images":{"scheduler":"127.0.0.1:5001/neon-candidate/autoscale-scheduler@sha256:8580f0c4c06a3099c3323fed674aa87c222b59abe5e262e7d3e8e05193336619","agent":"127.0.0.1:5001/neon-candidate/autoscaler-agent@sha256:e8e6d1ba2619bf5055b7ce84d4409b5e4f497c26a0c704cdac9f326a3e8c6f18"}}
def check(ok,message):
    if not ok: raise AssertionError(message)
def objects(path):
    docs=[x for x in yaml.safe_load_all(path.read_text()) if x]
    obj={(x["kind"],x["metadata"].get("namespace",""),x["metadata"]["name"]):x for x in docs}
    check(len(obj)==len(docs),"duplicate object")
    return obj
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[3])
    p.add_argument("--output",type=pathlib.Path,required=True,help="新的唯一归档目录，不覆盖历史")
    a=p.parse_args();repo=a.repo.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    # 固定已提交旧chart，所有fixture在本文件内；无需/data旧日志或网络。
    blob=subprocess.check_output(["git","-C",str(repo),"archive",BASELINE,"charts/neon-autoscaler"])
    baseline=out/"baseline";baseline.mkdir()
    with tarfile.open(fileobj=io.BytesIO(blob),mode="r:") as tf:
        for m in tf.getmembers(): check(not m.name.startswith("/") and ".." not in pathlib.PurePosixPath(m.name).parts,"unsafe archive path")
        tf.extractall(baseline)
    pinned=copy.deepcopy(VALUES);pinned["scheduler"]={"nodeSelector":{"kubernetes.io/hostname":"worker-118"}}
    cases=[("default-before",baseline,VALUES,None),("default-after",repo,VALUES,None),("scheduler-118",repo,pinned,None)]
    for name,selector,error in [("reject-116",{"kubernetes.io/hostname":"ubuntu"},"must be one of"),("reject-arch-override",{"kubernetes.io/arch":"arm64"},"Additional property kubernetes.io/arch"),("reject-pool-override",{"neon.tech/pg17-memory-pool":"other"},"Additional property neon.tech/pg17-memory-pool")]:
        values=copy.deepcopy(VALUES);values["scheduler"]={"nodeSelector":selector};cases.append((name,repo,values,error))
    receipt={"baseline_commit":BASELINE,"cases":[],"cluster_apply_performed":False}
    for name,root,values,error in cases:
        f=out/(name+"-values.json");f.write_text(json.dumps(values,indent=2)+"\n")
        cmd=["helm","template","scheduler-placement",str(root/"charts/neon-autoscaler"),"--namespace","default","--kube-version","1.31.2","-f",str(f)]
        r=subprocess.run(cmd,capture_output=True,text=True);(out/(name+".yaml")).write_text(r.stdout);(out/(name+".stderr")).write_text(r.stderr)
        check((r.returncode==0)==(error is None),name+": unexpected exit")
        if error: check(error in r.stderr,name+": failed for unrelated reason")
        receipt["cases"].append({"name":name,"command":cmd,"exit":r.returncode,"expected_success":error is None})
    before=objects(out/"default-before.yaml");after=objects(out/"default-after.yaml");check(before==after,"default full AST changed")
    pinned=objects(out/"scheduler-118.yaml");key=("Deployment","kube-system","autoscale-scheduler")
    old=after[key]["spec"]["template"]["spec"];new=pinned[key]["spec"]["template"]["spec"]
    check(new["nodeSelector"]==dict(old["nodeSelector"],**{"kubernetes.io/hostname":"worker-118"}),"scheduler weakened selector")
    check(new["affinity"]==old["affinity"],"scheduler affinity changed")
    # 去掉本次唯一期望差异后逐对象完整比较，确保Agent/其它配置保持。
    del pinned[key]["spec"]["template"]["spec"]["nodeSelector"]["kubernetes.io/hostname"]
    check(pinned==after,"unrelated object changed")
    cmd=["helm","lint",str(repo/"charts/neon-autoscaler"),"--strict","-f",str(out/"scheduler-118-values.json")]
    r=subprocess.run(cmd,capture_output=True,text=True);(out/"lint.stdout").write_text(r.stdout);(out/"lint.stderr").write_text(r.stderr);check(r.returncode==0,"lint failed")
    receipt.update(status="PASS_SCHEDULER_HOSTNAME_FOCUSED_RENDER",render_commands=len(cases),lint_command=cmd,lint_exit=r.returncode,default_old_AST_equal=True,only_added_scheduler118_hostname=True,Agent_and_pool_os_arch_affinity_unchanged=True,script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),seconds=time.monotonic()-start)
    f=out/"result.json";f.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n");print(json.dumps({"status":receipt["status"],"result":str(f),"sha256":hashlib.sha256(f.read_bytes()).hexdigest(),"seconds":receipt["seconds"]}))
if __name__=="__main__": main()
