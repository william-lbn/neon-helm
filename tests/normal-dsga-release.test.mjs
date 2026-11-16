import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {validateManifest, releaseOverlays, expectedImages, imageReference} from '../tools/package-dsga-release.mjs';
import {root, merge, documents} from '../tools/lib.mjs';
import {ciValues} from '../tools/ci-values.mjs';

// 此fixture由Neon的独立消费合同生成并通过其正控；没有调用registry或K8s。
const fixture = () => JSON.parse(fs.readFileSync(new URL('./fixtures/normal-dsga-manifest.json', import.meta.url), 'utf8'));
const validate = value => validateManifest(value, {releaseVersion: fixture().version, helmSha: fixture().source_lock.helm_commit});
const proof = (m, pg = 'v18') => m.images[`vm-compute-node-${pg}`].guest_disk.normal_guest;
function mutate(m, name, change) {
  const p = proof(m), receipt = JSON.parse(p.assembly_json);
  if (name === 'receipt') change(receipt);
  else {
    const doc = JSON.parse(p.documents[name]); change(doc);
    p.documents[name] = JSON.stringify(doc);
    receipt.files_sha256[name] = createHash('sha256').update(p.documents[name]).digest('hex');
  }
  p.assembly_json = JSON.stringify(receipt);
}

test('Neon-produced schema 3 pair is independently consumed without granting qualification', () => {
  const m = fixture(); assert.equal(validate(m), m);
  assert.equal(Object.keys(m.images).length, expectedImages(true, true).length);
  assert.equal(m.qualification.production_ready, false);
  assert.equal(m.qualification.physical_memory_release_qualified, false);
  assert.notEqual(m.postgres_native_validation.v18.postgres_binary_sha256, m.images['compute-node-v18'].postgres_elf_sha256);
});

const failures = [
  ['half normal pair', m => {m.vm_system_modes.v18 = 'legacy';}],
  ['unbound old PG mode', m => {m.vm_system_modes.v16 = 'normal-split-v3';}],
  ['missing normal base', m => {delete m.images['normal-guest-base-v17'];}],
  ['missing original readback', m => {delete proof(m).documents['normal-readback.json'];}],
  ['changed original bytes', m => {proof(m).documents['normal-readback.json'] += ' ';}],
  ['archive digest drift', m => {proof(m).archive_sha256 = 'f'.repeat(64);}],
  ['duplicate embedded JSON', m => {proof(m).assembly_json = proof(m).assembly_json.replace('"kind":', '"kind":"duplicate","kind":');}],
  ['prior attempt', m => mutate(m, 'receipt', d => {d.execution.run_attempt = '1';})],
  ['wrong Neon build', m => mutate(m, 'receipt', d => {d.compute_source = 'e'.repeat(40);})],
  ['wrong Auto build', m => mutate(m, 'receipt', d => {d.guest_autoscaling_source = 'e'.repeat(40);})],
  ['wrong PG source', m => mutate(m, 'receipt', d => {d.postgres_source = 'e'.repeat(40);})],
  ['wrong verification source', m => {m.verification_commit = 'e'.repeat(40);}],
  ['missing input run identity', m => {delete m.images['normal-guest-base-v18'].execution;}],
  ['missing independent PG ELF', m => {delete m.images['compute-node-v18'].postgres_elf_sha256;}],
  ['wrong independent PG source', m => {m.images['compute-node-v18'].postgres_source = 'f'.repeat(40);}],
  ['missing original Builder ELF', m => {delete m.images['vm-builder'].builder_sha256;}],
  ['missing original runtime ELF', m => {delete m.images['neonvm-daemon'].runtime_elf_sha256;}],
  ...['compute_ctl', 'neonvmd', 'dsga_resource_guard'].map(name => [`changed final ${name}`, m => mutate(m, 'normal-readback.json', d => {d.root.runtime_elf_sha256[name] = 'f'.repeat(64);})]),
  ['System digest drift', m => mutate(m, 'receipt', d => {d.system_manifest_sha256 = 'e'.repeat(64);})],
  ['NativeBirth proof omitted', m => mutate(m, 'normal-readback.json', d => {delete d.root.native_birth_manifest_sha256;})],
  ['plan drift', m => mutate(m, 'normal-readback.json', d => {d.root.build_plan_sha256 = 'e'.repeat(64);})],
  ['package drift', m => mutate(m, 'ordinary-input-readback.json', d => {d.package_lock_sha256 = 'e'.repeat(64);})],
  ['base drift', m => mutate(m, 'assembly-inputs.json', d => {d.base_image = d.kernel_image;})],
  ['final disk removed', m => mutate(m, 'normal-readback.json', d => {d.oci.assets['disk.qcow2'].push({layer_digest: 'sha256:' + 'e'.repeat(64), material: null});})],
  ['missing actual normal kernel', m => {delete m.autoscaling_capabilities.normal_kernel;}],
  ['boot kernel differs', m => {m.autoscaling_capabilities.normal_kernel.artifact_sha256 = 'f'.repeat(64);}],
  ['normal kernel source differs', m => {m.images['vm-kernel-normal'].source_commit = m.neon_commit;}],
  ['missing second native gate', m => {delete m.postgres_native_validation.v18;}],
  ['native gate wrong attempt', m => {m.postgres_native_validation.v18.run_attempt = '1';}],
  ['normal does not grant production', m => {m.qualification.production_ready = true;}],
  ['normal does not grant physical return', m => {m.qualification.physical_memory_release_qualified = true;}],
  ['capability cannot grant normal qualification', m => {m.autoscaling_capabilities.normal_kernel.normal_qualification = true;}],
  ['schema downgrade cannot hide normal evidence', m => {m.schema_version = 2; m.vm_system_mode = 'legacy';}],
];
for (const [name, change] of failures) test(`schema 3 rejects ${name}`, () => {
  const m = fixture(); change(m); assert.throws(() => validate(m));
});

