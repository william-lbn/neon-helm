import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readJSON,validateControlImagesLock} from '../tools/lib.mjs';
const lock=readJSON(readJSON('stack/stack.json').controlImagesLock);
const references=Object.fromEntries(Object.entries(lock.images).map(([name,image])=>[name,image.reference]));
test('current distribution requires one published source revision and seven public image receipts',()=>{
  assert.equal(validateControlImagesLock(lock,references),true);
  const mixed=structuredClone(lock);mixed.images.auth.source_commit='0'.repeat(40);
  assert.throws(()=>validateControlImagesLock(mixed,references),/drift/);
});
test('digest-pinned but wrong-component profile cannot replace the Auth runtime',()=>{
  assert.throws(()=>validateControlImagesLock(lock,{...references,auth:references.api}),/drift/);
});
test('a missing image or private registry result cannot qualify as the whole product',()=>{
  const missing=structuredClone(lock);delete missing.images.auth;
  assert.throws(()=>validateControlImagesLock(missing,references),/distribution/);
  const privateImage=structuredClone(lock);privateImage.images.web.anonymous_pull_verified=false;
  assert.throws(()=>validateControlImagesLock(privateImage,references),/drift/);
});
