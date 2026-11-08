#!/usr/bin/env node
/** Build offline Helm release artifacts from one verified Neon distribution.
 * This tool never talks to Kubernetes, publishes images, or grants a runtime
 * qualification. It accepts only the explicitly versioned DSGA candidate lane.
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {parseDocument, stringify} from 'yaml';
import {root, merge, documents} from './lib.mjs';
import {ciValues, ciNamespace, ciKubeVersion} from './ci-values.mjs';

export const CORE_BINARIES = [
  'pageserver', 'safekeeper', 'proxy', 'pg_sni_router', 'storage_broker',
  'storage_controller', 'endpoint_storage', 'storage_scrubber', 'neon_local',
  'pagectl', 'compute_ctl', 'fast_import', 'local_proxy', 'vm-monitor',
  'storcon_cli', 'pagebench', 'compaction-simulator', 'wal_craft',
];
export const COMPUTE_COMPONENTS = ['pgbouncer', 'postgres-exporter', 'pgbouncer-exporter', 'sql-exporter'];
export const AUTOSCALING_IMAGES = [
  'autoscaling-go-base', 'vm-kernel', 'vm-builder', 'neonvm-controller',
  'neonvm-vxlan-controller', 'neonvm-runner', 'neonvm-daemon',
  'autoscale-scheduler', 'autoscaler-agent', 'cluster-autoscaler-neonvm',
  'dsga-platform-qualifier',
];
export const POSTGRES_PROFILES = {v14: 'full', v15: 'full', v16: 'full', v17: 'full', v18: 'dsga-core'};
export const RELEASE_VERSION = /^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)-dsga\.[1-9][0-9]*\.[1-9][0-9]*\.amd64$/;
const SHA = /^[a-f0-9]{40}$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;
const REGISTRY = 'docker.io/williamluckyli';

function requireThat(value, message) {
  if (!value) throw new Error(message);
}
function object(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function exactSet(actual, expected, label) {
  requireThat(Array.isArray(actual) && actual.every(v => typeof v === 'string') &&
    new Set(actual).size === actual.length &&
    JSON.stringify([...actual].sort()) === JSON.stringify([...expected].sort()), `${label} differs from the supported distribution contract`);
}
export function expectedImages() {
  return [
    'neon', 'neon-build-tools', ...CORE_BINARIES.map(v => v.replaceAll('_', '-')),
    ...COMPUTE_COMPONENTS, ...AUTOSCALING_IMAGES,
    ...Object.keys(POSTGRES_PROFILES).flatMap(v => [
      `compute-node-${v}`, `vm-compute-node-${v}`,
      ...(POSTGRES_PROFILES[v] === 'full' ? [`neon-test-extensions-${v}`] : []),
    ]),
  ].sort();
}

export function validateManifest(manifest, {releaseVersion, helmSha}) {
  requireThat(object(manifest), 'Manifest must be an object');
  requireThat(typeof releaseVersion === 'string' && RELEASE_VERSION.test(releaseVersion), 'Expected canonical DSGA candidate SemVer ending in .amd64');
  requireThat(SHA.test(helmSha || ''), 'Expected full immutable Helm SHA');
  requireThat(manifest.schema_version === 2 && manifest.channel === 'dsga', 'Expected schema_version=2 and channel=dsga');
  requireThat(manifest.version === releaseVersion && manifest.chart_version === releaseVersion, 'Manifest/image/Chart version mismatch');
  requireThat(manifest.architecture === 'linux/amd64', 'Current DSGA Helm deployment templates support linux/amd64 only');
  requireThat(SHA.test(manifest.neon_commit || '') && SHA.test(manifest.verification_commit || ''), 'Missing immutable Neon/verification commit');
  requireThat(manifest.release_tier === 'candidate' && manifest.vm_system_mode === 'legacy', 'This workflow only packages the explicitly unqualified legacy candidate VM lane');
  requireThat(object(manifest.qualification) && manifest.qualification.production_ready === false &&
    manifest.qualification.physical_memory_release_qualified === false, 'A package build cannot grant production or physical-memory-release qualification');
  const lock = manifest.source_lock;
  requireThat(object(lock), 'Missing source_lock');
  requireThat(lock.registry === REGISTRY, 'Unexpected image registry in source lock');
  requireThat(lock.helm_repository === 'william-lbn/neon-helm' && lock.helm_commit === helmSha, 'Helm source SHA/repository differs from the checked out source');
  requireThat(lock.autoscaling_repository === 'william-lbn/autoscaling' && SHA.test(lock.autoscaling_commit || ''), 'Missing immutable Autoscaling source');
  requireThat(lock.postgres_repository === 'william-lbn/postgres' && object(lock.postgres), 'Missing PostgreSQL source');
  exactSet(Object.keys(lock.postgres), Object.keys(POSTGRES_PROFILES), 'PostgreSQL majors');
  requireThat(Object.values(lock.postgres).every(sha => SHA.test(sha)), 'All PostgreSQL majors require full source SHAs');
  requireThat(object(lock.postgres_profiles), 'Missing PostgreSQL build profiles');
  exactSet(Object.keys(lock.postgres_profiles), Object.keys(POSTGRES_PROFILES), 'PostgreSQL profile majors');
  for (const [major, profile] of Object.entries(POSTGRES_PROFILES)) {
    requireThat(lock.postgres_profiles[major] === profile, `Unsupported ${major} profile: PG18 is dsga-core, not full extensions`);
  }
  exactSet(lock.core_binaries, CORE_BINARIES, 'Core binary inventory');
  requireThat(object(lock.compute_components), 'Missing compute component inventory');
  exactSet(Object.keys(lock.compute_components), COMPUTE_COMPONENTS, 'Compute component inventory');
  exactSet(lock.autoscaling_images, AUTOSCALING_IMAGES, 'Autoscaling image inventory');
  requireThat(object(manifest.images), 'Missing image records');
  exactSet(Object.keys(manifest.images), expectedImages(), 'Complete image inventory');
  for (const [name, record] of Object.entries(manifest.images)) {
    requireThat(object(record) && record.kind === 'runtime' && record.name === name, `Invalid image identity for ${name}`);
    requireThat(record.image === `${lock.registry}/${name}:${releaseVersion}`, `Wrong component, registry or version for ${name}`);
    requireThat(DIGEST.test(record.digest || ''), `Missing immutable digest for ${name}`);
    const autoscaling = AUTOSCALING_IMAGES.includes(name);
    const repository = autoscaling ? lock.autoscaling_repository : 'william-lbn/neon';
    const commit = autoscaling ? lock.autoscaling_commit : manifest.neon_commit;
    requireThat(record.source_repository === repository && record.source_commit === commit, `Image source mismatch for ${name}`);
    if ('architecture' in record) requireThat(record.architecture === manifest.architecture, `Image architecture mismatch for ${name}`);
    if ('execution' in record) {
      const [, runId, attempt] = releaseVersion.match(/-dsga\.([0-9]+)\.([0-9]+)\.amd64$/);
      requireThat(object(record.execution) && record.execution.repository === 'william-lbn/neon' &&
        record.execution.run_id === runId && record.execution.run_attempt === attempt &&
        record.execution.run_url === `https://github.com/william-lbn/neon/actions/runs/${runId}/attempts/${attempt}`,
      `Image execution belongs to a different run or attempt: ${name}`);
    }
  }
  return manifest;
}

export function imageReference(manifest, name) {
  const image = manifest.images[name];
  requireThat(image && DIGEST.test(image.digest || ''), `Missing immutable digest for ${name}`);
  // Helm uses the digest as identity. Do not leave a mutable tag in the value.
  return `${manifest.source_lock.registry}/${name}@${image.digest}`;
}

export function releaseOverlays(manifest, pgMajor) {
  requireThat([17, 18].includes(pgMajor), 'Only PG17/PG18 deployment overlays are supported');
  const ref = name => imageReference(manifest, name);
  return {
    neonvm: {
      experimentalAcknowledged: false,
      images: {controller: ref('neonvm-controller'), runner: ref('neonvm-runner'), vxlanController: ref('neonvm-vxlan-controller')},
    },
    'neon-autoscaler': {
      experimentalAcknowledged: false,
      images: {agent: ref('autoscaler-agent'), scheduler: ref('autoscale-scheduler')},
      // The current platform qualification chart remains PG17-only. A PG18
      // artifact is not permission to weaken that runtime contract.
      dsga: {enabled: false},
    },
    'neon-core': {
      validation: {labAcknowledged: false},
      global: {
        neonImage: {repository: `${manifest.source_lock.registry}/neon`, tag: '', digest: manifest.images.neon.digest},
        componentImages: {
          pageserver: ref('pageserver'), safekeeper: ref('safekeeper'), storageBroker: ref('storage-broker'),
          proxy: ref('proxy'), storageController: ref('storage-controller'),
        },
      },
      compute: {
        enabled: false, pgVersion: pgMajor, mode: 'public',
        buildProfile: manifest.source_lock.postgres_profiles[`v${pgMajor}`],
        // This legacy chart's compute.image.digest is a FULL reference, unlike
        // global.neonImage.digest and the qualifier's image.digest fields.
        image: {repository: `${manifest.source_lock.registry}/compute-node-v${pgMajor}`, tag: '', digest: ref(`compute-node-v${pgMajor}`)},
      },
    },
    'neon-compute': {
      experimentalAcknowledged: false,
      compute: {
        enabled: false, pgVersion: pgMajor, startupMode: 'legacy',
        image: ref(`vm-compute-node-v${pgMajor}`),
        runtime: {runnerImage: ref('neonvm-runner'), kernelImage: ref('vm-kernel')},
      },
    },
    'neon-managed-pageserver': {image: ref('pageserver')},
    'dsga-platform-qualifier': {
      enabled: false,
      image: {repository: `${manifest.source_lock.registry}/dsga-platform-qualifier`, digest: manifest.images['dsga-platform-qualifier'].digest},
    },
  };
}

function execute(binary, args, {cwd = root} = {}) {
  const result = spawnSync(binary, args, {cwd, encoding: 'utf8', timeout: 120000, maxBuffer: 16 * 1024 * 1024});
  if (result.error || result.status !== 0) {
    throw new Error(`${binary} ${args[0]} failed: ${result.error?.message || result.stderr || result.stdout}`);
  }
  return result.stdout;
}
function hash(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}
function writeJSON(file, value) {
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n', {flag: 'wx'});
}

export function parseManifest(raw) {
  // JSON.parse alone accepts duplicate keys, which can make a reviewed value
  // differ from the consumed one. YAML's strict duplicate-key parser also
  // accepts the JSON grammar; JSON.parse still rejects non-JSON input.
  const value = JSON.parse(raw);
  const doc = parseDocument(raw, {uniqueKeys: true});
  requireThat(doc.errors.length === 0, 'Manifest contains duplicate or ambiguous object keys');
  return value;
}

export function packageRelease({manifestPath, releaseVersion, helmSha, output}) {
  const source = execute('git', ['rev-parse', 'HEAD']).trim();
  requireThat(source === helmSha, 'Requested Helm SHA is not the checked out HEAD');
  requireThat(execute('git', ['status', '--porcelain', '--untracked-files=normal']).trim() === '', 'Refusing to label a dirty source tree with a clean Helm SHA');
  const raw = fs.readFileSync(manifestPath, 'utf8');
  requireThat(Buffer.byteLength(raw) <= 2 * 1024 * 1024, 'Distribution manifest is unexpectedly large');
  const manifest = validateManifest(parseManifest(raw), {releaseVersion, helmSha});
  const destination = path.resolve(output);
  requireThat(!fs.existsSync(destination), 'Release output must be new; never merge stale packages from another run');
  const parent = path.dirname(destination);
  fs.mkdirSync(parent, {recursive: true});
  const staging = fs.mkdtempSync(path.join(os.tmpdir(), 'dsga-helm-source-'));
  const pending = fs.mkdtempSync(path.join(parent, '.dsga-helm-pending-'));
  const helm = process.env.HELM_BIN || 'helm';
  const checksum = hash(raw);
  const qualifiedCharts = new Set(Object.keys(releaseOverlays(manifest, 17)));
  try {
    const charts = fs.readdirSync(path.join(root, 'charts'), {withFileTypes: true})
      .filter(entry => entry.isDirectory()).map(entry => entry.name).sort();
    requireThat(charts.length > 0, 'No charts found');
    const lock = {
      schema_version: 2, version: releaseVersion, chart_version: releaseVersion,
      distribution_manifest_sha256: checksum, architecture: manifest.architecture,
      neon_commit: manifest.neon_commit, verification_commit: manifest.verification_commit,
      source_lock: manifest.source_lock,
      images: Object.fromEntries(Object.keys(manifest.images).sort().map(name => [name, imageReference(manifest, name)])),
      release_tier: manifest.release_tier, vm_system_mode: manifest.vm_system_mode,
      qualification: manifest.qualification,
      chart_image_bindings: [...qualifiedCharts].sort(),
      deployment_constraints: {
        kubernetes_runtime_contract: '1.31.x with original worker-117/118/119 placement',
        operator_identities_and_budgets_required: true,
        pg18_trusted_deployment_blocked_for_legacy_vm: true,
        pg18_public_sql_build_profile: 'dsga-core',
        pg18_public_sql_container_verified_by_helm_packaging: false,
        autoscaler_platform_qualification_pg_major: 17,
        external_control_plane_images_rebuilt: false,
      },
    };
    writeJSON(path.join(pending, 'dsga-release-lock.json'), lock);
    fs.writeFileSync(path.join(pending, 'distribution-manifest.json'), raw, {flag: 'wx'});
    for (const pg of [17, 18]) {
      for (const [chart, values] of Object.entries(releaseOverlays(manifest, pg))) {
        writeJSON(path.join(pending, `pg${pg}-${chart}.values.json`), values);
      }
    }
    const receipts = [];
    for (const chart of charts) {
      const directory = path.join(staging, chart);
      fs.cpSync(path.join(root, 'charts', chart), directory, {recursive: true, dereference: false});
      const metadataFile = path.join(directory, 'Chart.yaml');
      const metadata = parseDocument(fs.readFileSync(metadataFile, 'utf8'));
      requireThat(!metadata.errors.length && metadata.get('name') === chart, `Invalid Chart identity: ${chart}`);
      metadata.set('version', releaseVersion);
      if (qualifiedCharts.has(chart)) metadata.set('appVersion', releaseVersion);
      const annotations = metadata.get('annotations')?.toJSON() || {};
      metadata.set('annotations', {
        ...annotations,
        'neon.tech/distribution-version': releaseVersion,
        'neon.tech/distribution-manifest-sha256': checksum,
        'neon.tech/neon-commit': manifest.neon_commit,
        'neon.tech/autoscaling-commit': manifest.source_lock.autoscaling_commit,
        'neon.tech/helm-commit': helmSha,
        'neon.tech/postgres17-commit': manifest.source_lock.postgres.v17,
        'neon.tech/postgres18-commit': manifest.source_lock.postgres.v18,
        'neon.tech/release-tier': 'candidate',
        'neon.tech/vm-system-mode': 'legacy',
        'neon.tech/production-ready': 'false',
        'neon.tech/physical-memory-release-qualified': 'false',
        'neon.tech/image-binding': qualifiedCharts.has(chart) ? 'current-distribution' : 'separate-product-not-rebuilt',
      });
      fs.writeFileSync(metadataFile, metadata.toString());
      const valuesFile = path.join(directory, 'values.yaml');
      const originalValues = documents(fs.readFileSync(valuesFile, 'utf8'))[0];
      const overlay = releaseOverlays(manifest, 17)[chart] || {};
      const values = merge(originalValues, overlay);
      fs.writeFileSync(valuesFile, stringify(values));
      fs.mkdirSync(path.join(directory, 'files'), {recursive: true});
      writeJSON(path.join(directory, 'files/dsga-release-lock.json'), lock);

      // Only the offline fixture acknowledges experimental settings. Package
      // defaults and released overlays keep their acknowledgements disabled.
      const fixture = merge(ciValues(chart), overlay);
      if ('experimentalAcknowledged' in fixture) fixture.experimentalAcknowledged = true;
      if (fixture.validation) fixture.validation.labAcknowledged = true;
      if (chart === 'neon-compute') Object.assign(fixture.compute, {tenantId: '1'.repeat(32), timelineId: '2'.repeat(32)});
      const fixtureFile = path.join(staging, `${chart}.json`);
      writeJSON(fixtureFile, fixture);
      const lintFixture = structuredClone(fixture);
      if (chart === 'dsga-qualification-issuer') lintFixture.subject.name = 'release-name';
      const lintFile = path.join(staging, `${chart}.lint.json`);
      writeJSON(lintFile, lintFixture);
      execute(helm, ['lint', directory, '-f', lintFile, '-n', ciNamespace(chart), '--kube-version', ciKubeVersion(chart), '--strict']);
      const rendered = execute(helm, ['template', chart, directory, '-f', fixtureFile, '-n', ciNamespace(chart), '--kube-version', ciKubeVersion(chart)]);
      requireThat(!documents(rendered).some(value => value.kind === 'Secret'), `Unexpected Secret creation by ${chart}`);
      execute(helm, ['package', directory, '--destination', pending]);
      const filename = `${chart}-${releaseVersion}.tgz`;
      const packagedMeta = documents(execute(helm, ['show', 'chart', path.join(pending, filename)]))[0];
      requireThat(packagedMeta.version === releaseVersion && packagedMeta.annotations['neon.tech/helm-commit'] === helmSha, `Packaged Chart metadata mismatch: ${chart}`);
      receipts.push({chart, file: filename, sha256: hash(fs.readFileSync(path.join(pending, filename))), lint: 'pass', offline_render: 'pass'});
    }
    execute(helm, ['repo', 'index', pending, '--url', `https://github.com/william-lbn/neon/releases/download/${releaseVersion}`]);
    writeJSON(path.join(pending, 'helm-package-receipt.json'), {
      schema_version: 1, release_version: releaseVersion, helm_commit: helmSha,
      distribution_manifest_sha256: checksum, charts: receipts,
      qualification: manifest.qualification, deployed: false,
      pg18_legacy_deployment_blocked: true,
    });
    fs.writeFileSync(path.join(pending, 'DSGA-HELM-README.md'), `# DSGA 候选发行 ${releaseVersion}\n\n` +
      `这组 Chart 与同目录 distribution-manifest.json 的四库源码和镜像摘要绑定。先运行 \`sha256sum -c HELM-SHA256SUMS\`。${charts.length} 个 Chart 均采用同一版本；六组运行组件的镜像绑定来自本次发行，控制面和其它产品镜像保留原独立来源。\n\n` +
      `## 当前能力边界\n\n` +
      `- 平台：linux/amd64；现有受管部署仍要求 Kubernetes 1.31.x 和原 worker-117/118/119 放置约束。\n` +
      `- release_tier=candidate，vm_system_mode=legacy，production_ready=false，physical_memory_release_qualified=false。打包通过不构成正常启动闭包、Host 物理归还或生产验收。\n` +
      `- PG17 为 full 构建，PG18 为 dsga-core 构建。PG18 没有 neon-test-extensions-v18 制品。\n` +
      `- pg18-neon-core.values.json 显式选择 public / dsga-core SQL 配置，仅预加载本次交付的 neon、pg_stat_statements；不会加载未交付的第三方扩展。此路径已验证离线渲染及配置初始化，不代表容器或完整存储链路实跑验收。\n` +
      `- PG18 现有受管 Chart 需要 trusted-runtime-v1；本次 legacy VM 镜像不满足该条件。pg18-neon-compute.values.json 记录正确摘要并保持关闭，直接启用将被现有 schema 拒绝。需要另行取得完整 normal-split 镜像与真实资格后才能部署该闭包。\n` +
      `- 所有发行 overlay 保留实验确认/自动伸缩/Compute/Qualifier 的安全关闭默认值。真实租户、VM UID、预算、CA、Lease、节点身份及认证报告由实际部署输入提供。\n\n` +
      `## 使用文件\n\n` +
      `每个 pg17-<chart>.values.json / pg18-<chart>.values.json 都是对应单个 Chart 的镜像覆盖文件，可与已核实的部署 values 合并；不得将离线渲染 fixture 用于部署。Chart 内嵌 files/dsga-release-lock.json，同目录锁还说明未被本次构建重建的组件。\n\n` +
      `示例（仅离线渲染，operator-values.yaml 必须来自实际部署计划）：\n\n` +
      `\`\`\`bash\nhelm template neonvm ./neonvm-${releaseVersion}.tgz -f pg17-neonvm.values.json -f operator-values.yaml --kube-version 1.31.2\n\`\`\`\n`, {flag: 'wx'});
    const files = fs.readdirSync(pending).sort();
    fs.writeFileSync(path.join(pending, 'HELM-SHA256SUMS'), files.map(name => `${hash(fs.readFileSync(path.join(pending, name)))}  ${name}\n`).join(''), {flag: 'wx'});
    fs.renameSync(pending, destination);
    return {version: releaseVersion, charts: receipts.length, images: Object.keys(manifest.images).length, output: destination, deployed: false};
  } finally {
    fs.rmSync(staging, {recursive: true, force: true});
    if (fs.existsSync(pending)) fs.rmSync(pending, {recursive: true, force: true});
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const {values} = parseArgs({options: {
    manifest: {type: 'string'}, version: {type: 'string'}, 'helm-sha': {type: 'string'}, output: {type: 'string'},
  }});
  for (const name of ['manifest', 'version', 'helm-sha', 'output']) requireThat(values[name], `Missing --${name}`);
  console.log(JSON.stringify(packageRelease({manifestPath: values.manifest, releaseVersion: values.version, helmSha: values['helm-sha'], output: values.output})));
}
