/** Schema 3 consumes original build evidence; it never grants runtime qualification. */
import {createHash} from 'node:crypto';
import {isDeepStrictEqual} from 'node:util';

export const NORMAL_MODE = 'normal-split-v3';
export const NORMAL_IMAGES = ['normal-guest-base-v17', 'normal-guest-base-v18', 'vm-kernel-normal'];
const DOCUMENTS = ['assembly-inputs.json', 'base-provenance.json', 'ordinary-input-readback.json', 'normal-readback.json', 'oci-metadata.json'];
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const sha = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value) && value !== '0'.repeat(64);
const digest = value => typeof value === 'string' && value.startsWith('sha256:') && sha(value.slice(7));
const hash = value => createHash('sha256').update(value).digest('hex');
const tagged = item => `${item.image}@${item.digest}`;
const immutable = item => `${item.image.slice(0, item.image.lastIndexOf(':'))}@${item.digest}`;
function check(value, reason) { if (!value) throw new Error(`Normal Guest ${reason}`); }
function same(actual, expected, reason) {
  check(object(actual) && Object.entries(expected).every(([key, value]) => isDeepStrictEqual(actual[key], value)), reason);
}
function keys(actual, expected, reason) {
  check(object(actual) && isDeepStrictEqual(Object.keys(actual).sort(), [...expected].sort()), reason);
}

