#!/usr/bin/env node
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {get, kube, pinned} from './lib.mjs';

const namePattern = /^[a-z0-9][a-z0-9.-]*$/;
const catalogEnv = 'NEON_DSGA_RUNTIME_CATALOG';

export function imagePins(catalog, operations) {
  if (![1, 2, 3].includes(catalog?.protocol_version) ||
      !Array.isArray(catalog.releases) || catalog.releases.length === 0 || catalog.releases.length > 32 ||
      !Array.isArray(operations)) throw new Error('DSGA image inventory is incomplete');
  const pins = new Map();
  function add(plan, origin) {
    const images = {guest: plan?.image, runner: plan?.runner, kernel: plan?.kernel};
    if (plan?.qualifier != null) images.qualifier = plan.qualifier;
    const nodes = plan?.nodes ?? null;
    if (Object.values(images).some(image => typeof image !== 'string' || !pinned.test(image)) ||
        nodes !== null && (!Array.isArray(nodes) || nodes.length === 0 ||
          nodes.some(node => typeof node !== 'string' || !namePattern.test(node)) ||
          new Set(nodes).size !== nodes.length)) throw new Error('DSGA image or placement is unavailable');
    for (const [role, image] of Object.entries(images)) {
      if (!pins.has(image)) pins.set(image, []);
      pins.get(image).push({role, nodes, ...origin});
    }
  }
  for (const item of catalog.releases) {
    const creation = item?.creation;
    const major = creation?.postgres_version;
    if (![17, 18].includes(major)) throw new Error('Unexpected DSGA catalog PostgreSQL major');
    const qualifier = creation.vm?.generic_guest?.supply?.qualifier_image;
    if (catalog.protocol_version >= 2 && qualifier == null) throw new Error('The catalog qualifier image is unavailable');
    add({
      image: creation.image, runner: creation.vm?.runner_image, kernel: creation.vm?.kernel_image,
      nodes: creation.vm?.placement?.allowed_node_names,
      qualifier,
    }, {source: 'catalog', postgresMajor: major});
  }
  for (const item of operations) {
    if (typeof item?.id !== 'string' || !/^op_[a-f0-9]+$/.test(item.id) ||
        !['queued', 'running', 'retry_wait', 'failed'].includes(item.state)) {
      throw new Error('Unexpected DSGA Operation entry');
    }
    add(item, {source: 'operation', operation: item.id, state: item.state});
  }
  return [...pins.entries()].sort(([left], [right]) => left.localeCompare(right))
    .map(([image, origins]) => ({image, origins}));
}

function catalogSnapshot(namespace, apiDeployment) {
  const api = get('deployment', apiDeployment, namespace);
  const refs = api?.spec?.template?.spec?.containers?.flatMap(c =>
    (c.env ?? []).filter(env => env.name === catalogEnv).map(env => env.valueFrom?.secretKeyRef));
  if (refs?.length !== 1 || refs[0]?.key !== 'catalog.json' || !namePattern.test(refs[0]?.name ?? '')) {
    throw new Error('The API Deployment has no original DSGA runtime catalog reference');
  }
  const secret = get('secret', refs[0].name, namespace);
  const raw = secret?.data?.['catalog.json'];
  if (typeof raw !== 'string' || !api.metadata?.uid || !Number.isSafeInteger(api.metadata?.generation) ||
      !secret.metadata?.uid || !secret.metadata?.resourceVersion) throw new Error('The DSGA runtime catalog is unavailable');
  let catalog;
  try {
    catalog = JSON.parse(Buffer.from(raw, 'base64').toString('utf8'));
  } catch {
    throw new Error('The DSGA runtime catalog is not valid JSON');
  }
  return {
    catalog,
    identity: [api.metadata.uid, api.metadata.generation, secret.metadata.uid, secret.metadata.resourceVersion],
  };
}

function projectedOperations(namespace, metadataPod) {
  const statement = `
BEGIN READ ONLY;
WITH eligible AS (
  SELECT o.id,o.state,o.payload->'dsga_creation' AS plan
  FROM operations o
  WHERE o.payload ? 'dsga_creation' AND (
    o.state IN ('queued','running','retry_wait') OR
    (o.state='failed' AND o.retryable AND NOT EXISTS (
      SELECT 1 FROM operations retired
      WHERE retired.project_id=o.project_id AND retired.resource_id=o.resource_id
        AND retired.state='succeeded' AND retired.finished_at IS NOT NULL
        AND retired.lease_owner IS NULL AND retired.lease_expires_at IS NULL
        AND (
          (retired.action IN ('cleanup_failed_project','cleanup_failed_branch','cleanup_failed_endpoint')
            AND retired.payload->>'failed_create_operation_id'=o.id)
          OR
          (retired.action='retire_failed_dsga_resume_v1'
            AND retired.payload->>'failed_resume_operation_id'=o.id
            AND EXISTS (SELECT 1 FROM dsga_failed_resume_settlements s WHERE s.operation_id=retired.id))
        )
    ))
  )
)
SELECT COALESCE(json_agg(json_build_object(
  'id',id,'state',state,'image',plan->>'image','runner',plan#>>'{vm,runner_image}',
  'kernel',plan#>>'{vm,kernel_image}','nodes',plan#>'{vm,placement,allowed_node_names}',
  'qualifier',plan#>>'{vm,generic_guest,supply,qualifier_image}'
) ORDER BY id),'[]'::json)
FROM eligible;
COMMIT;`;
  const reply = kube(['-n', namespace, 'exec', metadataPod, '--', 'sh', '-ec',
    'exec psql -XqAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"', 'query', statement]);
  return JSON.parse(reply.stdout);
}

function main() {
  const {values: options} = parseArgs({options: {
    namespace: {type: 'string'}, 'api-deployment': {type: 'string'}, 'metadata-pod': {type: 'string'},
    image: {type: 'string'}, node: {type: 'string'},
  }});
  const {namespace, 'api-deployment': apiDeployment, 'metadata-pod': metadataPod, image, node} = options;
  if (![namespace, apiDeployment, metadataPod].every(value => typeof value === 'string' && namePattern.test(value))) {
    throw new Error('Supply the namespace, original API Deployment and metadata PostgreSQL Pod');
  }
  if ((image || node) && (!pinned.test(image ?? '') || !namePattern.test(node ?? ''))) {
    throw new Error('Supply both the immutable candidate image and the candidate node');
  }
  const before = catalogSnapshot(namespace, apiDeployment);
  const pins = imagePins(before.catalog, projectedOperations(namespace, metadataPod));
  const after = catalogSnapshot(namespace, apiDeployment);
  if (before.identity.some((value, i) => value !== after.identity[i])) {
    throw new Error('DSGA runtime catalog changed during image inventory');
  }
  if (image) {
    const digest = image.slice(image.lastIndexOf('@'));
    const observed = pins.filter(pin => pin.image.endsWith(digest))
      .flatMap(pin => pin.origins).filter(origin => origin.nodes === null || origin.nodes.includes(node));
    console.log(JSON.stringify({candidate: image, node, required: observed.length !== 0, origins: observed}, null, 2));
    if (observed.length) process.exitCode = 3;
  } else {
    console.log(JSON.stringify({namespace, pins}, null, 2));
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof SyntaxError ? 'The DSGA image inventory response is invalid' : error.message);
    process.exitCode = 1;
  }
}
