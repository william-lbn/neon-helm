import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fixtureManifest} from './fixtures/dsga-manifest.mjs';
import {validateManifest, releaseOverlays, parseManifest, expectedImages, imageReference} from '../tools/package-dsga-release.mjs';
import {root, merge, documents, readJSON} from '../tools/lib.mjs';

function validate(value) {
  return validateManifest(value, {releaseVersion: fixtureManifest().version, helmSha: fixtureManifest().source_lock.helm_commit});
}
test('complete candidate locks all four repositories and 49 image records', () => {
  const manifest = fixtureManifest();
  assert.equal(validate(manifest), manifest);
  assert.equal(expectedImages().length, 49);
  assert.equal(manifest.images['neon-test-extensions-v18'], undefined);
});

const invalidCases = [
  ['missing digest', m => { delete m.images['neonvm-runner'].digest; }, /digest/],
  ['tag used as digest', m => { m.images.pageserver.digest = 'latest'; }, /digest/],
  ['wrong source revision', m => { m.images.pageserver.source_commit = m.source_lock.autoscaling_commit; }, /source mismatch/],
  ['wrong source repository', m => { m.images.pageserver.source_repository = 'another-owner/neon'; }, /source mismatch/],
  ['autoscaling built from Neon source', m => { m.images['neonvm-runner'].source_commit = m.neon_commit; }, /source mismatch/],
  ['Helm SHA is from another checkout', m => { m.source_lock.helm_commit = m.neon_commit; }, /Helm source/],
  ['Helm repository substitution', m => { m.source_lock.helm_repository = 'another-owner/neon-helm'; }, /Helm source/],
  ['mutable PG ref', m => { m.source_lock.postgres.v18 = 'codex/pg18'; }, /full source SHAs/],
  ['missing PG18 source', m => { delete m.source_lock.postgres.v18; }, /PostgreSQL majors/],
  ['missing qualifier image', m => { delete m.images['dsga-platform-qualifier']; }, /image inventory/],
  ['omitted core inventory cannot hide a missing image', m => { m.source_lock.core_binaries = ['pageserver']; }, /Core binary inventory/],
  ['extra source inventory', m => { m.source_lock.autoscaling_images.push('foreign-image'); }, /Autoscaling image inventory/],
  ['PG18 cannot claim all extensions', m => { m.source_lock.postgres_profiles.v18 = 'full'; }, /PG18 is dsga-core/],
  ['extra PG18 extensions record', m => { m.images['neon-test-extensions-v18'] = structuredClone(m.images['neon-test-extensions-v17']); }, /image inventory/],
  ['component image substitution', m => { m.images.pageserver.image = m.images.safekeeper.image; }, /Wrong component/],
  ['record name mismatch', m => { m.images.pageserver.name = 'safekeeper'; }, /image identity/],
  ['mixed release versions', m => { m.images.pageserver.image = m.images.pageserver.image.replace(/\.1\.amd64$/, '.2.amd64'); }, /version/],
  ['Chart version drift', m => { m.chart_version = '0.1.30'; }, /version mismatch/],
  ['mutable latest release version', m => { m.version = 'latest'; }, /version mismatch/],
  ['unsupported schema', m => { m.schema_version = 1; }, /schema_version/],
  ['stable channel contamination', m => { m.channel = 'stable'; }, /channel/],
  ['unqualified arm64 deployment', m => { m.architecture = 'linux/arm64'; }, /amd64 only/],
  ['different registry', m => { m.source_lock.registry = 'example.invalid/mirror'; }, /registry/],
  ['release build grants production', m => { m.qualification.production_ready = true; }, /cannot grant/],
  ['release build grants physical return', m => { m.qualification.physical_memory_release_qualified = true; }, /cannot grant/],
  ['missing qualification statement', m => { delete m.qualification; }, /cannot grant/],
  ['unproved normal VM mode', m => { m.vm_system_mode = 'normal-split'; }, /legacy candidate/],
  ['image architecture contamination', m => { m.images['neonvm-runner'].architecture = 'linux/arm64'; }, /architecture mismatch/],
  ['earlier run attempt reused', m => { m.images['neonvm-runner'].execution.run_attempt = '2'; }, /different run or attempt/],
  ['different CI run reused', m => { m.images['neonvm-runner'].execution.run_id = '987654321'; }, /different run or attempt/],
  ['independently built Autoscaling cannot masquerade as same-run release', m => { m.images['neonvm-runner'].execution.repository = 'william-lbn/autoscaling'; }, /different run or attempt/],
];
for (const [name, change, reason] of invalidCases) {
  test(`distribution rejects ${name}`, () => {
    const manifest = fixtureManifest(); change(manifest);
    assert.throws(() => validate(manifest), reason);
  });
}
test('release version rejects prefixes, paths, leading zeros and mutable channels', () => {
  for (const releaseVersion of ['latest', 'v0.2.0-dsga.123.1.amd64', '../0.2.0', '0.2.0-dsga.01.1.amd64', '0.2.0-dsga.123.1.arm64', '0.2.0']) {
    assert.throws(() => validateManifest(fixtureManifest(), {releaseVersion, helmSha: fixtureManifest().source_lock.helm_commit}), /SemVer/);
  }
});
test('duplicate JSON keys cannot override reviewed source or digest fields', () => {
  assert.throws(() => parseManifest('{"images":{"pageserver":{"digest":"first","digest":"second"}}}'), /duplicate/);
  assert.throws(() => parseManifest('schema_version: 2'), SyntaxError);
  assert.deepEqual(parseManifest('{"schema_version":2}'), {schema_version: 2});
});
test('per-major overlays use the exact digest and preserve runtime gates', () => {
  const m = fixtureManifest();
  for (const pg of [17, 18]) {
    const values = releaseOverlays(m, pg);
    assert.equal(values['neon-compute'].compute.pgVersion, pg);
    assert.equal(values['neon-compute'].compute.image, imageReference(m, `vm-compute-node-v${pg}`));
    assert.equal(values['neon-compute'].compute.enabled, false);
    assert.equal(values['neon-compute'].experimentalAcknowledged, false);
    assert.equal(values['neon-compute'].compute.startupMode, 'legacy');
    assert.equal(values['neon-compute'].compute.runtime.incarnation, undefined);
    assert.equal(values['neon-compute'].compute.runtime.podResources, undefined);
    assert.equal(values['neon-autoscaler'].dsga.enabled, false);
    assert.equal(values['neon-core'].compute.enabled, false);
    assert.equal(values['neon-core'].compute.mode, 'public');
    assert.equal(values['neon-core'].compute.buildProfile, pg === 18 ? 'dsga-core' : 'full');
    assert.equal(values['neon-core'].compute.image.digest, imageReference(m, `compute-node-v${pg}`));
    assert.equal(values['neon-core'].validation.labAcknowledged, false);
    assert.equal(values['dsga-platform-qualifier'].enabled, false);
    assert.equal(values.neonvm.images.runner, imageReference(m, 'neonvm-runner'));
    for (const ref of Object.values(values.neonvm.images)) assert.match(ref, /@sha256:[a-f0-9]{64}$/);
  }
  assert.notEqual(releaseOverlays(m, 17)['neon-compute'].compute.image, releaseOverlays(m, 18)['neon-compute'].compute.image);
});
test('legacy standalone compute uses a full image reference, not a bare sha256', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsga-core-image-'));
  try {
    const manifest = fixtureManifest();
    const values = merge(merge(readJSON('profiles/lab/neon-core.json'), releaseOverlays(manifest, 17)['neon-core']), {
      validation: {labAcknowledged: true},
      compute: {enabled: true, mode: 'wrapper', tenantId: '1'.repeat(32), timelineId: '2'.repeat(32)},
    });
    const file = path.join(dir, 'values.json'); fs.writeFileSync(file, JSON.stringify(values));
    const result = spawnSync(process.env.HELM_BIN || 'helm', ['template', 'offline-core', path.join(root, 'charts/neon-core'), '-f', file, '-n', 'neon', '--kube-version', '1.31.2'], {encoding: 'utf8'});
    assert.equal(result.status, 0, result.stderr || result.error?.message);
    const compute = documents(result.stdout).find(doc => doc.kind === 'Deployment' && doc.metadata.name === 'compute');
    assert.equal(compute.spec.template.spec.containers[0].image, imageReference(manifest, 'compute-node-v17'));
  } finally { fs.rmSync(dir, {recursive: true, force: true}); }
});

