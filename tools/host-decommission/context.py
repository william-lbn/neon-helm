#!/usr/bin/env python3
"""以显式Autoscaling提交生成Host只读核验工具构建上下文，不修改SDK源码。"""
import argparse,hashlib,json,pathlib,re,shutil,subprocess
p=argparse.ArgumentParser();p.add_argument('--autoscaling-source',required=True);p.add_argument('--sdk-commit',required=True);p.add_argument('--out',required=True);a=p.parse_args();source=pathlib.Path(a.autoscaling_source).resolve();out=pathlib.Path(a.out).resolve()
if not re.fullmatch('[a-f0-9]{40}',a.sdk_commit):raise RuntimeError('Full SDK commit required')
def git(*args):return subprocess.check_output(['git','-C',str(source),*args],text=True).strip()
if git('rev-parse','HEAD')!=a.sdk_commit or git('status','--porcelain','--untracked-files=all'):raise RuntimeError('Clean exact SDK checkout required')
out.mkdir(parents=True);here=pathlib.Path(__file__).resolve().parent
for name in ('go.mod','go.sum'):shutil.copy2(source/name,out/name)
for name in ('pkg','internal','neonvm'):shutil.copytree(source/name,out/name)
tool=out/'tools/host-decommission';tool.mkdir(parents=True)
for name in ('main.go','main_test.go'):shutil.copy2(here/name,tool/name)
shutil.copy2(here/'Dockerfile',out/'Dockerfile');lock={'sdkCommit':a.sdk_commit,'sdkTree':git('rev-parse','HEAD^{tree}'),'toolSHA256':{name:hashlib.sha256((here/name).read_bytes()).hexdigest() for name in ('main.go','main_test.go','Dockerfile')}};(out/'source-lock.json').write_text(json.dumps(lock,indent=2)+'\n');print(json.dumps({'status':'context-created','out':str(out),'source':lock}))
