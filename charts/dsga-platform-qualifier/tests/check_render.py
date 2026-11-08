#!/usr/bin/env python3
"""独立资格Job离线lint/render与只读私有输入前检；不执行部署或发布。"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import yaml

CHART = Path(__file__).resolve().parents[1]
PINS = json.loads((CHART / 'files/pg17-node-identities.json').read_text())['allowedNodeUIDs']


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def protected(path, kind='file', maximum=1024 * 1024):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and str(path) == os.path.normpath(path), 'canonical original private path required')
    require(path.resolve() == path, 'original private path may not contain symlinks')
    current = path.parent
    while True:
        info = current.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0, 'private source ancestry is not root owned')
        require(not (info.st_mode & 0o022) or current != path.parent and info.st_mode & stat.S_ISVTX, 'private source ancestry is replaceable')
        if current == current.parent:
            break
        current = current.parent
    info = path.lstat()
    require(info.st_uid == 0, 'original private source must be root owned')
    if kind == 'socket':
        require(stat.S_ISSOCK(info.st_mode) and not info.st_mode & 0o077, 'original resource socket must be private')
        return None
    require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o022 and 0 < info.st_size <= maximum, 'bounded root protected original file required')
    return path.read_bytes()


def verify_private(v, namespace, agent_manifest):
    require(v['enabled'], 'private preflight requires explicitly enabled input')
    b, inputs, uds = v['binding'], v['inputs'], v['agentResourceReadSocket']
    require(socket.gethostname() == b['nodeName'], 'private hostPath preflight must run on selected original worker')
    config_raw = protected(Path(inputs['hostDirectory']) / inputs['configFileName'], maximum=64 * 1024)
    require(digest(config_raw) == inputs['configSHA256'], 'original private config SHA mismatch')
    config = json.loads(config_raw)
    require(config['binding'] == {'namespace': namespace, 'name': b['vmName'], 'vm_uid': b['vmUID'], 'incarnation': b['incarnation']}, 'private config VM binding differs from rendered Role')
    require(config['node_name'] == b['nodeName'] and config['node_uid'] == b['nodeUID'], 'private config Node binding differs')
    require(config['report_sha256'] == inputs['reportSHA256'], 'private report selection differs')
    resource_path = uds['mountDirectory'] + '/' + uds['name']
    require(config['control_socket_path'] == resource_path, 'issuer must target actual independent resource-read socket')
    require(1 <= config['timeout_seconds'] <= 120 and v['job']['activeDeadlineSeconds'] >= config['timeout_seconds'] + 30, 'Job deadline does not cover bounded CLI startup/read')
    mount = Path(inputs['mountDirectory'])
    bodies = {}
    for field in ['report_path', 'linux_artifact_path', 'continuous_artifact_path']:
        selected = Path(config[field])
        require(selected.is_relative_to(mount), 'private report/artifact is outside original readonly input mount')
        bodies[field] = protected(Path(inputs['hostDirectory']) / selected.relative_to(mount), maximum=64 * 1024 if field == 'report_path' else 1024 * 1024)
    require(digest(bodies['report_path']) == config['report_sha256'], 'original report bytes changed')
    report = json.loads(bodies['report_path'])
    require(report['scope'] == 'neon-dsga-linux-platform-report-v1', 'model report scope cannot be used')
    require(digest(bodies['linux_artifact_path']) == report['linux_artifact_sha256'] and digest(bodies['continuous_artifact_path']) == report['continuous_artifact_sha256'], 'original certification artifacts changed')
    require(report['host_binding']['namespace'] == v['hostLease']['namespace'] and report['host_binding']['lease_name'] == v['hostLease']['name'], 'private Host Lease differs from Role')
    q = report['qualification']
    require(q['identity']['vm_uid'] == b['vmUID'] and q['incarnation'] == b['incarnation'] and q['node_name'] == b['nodeName'] and q['node_uid'] == b['nodeUID'] and q['runner_pod_name'] == b['runnerPodName'], 'private qualification original identities differ')
    require(q['runner_birth']['name'] in b['runnerConfigMapNames'], 'original Runner Birth GET permission missing')
    manifest_raw = protected(agent_manifest)
    require(digest(manifest_raw) == uds['sourceManifestSHA256'], 'actual Agent manifest SHA changed')
    documents = [x for x in yaml.safe_load_all(manifest_raw) if isinstance(x, dict)]
    ds = next((x for x in documents if x.get('kind') == 'DaemonSet' and x['metadata']['name'] == 'autoscaler-agent' and x['metadata'].get('namespace') == 'kube-system'), None)
    cm = next((x for x in documents if x.get('kind') == 'ConfigMap' and x['metadata']['name'] == 'autoscaler-agent-config' and x['metadata'].get('namespace') == 'kube-system'), None)
    require(ds is not None and cm is not None, 'actual Agent DaemonSet and runtime ConfigMap projection required')
    agent = json.loads(cm['data']['config.json'])['dsga']
    require(agent.get('resourceReadSocketPath') == resource_path and agent.get('controlSocketPath') != resource_path, 'full management socket cannot substitute resource-read endpoint')
    pod = ds['spec']['template']['spec']
    container = next(x for x in pod['containers'] if x['name'] == 'autoscaler-agent')
    mount_info = next((x for x in container.get('volumeMounts', []) if x['mountPath'] == uds['mountDirectory']), None)
    require(mount_info is not None and not mount_info.get('readOnly', False), 'actual Agent writable resource-socket mount missing')
    volume = next((x for x in pod.get('volumes', []) if x['name'] == mount_info['name']), None)
    require(volume is not None and volume.get('hostPath') == {'path': uds['hostDirectory'], 'type': 'Directory'}, 'actual Agent original hostPath mapping differs')
    protected(Path(uds['hostDirectory']) / uds['name'], kind='socket')
    return {'privateInputBindings': 'pass', 'actualAgentResourceSocketMount': 'pass', 'reportArtifactsExactSHA': 'pass', 'platformCertification': 'not-performed', 'qualificationIssued': False}


def offline_values():
    v = yaml.safe_load((CHART / 'values.yaml').read_text())
    v['enabled'] = True
    v['image'] = {'repository': 'offline.invalid/qualificationissuer', 'digest': 'sha256:' + '1' * 64, 'pullSecrets': []}
    v['binding'] = {'vmName': 'offline-vm', 'vmUID': '00000000-0000-0000-0000-000000000017', 'incarnation': 'a' * 32, 'nodeName': 'worker-118', 'nodeUID': PINS['worker-118'], 'runnerPodName': 'offline-runner', 'runnerConfigMapNames': ['offline-birth', 'offline-state', 'offline-exit', 'offline-stopped']}
    v['hostLease'] = {'namespace': 'offline-host', 'name': 'offline-host-lease'}
    v['inputs'] = {'hostDirectory': '/offline-not-deployable/input', 'mountDirectory': '/offline-not-deployable/input', 'configFileName': 'issuer.json', 'configSHA256': '2' * 64, 'reportSHA256': '3' * 64}
    v['agentResourceReadSocket'] = {'hostDirectory': '/offline-not-deployable/resource-read', 'mountDirectory': '/offline-not-deployable/resource-read', 'name': 'resource.sock', 'sourceManifestSHA256': '4' * 64}
    return v


def run_checks(output):
    output.mkdir(parents=True, exist_ok=True)
    results = []
    def invoke(name, v=None, lint=False, expect_success=True):
        path = output / (name + '.yaml')
        if v is not None:
            path.write_text(yaml.safe_dump(v, sort_keys=False))
        command = [os.environ.get('HELM_BIN', 'helm'), 'lint' if lint else 'template']
        if not lint:
            command += ['qualifier-offline']
        command += [str(CHART)]
        if not lint:
            command += ['--kube-version', '1.31.2']
        command += ['--strict'] if lint else ['--namespace', 'neon']
        if v is not None:
            command += ['--values', str(path)]
        response = subprocess.run(command, capture_output=True, text=True, timeout=20)
        (output / (name + '.stdout')).write_text(response.stdout)
        (output / (name + '.stderr')).write_text(response.stderr)
        require((response.returncode == 0) == expect_success, name + ': unexpected bounded Helm result')
        results.append({'case': name, 'expectedSuccess': expect_success, 'exit': response.returncode})
        return [d for d in yaml.safe_load_all(response.stdout) if isinstance(d, dict)] if expect_success and not lint else []
    invoke('lint-disabled', lint=True)
    require(not invoke('default-disabled'), 'default disabled must render no Kubernetes objects')
    v = offline_values()
    # Helm3.12 lint没有kube-version参数；启用路径以指定真实minor的template验证。
    docs = invoke('enabled-offline-not-deployable', v)
    require(len(docs) == 8, 'unexpected additional resources')
    job = next(d for d in docs if d['kind'] == 'Job')
    require(len(job['metadata']['name']) <= 63, 'bounded Job name')
    spec = job['spec']['template']['spec']
    require('nodeName' not in spec and spec['schedulerName'] == 'autoscale-scheduler' and spec['nodeSelector'] == {'kubernetes.io/hostname': 'worker-118'}, 'Job bypassed original Host allocator')
    require(spec['securityContext']['runAsUser'] == 0 and 'fsGroup' not in spec['securityContext'], 'original root inode ownership must remain unchanged')
    require(not spec['hostNetwork'] and not spec['hostPID'] and not spec['hostIPC'] and not spec.get('initContainers') and len(spec['containers']) == 1, 'unexpected host capabilities or unbounded containers')
    container = spec['containers'][0]
    require(container['args'] == ['--config', v['inputs']['mountDirectory'] + '/' + v['inputs']['configFileName']] and 'command' not in container, 'new unsupported CLI arguments or shell wrapper')
    require(container['image'].endswith('@sha256:' + '1' * 64) and container['resources']['limits']['memory'] == '256Mi', 'digest or hard memory limit missing')
    require(container['securityContext']['capabilities']['drop'] == ['ALL'] and not container['securityContext']['allowPrivilegeEscalation'] and container['securityContext']['readOnlyRootFilesystem'], 'unexpected workload privilege')
    mounts = {x['name']: x for x in container['volumeMounts']}
    for name in ['original-inputs', 'original-agent-resource-read']:
        require(mounts[name]['readOnly'] and 'subPath' not in mounts[name], 'original source mount must preserve readonly directory/inode')
    require(all(x.get('hostPath', {}).get('type') in [None, 'Directory'] for x in spec['volumes']), 'host source directories must preexist')
    roles = [d for d in docs if d['kind'] in ['Role', 'ClusterRole']]
    for role in roles:
        for rule in role['rules']:
            require(not set(rule['verbs']) & {'update', 'patch', 'delete', 'deletecollection', 'watch', 'bind', 'escalate', 'impersonate', '*', 'apply'}, 'issuer has mutation or wildcard authority')
            require('*' not in rule['resources'] and '*' not in rule['apiGroups'], 'wildcard RBAC resource')
    create = [r for d in roles for r in d['rules'] if 'create' in r['verbs']]
    require(len(create) == 1 and create[0]['resources'] == ['configmaps'] and 'resourceNames' not in create[0], 'CREATE name restriction must not be falsely advertised')
    cluster = next(d for d in roles if d['kind'] == 'ClusterRole')
    require(cluster['rules'] == [{'apiGroups': [''], 'resources': ['nodes'], 'resourceNames': ['worker-118'], 'verbs': ['get']}, {'apiGroups': [''], 'resources': ['pods'], 'verbs': ['list']}], 'unexpected cluster scope')
    owner_name = 'dsga-' + digest(b'neon-dsga-lease-binding-v1\0' + json.dumps(['neon', v['binding']['vmName'], v['binding']['vmUID'], v['binding']['incarnation']], separators=(',', ':')).encode())[:56]
    require(any(r.get('resources') == ['leases'] and r.get('resourceNames') == [owner_name] for d in roles for r in d['rules']), 'owner Lease content-address differs from Go journal contract')
    changes = {
        'missing-image': lambda x: x['image'].update(repository=''),
        'tag-not-digest': lambda x: x['image'].update(digest='latest'),
        'uppercase-digest': lambda x: x['image'].update(digest='sha256:' + 'A' * 64),
        'excluded-node': lambda x: x['binding'].update(nodeName='ubuntu'),
        'different-node-uid': lambda x: x['binding'].update(nodeUID='00000000-0000-0000-0000-000000000000'),
        'missing-vm-uid': lambda x: x['binding'].update(vmUID=''),
        'wrong-incarnation': lambda x: x['binding'].update(incarnation='A' * 32),
        'missing-runner-source': lambda x: x['binding'].update(runnerConfigMapNames=['offline-birth']),
        'missing-host-lease': lambda x: x['hostLease'].update(name=''),
        'input-root-mount': lambda x: x['inputs'].update(hostDirectory='/'),
        'input-relative-path': lambda x: x['inputs'].update(hostDirectory='relative'),
        'input-parent-traversal': lambda x: x['inputs'].update(hostDirectory='/private/../other'),
        'missing-report-sha': lambda x: x['inputs'].update(reportSHA256=''),
        'missing-config-sha': lambda x: x['inputs'].update(configSHA256=''),
        'missing-resource-socket': lambda x: x['agentResourceReadSocket'].update(hostDirectory=''),
        'missing-agent-proof': lambda x: x['agentResourceReadSocket'].update(sourceManifestSHA256=''),
        'socket-name-traversal': lambda x: x['agentResourceReadSocket'].update(name='../control.sock'),
        'shadowed-mount': lambda x: x['agentResourceReadSocket'].update(mountDirectory=x['inputs']['mountDirectory']),
        'foreign-scheduler': lambda x: x['placement'].update(schedulerName='default-scheduler'),
        'missing-memory-limit': lambda x: x['resources']['limits'].update(memory=None),
        'zero-memory-limit': lambda x: x['resources']['limits'].update(memory='0Mi'),
        'arbitrary-sidecar': lambda x: x.update(extraContainers=[{'name': 'bypass'}]),
        'arbitrary-node-name': lambda x: x.update(nodeName='worker-118'),
        'nested-private-input-source': lambda x: x['agentResourceReadSocket'].update(hostDirectory=x['inputs']['hostDirectory'] + '/socket'),
        'nested-private-input-mount': lambda x: x['agentResourceReadSocket'].update(mountDirectory=x['inputs']['mountDirectory'] + '/socket'),
        'shadow-api-token': lambda x: x['inputs'].update(mountDirectory='/var/run/secrets'),
        'unbounded-deadline': lambda x: x['job'].update(activeDeadlineSeconds=0),
    }
    for name, change in changes.items():
        changed = copy.deepcopy(v)
        change(changed)
        invoke(name, changed, expect_success=False)
    report = {'scope': 'offline-render-contract-only', 'results': results, 'positiveDocuments': len(docs), 'negativeCases': len(changes), 'qualificationIssued': False, 'deploymentExecuted': False, 'actualAgentSocketMounted': False, 'actualPlatformCertified': False}
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--verify-private-inputs', action='store_true')
    parser.add_argument('--values', type=Path)
    parser.add_argument('--agent-manifest', type=Path)
    parser.add_argument('--namespace')
    args = parser.parse_args()
    if args.verify_private_inputs:
        require(args.values is not None and args.agent_manifest is not None and args.namespace, 'explicit original values, namespace and Agent manifest required')
        print(json.dumps(verify_private(yaml.safe_load(args.values.read_text()), args.namespace, args.agent_manifest), indent=2))
    else:
        with tempfile.TemporaryDirectory(prefix='qualifier-offline-') as temporary:
            output = args.output_dir or Path(temporary)
            result = run_checks(output)
            print(json.dumps({'cases': len(result['results']), 'negativeCases': result['negativeCases'], 'qualificationIssued': False, 'deploymentExecuted': False, 'result': str(output / 'result.json')}, indent=2))


if __name__ == '__main__':
    main()