function publicComputeValues(manifest, pg, overrides = {}) {
  return merge(merge(readJSON('profiles/lab/neon-core.json'), releaseOverlays(manifest, pg)['neon-core']), {
    validation: {labAcknowledged: true},
    compute: {
      enabled: true, tenantId: '1'.repeat(32), timelineId: '2'.repeat(32),
      configImage: `render.invalid/python@sha256:${'a'.repeat(64)}`, ...overrides,
    },
  });
}
function renderPublicCompute(file) {
  return spawnSync(process.env.HELM_BIN || 'helm', ['template', 'offline-public-compute', path.join(root, 'charts/neon-core'), '-f', file, '-n', 'neon', '--kube-version', '1.31.2'], {encoding: 'utf8'});
}

test('enabled PG18 public Compute preloads only delivered core extensions through the actual init script', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsga-public-config-'));
  try {
    const manifest = fixtureManifest();
    for (const pg of [17, 18]) {
      const valuesFile = path.join(dir, `pg${pg}.json`);
      fs.writeFileSync(valuesFile, JSON.stringify(publicComputeValues(manifest, pg)));
      const rendered = renderPublicCompute(valuesFile);
      assert.equal(rendered.status, 0, rendered.stderr || rendered.error?.message);
      const objects = documents(rendered.stdout);
      const config = objects.find(doc => doc.kind === 'ConfigMap' && doc.metadata.name === 'compute-public-config');
      const pod = objects.find(doc => doc.kind === 'Deployment' && doc.metadata.name === 'compute').spec.template.spec;
      assert.equal(pod.containers[0].image, imageReference(manifest, `compute-node-v${pg}`));
      const initial = JSON.parse(config.data['config.json']);
      const preload = initial.spec.cluster.settings.find(setting => setting.name === 'shared_preload_libraries').value;
      if (pg === 18) {
        assert.equal(preload, 'neon,pg_stat_statements');
        assert.ok(!initial.spec.cluster.settings.some(setting => /^(cron|timescaledb)\./.test(setting.name)));
        assert.doesNotMatch(rendered.stdout, /\b(pg_cron|timescaledb|ulid)\b/);
      } else {
        assert.equal(preload, 'neon,pg_cron,timescaledb,pg_stat_statements');
      }
      const input = path.join(dir, `input${pg}.json`), output = path.join(dir, `output${pg}.json`);
      fs.writeFileSync(input, config.data['config.json']);
      // Execute exactly the rendered initialization program, redirecting its
      // two fixed filesystem paths to this disposable offline directory.
      const program = pod.initContainers.find(container => container.name === 'render-config').args[0]
        .replaceAll('/template/config.json', input).replaceAll('/rendered/config.json', output);
      const initialized = spawnSync(process.env.PYTHON_BIN || 'python3', ['-c', program], {
        encoding: 'utf8', env: {PATH: process.env.PATH, TENANT_ID: '1'.repeat(32), TIMELINE_ID: '2'.repeat(32), PG_ROLE_SECRET: 'SCRAM-SHA-256$OFFLINE-NOT-A-CREDENTIAL'},
      });
      assert.equal(initialized.status, 0, initialized.stderr || initialized.error?.message);
      const actual = JSON.parse(fs.readFileSync(output, 'utf8'));
      const settings = Object.fromEntries(actual.spec.cluster.settings.map(setting => [setting.name, setting.value]));
      assert.equal(settings.shared_preload_libraries, pg === 18 ? 'neon,pg_stat_statements' : 'neon,pg_cron,timescaledb,pg_stat_statements,ulid');
      assert.equal(settings['neon.tenant_id'], '1'.repeat(32));
      assert.equal(settings['neon.timeline_id'], '2'.repeat(32));
      if (pg === 18) assert.equal(settings['cron.database'], undefined);
    }
  } finally { fs.rmSync(dir, {recursive: true, force: true}); }
});