export function verifyNormalManifest(manifest, parseJSON) {
  const {images, source_lock: lock, version, neon_commit: neon} = manifest;
  const [, runId, attempt] = version.match(/-dsga\.([0-9]+)\.([0-9]+)\.amd64$/);
  const execution = {repository: 'william-lbn/neon', run_id: runId, run_attempt: attempt,
    run_url: `https://github.com/william-lbn/neon/actions/runs/${runId}/attempts/${attempt}`};
  check(isDeepStrictEqual(manifest.execution, execution) && manifest.verification_commit === neon, 'source verification or run/attempt differs');
  keys(manifest.vm_system_modes, Object.keys(lock.postgres), 'per-major modes are incomplete');
  const pinned = lock.normal_guest_inputs;
  same(pinned, {architecture: 'linux/amd64'}, 'build inputs are missing');
  check(sha(pinned.build_plan_sha256) && sha(pinned.ordinary_package_lock_sha256), 'build/package lock digests are missing');
  const caps = manifest.autoscaling_capabilities;
  same(caps, {kind: 'distribution-capabilities', source_repository: lock.autoscaling_repository,
    source_commit: lock.autoscaling_commit, version, architecture: 'linux/amd64', execution,
    release_channel: 'candidate', normal_qualification: false, production_ready: false, latest_eligible: false,
    vm_builder_default_system_mode: 'legacy'}, 'capability source or qualification differs');
  check(isDeepStrictEqual(caps.image_digests, Object.fromEntries([...lock.autoscaling_images, 'vm-kernel-normal'].map(name => [name, images[name].digest]))), 'capability image digest set differs');
  for (const [name, field, guarded] of [['vm-kernel', 'kernel', false], ['vm-kernel-normal', 'normal_kernel', true]]) {
    const kernel = caps[field];
    same(kernel, {image: tagged(images[name]), normal_metadata_guard: guarded, normal_qualification: false}, 'kernel source or qualification differs');
    check(['artifact_sha256', 'config_sha256', 'notes_sha256'].every(key => sha(kernel[key])), 'actual kernel identity is incomplete');
    if (guarded) check(['profile', 'release'].every(key => typeof kernel[key] === 'string' && kernel[key].trim()), 'actual normal kernel profile/release is incomplete');
  }
  keys(manifest.postgres_native_validation, ['v17', 'v18'], 'both original native gates are required');
  for (const pg of ['v17', 'v18']) {
    const native = manifest.postgres_native_validation[pg];
    same(native, {kind: 'postgres-native-validation', source_repository: lock.postgres_repository,
      source_commit: lock.postgres[pg], pg_major: Number(pg.slice(1)), scope: 'native-kernel-not-vm',
      normal_qualification: false, production_ready: false, execution_repository: execution.repository,
      run_id: runId, run_attempt: attempt}, 'native gate source or attempt differs');
    check(sha(native.postgres_binary_sha256), 'native gate binary proof is absent');
  }
  const read = raw => {
    check(typeof raw === 'string' && Buffer.byteLength(raw) <= 8 * 1024 * 1024, 'original document is absent or oversized');
    const value = parseJSON(raw); check(object(value), 'document must be an object'); return value;
  };
  for (const pg of Object.keys(lock.postgres)) {
    const isNormal = ['v17', 'v18'].includes(pg), item = images[`vm-compute-node-${pg}`], disk = item.guest_disk;
    const mode = isNormal ? NORMAL_MODE : 'legacy';
    check(manifest.vm_system_modes[pg] === mode, 'PG17/PG18 must form the exact normal pair');
    same(disk, {system_mode: mode, image: tagged(item), format: 'qcow2', inputs: {
      compute: tagged(images[`compute-node-${pg}`]), builder: tagged(images['vm-builder']), daemon: tagged(images['neonvm-daemon']),
    }}, 'VM disk mode or input/output image binding differs');
    check(Number.isSafeInteger(disk.virtual_size) && disk.virtual_size >= 4 * 2 ** 30 && sha(disk.sha256), 'VM disk size or digest is invalid');
    if (!isNormal) { check(disk.normal_guest === undefined, 'legacy disk contains normal evidence'); continue; }
    const proof = disk.normal_guest;
    keys(proof, ['assembly_json', 'documents', 'archive_sha256'], 'original assembly evidence is missing');
    const receipt = read(proof.assembly_json);
    keys(proof.documents, DOCUMENTS, 'original readback files are incomplete');
    keys(receipt.files_sha256, [...DOCUMENTS, 'guest.oci.tar'], 'file digest set is incomplete');
    check(Object.values(receipt.files_sha256).every(sha) && sha(proof.archive_sha256) &&
      receipt.files_sha256['guest.oci.tar'] === proof.archive_sha256, 'OCI archive digest differs');
    const docs = Object.fromEntries(DOCUMENTS.map(name => {
      const raw = proof.documents[name], parsed = read(raw);
      check(hash(raw) === receipt.files_sha256[name], `original document digest differs: ${name}`);
      return [name, parsed];
    }));
    same(receipt, {kind: 'normal-guest-assembly', protocol_version: 1, build_mode: NORMAL_MODE,
      image: tagged(item), architecture: 'linux/amd64', execution, packaging_source: neon, compute_source: neon,
      guest_autoscaling_source: lock.autoscaling_commit, postgres_source: lock.postgres[pg], postgres_major: Number(pg.slice(1))},
    'assembly source or run/attempt differs');
    check(['disk_sha256', 'kernel_sha256', 'system_manifest_sha256', 'native_birth_manifest_sha256'].every(key => sha(receipt[key])) &&
      receipt.disk_sha256 === disk.sha256 && receipt.kernel_sha256 === caps.normal_kernel.artifact_sha256, 'disk/kernel/System/NativeBirth proof differs');
    const compute = images[`compute-node-${pg}`], daemon = images['neonvm-daemon'], builder = images['vm-builder'];
    check(compute.postgres_source === lock.postgres[pg] && sha(compute.postgres_elf_sha256) && sha(builder.builder_sha256), 'independent PG or Builder artifact is missing');
    keys(compute.runtime_elf_sha256, ['compute_ctl'], 'independent Compute ELF is missing');
    keys(daemon.runtime_elf_sha256, ['neonvmd', 'dsga_resource_guard'], 'independent Daemon/Guard ELF is missing');
    const runtime = {...compute.runtime_elf_sha256, ...daemon.runtime_elf_sha256};
    check(Object.values(runtime).every(sha) && isDeepStrictEqual(receipt.runtime_elf_sha256, runtime), 'runtime ELF digests differ');
    const refs = {base_image: immutable(images[`normal-guest-base-${pg}`]), kernel_image: immutable(images['vm-kernel-normal']), disk_tools_image: immutable(images['neonvm-runner'])};
    same(docs['assembly-inputs.json'], {...refs, neon_source: neon, guest_autoscaling_source: lock.autoscaling_commit,
      postgres_major: Number(pg.slice(1)), postgres_elf_sha256: compute.postgres_elf_sha256, builder_sha256: builder.builder_sha256,
      kernel_sha256: receipt.kernel_sha256, runtime_elf_sha256: runtime}, 'assembly inputs differ from original same-run artifacts');
    const base = docs['base-provenance.json'];
    same(base, {base_image: refs.base_image}, 'base provenance differs');
    check(typeof base.platform_image === 'string' && base.platform_image.split('@')[0] === refs.base_image.split('@')[0] &&
      digest(base.platform_image.split('@')[1]) && digest(base.config_digest), 'base platform/config is unpinned');
    same(base.labels, {'org.opencontainers.image.revision': neon, 'io.neon.guest.autoscaling.source': lock.autoscaling_commit,
      'io.neon.pg.major': pg.slice(1), 'io.neon.pg.source': lock.postgres[pg], 'io.neon.ordinary.package-lock.sha256': pinned.ordinary_package_lock_sha256}, 'base source labels differ');
    const ordinary = docs['ordinary-input-readback.json'];
    same(ordinary, {kind: 'normal-ordinary-input-readback', protocol_version: 1, package_lock_sha256: pinned.ordinary_package_lock_sha256}, 'package source proof differs');
    check(Number.isSafeInteger(ordinary.derived_file_count) && ordinary.derived_file_count > 0 && Array.isArray(ordinary.inputs) &&
      ordinary.inputs.length > 0 && ordinary.inputs.every(e => object(e) && typeof e.path === 'string' && sha(e.sha256) && Number.isSafeInteger(e.bytes) && e.bytes > 0) &&
      new Set(ordinary.inputs.map(e => e.path)).size === ordinary.inputs.length, 'ordinary input inventory is invalid');
    const readback = docs['normal-readback.json'];
    same(readback, {kind: 'normal-guest-oci-readback', protocol_version: 1, builder_sha256: builder.builder_sha256}, 'final OCI readback is absent');
    const oci = readback.oci;
    same(oci, {image_digest: item.digest, architecture: 'linux/amd64'}, 'final OCI identity differs');
    check(digest(oci.platform_manifest_digest) && digest(oci.config_digest) && Array.isArray(oci.rootfs_diff_ids) &&
      oci.rootfs_diff_ids.length > 0 && oci.rootfs_diff_ids.every(digest), 'final OCI config/layers are incomplete');
    same(docs['oci-metadata.json'], {'containerimage.digest': item.digest}, 'producer OCI identity differs');
    for (const [name, expected] of [['disk.qcow2', receipt.disk_sha256], ['vmlinuz', receipt.kernel_sha256]]) {
      const history = oci.assets?.[name];
      check(Array.isArray(history) && history.length > 0 && history.every(layer => object(layer) && digest(layer.layer_digest) &&
        (layer.material === null || object(layer.material) && sha(layer.material.sha256) && Number.isSafeInteger(layer.material.size) && layer.material.size > 0)), 'disk/kernel layer history is incomplete');
      check(history.at(-1).material?.sha256 === expected, 'final visible disk/kernel differs');
    }
    same(readback.root, {kind: 'normal-guest-root-readback', protocol_version: 1, architecture: 'linux/amd64',
      system_profile: 'neon-dsga-normal-system-source-v3', build_plan_sha256: pinned.build_plan_sha256,
      base_image_sha256: refs.base_image.split('sha256:')[1], postgres_major: Number(pg.slice(1)),
      postgres_elf_sha256: compute.postgres_elf_sha256, system_manifest_sha256: receipt.system_manifest_sha256,
      native_birth_manifest_sha256: receipt.native_birth_manifest_sha256, runtime_elf_sha256: runtime}, 'final root differs from independent artifacts');
  }
}
