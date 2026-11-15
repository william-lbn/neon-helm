import assert from 'node:assert/strict';
import {test} from 'node:test';
import {imagePins} from '../tools/dsga-image-pins.mjs';

const ref = (tag, digit) => `neon.local/${tag}@sha256:${digit.repeat(64)}`;
const guest = ref('guest', 'a');
const runner = ref('runner', 'b');
const kernel = ref('kernel', 'c');
const frozenRunner = ref('frozen-runner', 'd');
const qualifier = ref('qualifier', 'e');
const catalog = {protocol_version: 3, releases: [{creation: {
  postgres_version: 17, image: guest, vm: {runner_image: runner, kernel_image: kernel,
    placement: {allowed_node_names: ['worker-117', 'worker-118', 'worker-119']},
    generic_guest: {supply: {qualifier_image: qualifier}}},
  confidential: 'unused-test-marker',
}}]};
const pending = {id: 'op_a1', state: 'failed', image: guest, runner: frozenRunner, kernel, nodes: ['worker-117']};

test('protects future catalog Runner and frozen retry Runner without active Pods', () => {
  const pins = imagePins(catalog, [pending]);
  assert.deepEqual(pins.find(pin => pin.image === runner).origins, [
    {role: 'runner', nodes: ['worker-117', 'worker-118', 'worker-119'], source: 'catalog', postgresMajor: 17},
  ]);
  assert.equal(pins.find(pin => pin.image === qualifier).origins[0].role, 'qualifier');
  assert.deepEqual(pins.find(pin => pin.image === frozenRunner).origins, [
    {role: 'runner', nodes: ['worker-117'], source: 'operation', operation: pending.id, state: 'failed'},
  ]);
  assert.equal(pins.find(pin => pin.image === guest).origins.length, 2);
  assert.ok(!JSON.stringify(pins).includes('unused-test-marker'));
});

test('rejects unavailable catalog, mutable pins and ambiguous node scope', () => {
  assert.throws(() => imagePins(null, []), /incomplete/);
  assert.throws(() => imagePins(catalog, [{...pending, runner: 'neon:latest'}]), /unavailable/);
  assert.throws(() => imagePins(catalog, [{...pending, nodes: ['worker-117', 'worker-117']}]), /unavailable/);
  assert.throws(() => imagePins(catalog, [{...pending, state: 'succeeded'}]), /Operation/);
});
