import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {root, documents, helm, merge} from '../tools/lib.mjs';
import {ciValues} from '../tools/ci-values.mjs';

for (const [name, override] of [['profile', {}], ['operator-resource-policy', {resources: {requests: {cpu: '100m', memory: '128Mi'}, limits: {memory: '768Mi'}}}]]) {
  test('managed Pageserver init obeys ' + name + ' without changing storage identity', () => {
    const defaults = documents(fs.readFileSync(path.join(root, 'charts/neon-managed-pageserver/values.yaml'), 'utf8'))[0];
    const values = merge(merge(defaults, ciValues('neon-managed-pageserver')), override);
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-pageserver-limits-'));
    const file = path.join(dir, 'values.json');
    fs.writeFileSync(file, JSON.stringify(values));
    const output = helm(['template', 'managed-pageserver', 'charts/neon-managed-pageserver', '-n', 'neon', '--kube-version', '1.36.6', '-f', file]).stdout;
    const deployment = documents(output).find(object => object.kind === 'Deployment' && object.metadata.name === 'pageserver-managed');
    const pod = deployment.spec.template.spec;
    assert.deepEqual(pod.initContainers[0].resources, values.resources);
    assert.deepEqual(pod.containers[0].resources, values.resources);
    assert.equal(pod.initContainers[0].image, values.initImage);
    assert.equal(pod.containers[0].image, values.image);
    assert.equal(pod.volumes.find(volume => volume.name === 'data').persistentVolumeClaim.claimName, values.existingClaim);
    assert.equal(pod.volumes.find(volume => volume.name === 'config').configMap.name, values.configMap);
    assert.equal(deployment.spec.strategy.type, 'Recreate');
  });
}
