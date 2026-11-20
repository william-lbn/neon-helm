import assert from 'node:assert/strict';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';

const root=path.resolve(import.meta.dirname,'..');
function plan(until) {
  const args=['tools/stack.mjs','plan'];
  if(until)args.push('--until',until);
  return spawnSync(process.execPath,args,{cwd:root,encoding:'utf8'});
}
function releases(result) {
  assert.equal(result.status,0,result.stderr);
  return JSON.parse(result.stdout).steps.map(step=>step.release);
}

test('stack plan includes the complete ordered stack by default',()=>{
  const actual=releases(plan());
  assert.equal(actual.at(-1),'neon-control-plane');
  assert.equal(actual.length,8);
});

test('stack plan stops inclusively by release name',()=>{
  const actual=releases(plan('neon-lab'));
  assert.equal(actual.at(-1),'neon-lab');
  assert(!actual.includes('managed-pageserver'));
});

test('stack plan stops inclusively by chart name',()=>{
  const actual=releases(plan('neon-core'));
  assert.equal(actual.at(-1),'neon-lab');
  assert(!actual.includes('managed-pageserver'));
});

test('data-plane cutoff includes gateway and excludes control plane',()=>{
  const actual=releases(plan('neon-compute-management-gateway'));
  assert.equal(actual.at(-1),'neon-compute-management-gateway');
  assert(!actual.includes('neon-control-plane'));
});

test('unknown cutoff is rejected before any deployment action',()=>{
  const result=plan('missing-release');
  assert.notEqual(result.status,0);
  assert.match(result.stderr,/Unknown --until release\/chart: missing-release/);
});
