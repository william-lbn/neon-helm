import test from 'node:test';
import assert from 'node:assert/strict';
import {resourceResult} from '../tools/lib.mjs';

test('maintenance preflight can inspect a cluster after the last VM is retired', () => {
  assert.deepEqual(resourceResult('\n', null).items, []);
  assert.equal(resourceResult('', 'vm-neon-compute'), null);
  assert.deepEqual(resourceResult('{"items":[]}', null).items, []);
  assert.throws(() => resourceResult('invalid API output', null), SyntaxError);
});