for (const [name, overrides, reason] of [
  ['PG18 with full extension profile', {buildProfile: 'full'}, /PG18 compute requires/],
  ['core profile with PG17', {pgVersion: 17}, /dsga-core buildProfile requires PG18/],
  ['core profile with wrapper startup', {mode: 'wrapper'}, /dsga-core buildProfile requires PG18 and public/],
  ['unknown profile', {buildProfile: 'other'}, /buildProfile/],
]) {
  test(`public Compute rejects ${name}`, () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsga-public-reject-'));
    try {
      const file = path.join(dir, 'values.json');
      fs.writeFileSync(file, JSON.stringify(publicComputeValues(fixtureManifest(), 18, overrides)));
      const result = renderPublicCompute(file);
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, reason);
    } finally { fs.rmSync(dir, {recursive: true, force: true}); }
  });
}
test('Helm renders the exact PG17 image; PG18 legacy activation remains rejected', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsga-release-render-'));
  try {
    const m = fixtureManifest();
    const fixture = {experimentalAcknowledged: true, compute: {enabled: true, tenantId: '1'.repeat(32), timelineId: '2'.repeat(32)}};
    for (const pg of [17, 18]) {
      const values = merge(releaseOverlays(m, pg)['neon-compute'], fixture);
      const file = path.join(dir, `pg${pg}.json`); fs.writeFileSync(file, JSON.stringify(values));
      const result = spawnSync(process.env.HELM_BIN || 'helm', ['template', 'offline-candidate', path.join(root, 'charts/neon-compute'), '-f', file, '-n', 'neon', '--kube-version', '1.31.2'], {encoding: 'utf8'});
      if (pg === 17) {
        assert.equal(result.status, 0, result.stderr || result.error?.message);
        const vm = documents(result.stdout).find(doc => doc.kind === 'VirtualMachine');
        assert.equal(vm.spec.guest.rootDisk.image, imageReference(m, 'vm-compute-node-v17'));
      } else {
        assert.notEqual(result.status, 0, 'A legacy PG18 image must not be presented as trusted-runtime-v1');
        assert.match(result.stderr, /startupMode/);
      }
    }
  } finally { fs.rmSync(dir, {recursive: true, force: true}); }
});
