set -eu
export NEON_ROOT_READER="${NEON_ROOT_READER:-$(dirname "$0")/read-root-resource.py}"
python3 -B - "$@" <<'PY'
import datetime,json,os,pathlib,subprocess,sys,time
os.umask(0o077);socket,uid,outPath,slot= sys.argv[1:5];slot=int(slot);out=pathlib.Path(outPath)
if out.exists():raise SystemExit('Original observer exists; inspect it instead of replaying')
out.mkdir(mode=0o700);baseline=None;peak=0;grew=False;instance=None;deadline=time.monotonic()+1100
report={'status':'observing','vmUID':uid,'readOnly':True}
def save():(out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
save()
while time.monotonic()<deadline:
 result=subprocess.run(['python3','-B',os.environ['NEON_ROOT_READER'],socket,uid],capture_output=True,text=True,timeout=35)
 if result.returncode:
  with (out/'read-errors.private.log').open('a') as file:file.write(result.stderr)
 else:
  view=json.loads(result.stdout);current=int(view['actual']['guest_mem_total_bytes'])
  if instance is None:instance=view['instance']
  if instance!=view['instance']:raise RuntimeError('Original PG/Compute instance changed')
  if baseline is None:baseline=current
  peak=max(peak,current)
  with (out/'root-observations.jsonl').open('a') as file:file.write(json.dumps(view)+'\n')
  report.update(instance=instance,baselineGuestMemTotalBytes=baseline,peakGuestMemTotalBytes=peak,currentGuestMemTotalBytes=current)
  if current>baseline+slot//2:grew=True;report['guestGrowthObserved']=True
  if grew and current<=baseline+slot//8:
   report.update(status='completed',guestGrowthAndShrinkObserved=True,completedAt=datetime.datetime.now(datetime.timezone.utc).isoformat());save();print(json.dumps(report));break
  save()
 time.sleep(5)
else:report.update(status='observation-ended',reason='Read-only deadline reached');save();print(json.dumps(report))
PY
