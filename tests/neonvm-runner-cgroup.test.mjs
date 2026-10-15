import test from 'node:test';
import assert from 'node:assert/strict';
import {helm,documents} from '../tools/lib.mjs';

test('runner cgroup opt-in is typed, explicit and preserves the legacy default',()=>{
  const base=['template','neonvm','charts/neonvm','-f','profiles/lab/neonvm.json','-n','default','--kube-version','1.31.4'];
  function command(extra=[]){
    const values=documents(helm([...base,...extra]).stdout);
    const deployment=values.find(v=>v.kind==='Deployment'&&v.metadata.name==='neonvm-controller');
    assert(deployment,'Controller required');
    return deployment.spec.template.spec.containers.flatMap(c=>[...(c.command||[]),...(c.args||[])]);
  }
  assert(command().includes('--disable-runner-cgroup'));
  assert(!command(['--set','controller.runnerCgroupEnabled=true']).includes('--disable-runner-cgroup'));
  const invalid=helm([...base,'--set-string','controller.runnerCgroupEnabled=true'],{allowFailure:true});
  assert.notEqual(invalid.status,0);assert.match(invalid.stderr,/runnerCgroupEnabled/);
});
