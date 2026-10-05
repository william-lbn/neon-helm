import test from 'node:test';
import assert from 'node:assert/strict';
import {validatePlan,readJSON,merge,compatibleAdoption,documents} from '../tools/lib.mjs';
test('dependency ordering rejects a forward dependency',()=>{
  const plan=readJSON('stack/stack.json');plan.steps[0].dependsOn=['neon-control-plane'];
  assert.throws(()=>validatePlan(plan),/Dependency/);
});
test('private overrides replace arrays without mutating locked source',()=>{
  const base={nested:{items:[1],keep:true}};
  assert.deepEqual(merge(base,{nested:{items:[2]}}),{nested:{items:[2],keep:true}});
  assert.deepEqual(base.nested.items,[1]);
});
test('adoption protects Helm ownership and unlisted resources',()=>{
  assert.throws(()=>compatibleAdoption({kind:'Deployment',metadata:{name:'another-app'}},{metadata:{annotations:{}}}),/allowlist/);
  assert.throws(()=>compatibleAdoption({kind:'Secret',metadata:{name:'neon-control-v2-db'}},{metadata:{}}),/Never/);
  assert.throws(()=>compatibleAdoption({kind:'Deployment',metadata:{name:'neon-control-adapter'}},{metadata:{annotations:{'meta.helm.sh/release-name':'other'}}}),/steal/);
});
test('adoption requires bound PVC and exact capacity',()=>{
  const obj={kind:'PersistentVolumeClaim',metadata:{name:'pageserver-managed-cache'},spec:{accessModes:['ReadWriteOnce'],resources:{requests:{storage:'10Gi'}}}};
  const current=structuredClone(obj);current.status={phase:'Bound'};
  assert.equal(compatibleAdoption(obj,current),true);
  current.spec.resources.requests.storage='5Gi';assert.throws(()=>compatibleAdoption(obj,current),/size/);
});
test('YAML duplicates fail instead of silently overriding fields',()=>assert.throws(()=>documents('a: 1\na: 2\n'),/YAML/));
