#!/usr/bin/env python3
"""从已提交源码和明确的Linux工具组装可核对的标准站点包，不收集运行凭据。"""
import argparse,gzip,hashlib,io,json,pathlib,shutil,subprocess,tarfile
p=argparse.ArgumentParser();p.add_argument('--control-plane-source',required=True);p.add_argument('--runtime-bin',required=True);p.add_argument('--host-proof',required=True);p.add_argument('--out',required=True);a=p.parse_args();repo=pathlib.Path(__file__).resolve().parents[1];cp=pathlib.Path(a.control_plane_source).resolve();bins=pathlib.Path(a.runtime_bin).resolve();out=pathlib.Path(a.out).resolve()
def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args],timeout=60)
for path in (repo,cp):
 if git(path,'status','--porcelain','--untracked-files=no').strip():raise RuntimeError('Commit source changes before assembling a release bundle')
proof=json.loads(pathlib.Path(a.host_proof).read_text())
if proof['status']!='built-and-tested' or proof['testSkip'] or proof['testFail']:raise RuntimeError('Actual native Host test proof required')
out.mkdir(parents=True);bundle=out/'neon-standard';bundle.mkdir();control=out/'control-source';control.mkdir()
for source,target,paths in [(repo,bundle,['charts','tools','profiles/standard-site','docs/standard','README.md']),(cp,control,['charts/neon-control-plane'])]:
 with tarfile.open(fileobj=io.BytesIO(git(source,'archive','--format=tar','HEAD',*paths))) as t:t.extractall(target,filter='data')
shutil.copytree(control/'charts/neon-control-plane',bundle/'control-plane-chart/neon-control-plane');shutil.rmtree(control);(bundle/'bin').mkdir()
for name in ('helm','node','host-decommission-check'):
 file=bins/name
 if file.is_symlink() or not file.is_file() or file.open('rb').read(4)!=b'\x7fELF':raise RuntimeError('Explicit Linux runtime binaries required')
 shutil.copy2(file,bundle/'bin'/name);(bundle/'bin'/name).chmod(0o555)
for file in (bundle/'profiles/standard-site').rglob('*.json'):
 value=file.read_text()
 if ('-----BEGIN '+'PRIVATE KEY-----') in value or '-----BEGIN CERTIFICATE-----' in value:raise RuntimeError('Runtime credentials or PKI cannot enter reusable profiles')
lock={'helmCommit':git(repo,'rev-parse','HEAD').decode().strip(),'controlPlaneCommit':git(cp,'rev-parse','HEAD').decode().strip(),'autoscalingSDKCommit':proof['sdkSource'],'hostNativeTests':{'pass':proof['testPass'],'fail':proof['testFail'],'skip':proof['testSkip']},'runtimeBinaries':{n:hashlib.sha256((bundle/'bin'/n).read_bytes()).hexdigest() for n in ('helm','node','host-decommission-check')}};(bundle/'standard-source-lock.json').write_text(json.dumps(lock,indent=2)+'\n')
files=sorted(p for p in bundle.rglob('*') if p.is_file());(bundle/'SHA256SUMS').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+str(f.relative_to(bundle))+'\n' for f in files));archive=out/'neon-standard.tgz'
def normalized(info):
 info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0;return info
with archive.open('wb') as file,gzip.GzipFile(filename='',mode='wb',fileobj=file,mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as t:t.add(bundle,arcname='neon-standard',filter=normalized)
result={'status':'bundled','archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,'source':lock};(out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
