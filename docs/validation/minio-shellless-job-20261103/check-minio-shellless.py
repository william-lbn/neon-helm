# 本次实际 shellless mc Job 接线的可重跑定向检查；不访问 Secret 内容。
import json,subprocess,sys
from pathlib import Path
import yaml
chart=Path(sys.argv[1]); values=Path(sys.argv[2])
z=subprocess.run(["helm","lint",str(chart),"--strict","-f",str(values)],capture_output=True); assert z.returncode==0
z=subprocess.check_output(["helm","template","neon-pg17-core",str(chart),"-n","neon","--kube-version","1.31.2","-f",str(values)])
docs=[x for x in yaml.safe_load_all(z) if x]
j=[x for x in docs if x["kind"]=="Job" and x["metadata"]["name"]=="neon-pg17-core-minio-init"];assert len(j)==1
c=j[0]["spec"]["template"]["spec"]["containers"][0]; e=c["env"]
assert [x["name"] for x in e]==["MINIO_ROOT_USER","MINIO_ROOT_PASSWORD","MC_HOST_local"]
for x,k in zip(e[:2],["accessKey","secretKey"]):assert x["valueFrom"]["secretKeyRef"]=={"name":"neon-object-store","key":k}
assert e[2]["value"]=="http://$(MINIO_ROOT_USER):$(MINIO_ROOT_PASSWORD)@minio:9000"
assert c["command"]==["/usr/bin/mc"]
assert c["args"]==["mb","--ignore-existing","--region","us-east-1","local/neon"]
assert c["resources"]["limits"]["memory"]=="512Mi"
assert j[0]["spec"]["backoffLimit"]==6 and j[0]["spec"]["activeDeadlineSeconds"]==600
assert all("secret" not in str(x).lower() for x in c["args"])
print(json.dumps({"passed":True,"checks":9,"shell_required":False,"credentials_in_argv":False}))