test('normal overlays retain all creation/qualification gates and no invented instance identity', () => {
  const m = validate(fixture());
  for (const pg of [17, 18]) {
    const overlays = releaseOverlays(m, pg), compute = overlays['neon-compute'];
    assert.equal(compute.experimentalAcknowledged, false);
    assert.equal(compute.compute.enabled, false);
    assert.equal(compute.compute.startupMode, 'trusted-runtime-v1');
    assert.equal(compute.compute.image, imageReference(m, `vm-compute-node-v${pg}`));
    assert.equal(compute.compute.runtime.kernelImage, imageReference(m, 'vm-kernel-normal'));
    assert.equal(compute.compute.runtime.incarnation, undefined);
    assert.equal(compute.compute.runtime.computeInstanceId, undefined);
    assert.equal(compute.compute.runtime.podResources, undefined);
    assert.equal(overlays['neon-control-plane'].api.creationEnabled, false);
    assert.equal(overlays['neon-core'].compute.enabled, false);
    assert.equal(overlays['neon-autoscaler'].dsga.enabled, false);
    assert.equal(overlays['dsga-platform-qualifier'].enabled, false);
  }
});

test('real Helm renders disabled normal overlays but rejects activation without original identity/budget', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'normal-release-render-'));
  try {
    const m = fixture();
    for (const pg of [17, 18]) {
      const base = merge(ciValues('neon-compute'), releaseOverlays(m, pg)['neon-compute']);
      Object.assign(base.compute, {tenantId: '1'.repeat(32), timelineId: '2'.repeat(32)});
      const render = values => {
        const file = path.join(directory, `pg${pg}.json`); fs.writeFileSync(file, JSON.stringify(values));
        return spawnSync(process.env.HELM_BIN || 'helm', ['template', 'offline-normal', path.join(root, 'charts/neon-compute'), '-f', file, '-n', 'neon', '--kube-version', '1.31.2'], {encoding: 'utf8'});
      };
      assert.notEqual(render(base).status, 0, 'The explicit experimental acknowledgment must remain required');
      base.experimentalAcknowledged = true; // 仅本地渲染fixture的人工确认，不写入发行overlay。
      const disabled = render(base);
      assert.equal(disabled.status, 0, disabled.stderr || disabled.error?.message);
      assert.ok(!documents(disabled.stdout).some(doc => ['VirtualMachine', 'Secret'].includes(doc.kind)));
      const enabled = merge(base, {compute: {enabled: true}});
      assert.notEqual(render(enabled).status, 0, 'No per-instance Pod budget was supplied');
      const budgetOnly = merge(enabled, {compute: {runtime: {podResources: {limits: {cpu: '2', memory: '10Gi'}}}}});
      const missingIdentity = render(budgetOnly);
      assert.notEqual(missingIdentity.status, 0);
      assert.match(missingIdentity.stderr, /original cp-Endpoint|instance identity/);
    }
  } finally {fs.rmSync(directory, {recursive: true, force: true});}
});
