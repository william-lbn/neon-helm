// Synthetic, offline-only records. These hashes do not identify registry images.
import {createHash} from 'node:crypto';
import {CORE_BINARIES, COMPUTE_COMPONENTS, AUTOSCALING_IMAGES, POSTGRES_PROFILES, expectedImages} from '../../tools/package-dsga-release.mjs';
const fakeSha = label => createHash('sha1').update(`OFFLINE-NOT-DEPLOYABLE/${label}`).digest('hex');

export function fixtureManifest(helmSha = fakeSha('helm')) {
  const version = '0.2.0-dsga.123456789.1.amd64';
  const neon = fakeSha('neon');
  const autoscaling = fakeSha('autoscaling');
  const registry = 'docker.io/williamluckyli';
  return {
    schema_version: 2, channel: 'dsga', version, chart_version: version,
    architecture: 'linux/amd64', neon_commit: neon, verification_commit: neon,
    release_tier: 'candidate', vm_system_mode: 'legacy',
    qualification: {production_ready: false, physical_memory_release_qualified: false},
    source_lock: {
      registry, autoscaling_repository: 'william-lbn/autoscaling', autoscaling_commit: autoscaling,
      postgres_repository: 'william-lbn/postgres', postgres: Object.fromEntries(Object.keys(POSTGRES_PROFILES).map(v => [v, fakeSha(v)])),
      postgres_profiles: {...POSTGRES_PROFILES},
      helm_repository: 'william-lbn/neon-helm', helm_commit: helmSha,
      core_binaries: [...CORE_BINARIES], compute_components: Object.fromEntries(COMPUTE_COMPONENTS.map(v => [v, `/bin/${v}`])),
      autoscaling_images: [...AUTOSCALING_IMAGES],
    },
    images: Object.fromEntries(expectedImages().map(name => [name, {
      kind: 'runtime', name, image: `${registry}/${name}:${version}`,
      digest: `sha256:${createHash('sha256').update(`OFFLINE-NOT-DEPLOYABLE/${name}`).digest('hex')}`,
      source_repository: AUTOSCALING_IMAGES.includes(name) ? 'william-lbn/autoscaling' : 'william-lbn/neon',
      source_commit: AUTOSCALING_IMAGES.includes(name) ? autoscaling : neon,
      architecture: 'linux/amd64',
      execution: {repository: 'william-lbn/neon', run_id: '123456789', run_attempt: '1', run_url: 'https://github.com/william-lbn/neon/actions/runs/123456789/attempts/1'},
    }])),
  };
}
