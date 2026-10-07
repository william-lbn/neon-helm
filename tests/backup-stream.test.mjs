import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {run,fileDigest,digest} from '../tools/lib.mjs';

function fixture(t) {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'neon-backup-stream-'));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  return path.join(dir,'metadata.partial.private.sql');
}

test('metadata backup above the 32 MiB buffer streams to a private complete file',(t)=>{
  const file=fixture(t);
  const bytes=33*1024*1024+17;
  const result=run(process.execPath,['-e',`process.stdout.write(Buffer.alloc(${bytes},120))`],{stdoutFile:file});
  assert.equal(result.status,0);
  assert.equal(result.stdout,null);
  assert.equal(fs.statSync(file).size,bytes);
  assert.equal(fs.statSync(file).mode&0o777,0o600);
  assert.equal(fileDigest(file),digest(Buffer.alloc(bytes,120)));
});

test('a failed dump retains partial bytes and never returns a successful result',(t)=>{
  const file=fixture(t);
  assert.throws(()=>run(process.execPath,['-e','process.stdout.write("partial");process.exit(7)'],{stdoutFile:file}),/failed with exit 7/);
  assert.equal(fs.readFileSync(file,'utf8'),'partial');
});

test('a stream destination is exclusive and cannot overwrite an earlier attempt',(t)=>{
  const file=fixture(t);
  fs.writeFileSync(file,'original',{mode:0o600});
  assert.throws(()=>run(process.execPath,['-e','process.stdout.write("replacement")'],{stdoutFile:file}),{code:'EEXIST'});
  assert.equal(fs.readFileSync(file,'utf8'),'original');
});
