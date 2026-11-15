import assert from 'node:assert/strict';
import {test} from 'node:test';
import {diskHeadroom, plannedDiskBytes} from '../tools/stack-disk.mjs';

const sample = {
  node: {
    nodeName: 'worker-117',
    fs: {capacityBytes: 52_518_420_480, availableBytes: 8_093_463_808, inodes: 100, inodesFree: 14},
    runtime: {imageFs: {capacityBytes: 52_518_420_480, availableBytes: 8_093_463_808}},
  },
};

test('shared nodefs and imagefs preserve each eviction margin without double counting the planned deployment', () => {
  const config = {
    evictionHard: {'nodefs.available': '5%', 'imagefs.available': '5%'},
    evictionMinimumReclaim: {'nodefs.available': '10%', 'imagefs.available': '10%'},
  };
  const planned = plannedDiskBytes('536870912');
  const [node, images] = diskHeadroom('worker-117', sample, config, planned);
  assert.equal(node.hard, 2_625_921_024);
  assert.equal(node.reclaim, 5_251_842_048);
  assert.equal(node.headroom, -321_170_176);
  assert.equal(images.headroom, node.headroom);
});

test('soft and inode thresholds use the actual available units from the correct filesystem', () => {
  const config = {
    evictionHard: {'nodefs.available': '500M', 'nodefs.inodesFree': '5%'},
    evictionSoft: {'nodefs.available': '1Gi', 'imagefs.available': '1e8'},
    evictionMinimumReclaim: {'nodefs.available': '250Mi', 'nodefs.inodesFree': '10%'},
  };
  const [node, inodes, images] = diskHeadroom('worker-117', sample, config, 0);
  assert.equal(node.headroom, 8_093_463_808 - 1_073_741_824 - 262_144_000);
  assert.equal(inodes.headroom, -1);
  assert.equal(images.headroom, 8_093_463_808 - 100_000_000);
});

test('missing or malformed deployment inputs fail before any stack mutation', () => {
  assert.throws(() => diskHeadroom('worker-119', sample, {}, 0), /configuration is unavailable/);
  assert.throws(() => diskHeadroom('worker-117', {node: {...sample.node, runtime: {}}}, {}, 0), /imagefs.available is unavailable/);
  assert.throws(() => diskHeadroom('worker-117', sample, {evictionHard: {'nodefs.available': 'large'}}, 0), /Invalid Kubelet/);
  assert.equal(plannedDiskBytes(), 0);
  assert.throws(() => plannedDiskBytes('2Gi'), /integer byte count/);
  assert.throws(() => plannedDiskBytes('9007199254740993'), /integer byte count/);
});
