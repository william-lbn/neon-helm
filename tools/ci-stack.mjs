import fs from 'node:fs';
import path from 'node:path';
import {root, readJSON, validatePlan, documents, helm} from './lib.mjs';
import {ciValues} from './ci-values.mjs';
import {checkChartCatalog} from './chart-catalog.mjs';
import {validateResourceOwnership} from './resource-ownership.mjs';

const output = path.join(root, 'artifacts/stack-contracts');
fs.mkdirSync(output, {recursive: true});
const plan = validatePlan(readJSON('stack/stack.json'));
const kubeVersion = process.env.HELM_STACK_KUBE_VERSION || '1.31.2';
const scopes = {'cert-manager.io/Certificate': 'Namespaced', 'cert-manager.io/Issuer': 'Namespaced', 'cert-manager.io/ClusterIssuer': 'Cluster'};
function render(step) {
  const file = path.join(output, step.release + '.json');
  fs.writeFileSync(file, JSON.stringify(ciValues(step.chart)));
  const result = helm(['template', step.release, 'charts/' + step.chart, '-n', step.namespace, '--include-crds', '--kube-version', kubeVersion, '-f', file], {timeout: 60000});
  fs.writeFileSync(path.join(output, step.release + '.yaml'), result.stdout);
  return {release: step.release, namespace: step.namespace, objects: documents(result.stdout)};
}
const batches = plan.steps.map(render);
const result = {result: 'pass', catalog: checkChartCatalog(), kubernetesRenderVersion: kubeVersion, stack: validateResourceOwnership(batches, {scopes}), deployed: false, qualificationIssued: false};
fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result));
