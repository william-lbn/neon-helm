#!/usr/bin/env python3
"""只读诊断标准站点，不自动修复、开放准入或重放操作。"""
import argparse
import json
import os
import pathlib
import subprocess
from standard_contract import input_manifest, private_state, lock_state, safe_path, verify_images


def diagnose(config_file, state):
    state = private_state(state, readonly=True)
    with lock_state(state, readonly=True):
        return _diagnose_unlocked(config_file, state)


def _diagnose_unlocked(config_file, state):
    config_file = safe_path(config_file)
    config = json.loads(config_file.read_text())
    report = json.loads(safe_path(state / 'receipt.json').read_text())
    results = []
    def result(code, ok, message):
        results.append({'code': code, 'ok': ok, 'message': message})
    result('INSTALL_RECEIPT', report.get('status')=='installed', '原安装收据必须明确完成，不能用就绪对象代替未结清的安装')
    env = dict(os.environ, KUBECONFIG=config['kubeconfig'])
    def run(*args):
        completed = subprocess.run(args, env=env, capture_output=True, timeout=60)
        if completed.returncode:
            raise RuntimeError('只读查询未确认；原始输出留在命令自身，不写入公共报告')
        return json.loads(completed.stdout)
    cluster = run('kubectl', 'get', 'namespace', 'kube-system', '-o', 'json')['metadata']['uid']
    result('CLUSTER_IDENTITY', report.get('clusterUID', cluster) == cluster, '核对本次集群 UID；历史收据可能没有绑定')
    if report.get('inputSet'):
        result('RELEASE_INPUTS', input_manifest(config_file, config) == report['inputSet'], '核对 Chart、values、目录和执行工具的原始摘要')
    else:
        result('LEGACY_RECEIPT', None, '历史验收收据仅供只读观察，不能直接用于新工具接续变更')
    releases = run(os.environ.get('HELM_BIN', 'helm'), 'list', '-A', '--all', '-o', 'json')
    for name, entry in config['releases'].items():
        found = [r for r in releases if r['name'] == entry['release'] and r['namespace'] == entry['namespace']]
        result('HELM_' + name, len(found) == 1 and found[0]['status'] == 'deployed', '发行组件应只有一个已部署的原 release')
    namespaces = set(config['namespaces'].values()) | {e['namespace'] for e in config['releases'].values()}
    objects = run('kubectl', 'get', 'deployments,statefulsets,daemonsets', '-A', '-o', 'json')['items']
    for obj in objects:
        metadata, status = obj['metadata'], obj.get('status', {})
        if metadata['namespace'] not in namespaces:
            continue
        desired = status.get('desiredNumberScheduled', 0) if obj['kind'] == 'DaemonSet' else obj['spec'].get('replicas', 1)
        ready = status.get('numberReady', 0) if obj['kind'] == 'DaemonSet' else status.get('readyReplicas', 0)
        current = status.get('observedGeneration', 0) >= metadata.get('generation', 1)
        result('WORKLOAD_' + obj['kind'] + '/' + metadata['name'], current and ready >= desired, '工作负载应观察到当前代际并达到期望就绪数')
    nodes = {n['metadata']['name']: n for n in run('kubectl', 'get', 'nodes', '-o', 'json')['items']}
    pods = run('kubectl', 'get', 'pods', '-A', '-o', 'json')
    for pod in pods['items']:
        metadata, status = pod['metadata'], pod.get('status', {})
        if metadata['namespace'] in namespaces and status.get('phase') not in ('Succeeded', 'Failed'):
            result('POD_' + metadata['namespace'] + '/' + metadata['name'], not metadata.get('deletionTimestamp') and any(c['type']=='Ready' and c['status']=='True' for c in status.get('conditions', [])), '产品与系统前置 Pod 应就绪；共享组件只报告，不自动修改')
    for host in report.get('selectedHosts', []):
        actual = nodes.get(host['name'], {})
        ready = actual.get('metadata', {}).get('uid') == host['uid'] and any(c['type'] == 'Ready' and c['status'] == 'True' for c in actual.get('status', {}).get('conditions', []))
        result('HOST_' + host['name'], ready, '原物理节点 UID 应一致且 Ready；业务预算通过原 SDK 诊断')
    hosts = [h['name'] for h in report.get('selectedHosts', [])]
    if hosts:
        tool=(pathlib.Path(__file__).resolve().parent/'host-pod-preflight.mjs').as_uri()
        code='import fs from "node:fs";import {inspectHostPodLimits} from '+json.dumps(tool)+';const input=JSON.parse(fs.readFileSync(0,"utf8"));console.log(JSON.stringify(inspectHostPodLimits(input.pods,input.hosts)));'
        checked=subprocess.run([os.environ.get('NEON_NODE_BIN','node'),'--input-type=module','-e',code],env=env,input=json.dumps({'pods':pods,'hosts':hosts}).encode(),capture_output=True,timeout=60)
        if checked.returncode:raise RuntimeError('原普通 Pod 硬限检查未确认')
        hard_limits=json.loads(checked.stdout)
        result('ORDINARY_POD_HARD_LIMITS', hard_limits['ready'], '原 Host 上所有活动普通 Pod 和 init container 都必须有有效内存硬限')
    refs = set()
    def collect(value):
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, str) and '@sha256:' in value:
            refs.add(value)
    collect(config)
    for entry in config['releases'].values():
        collect(json.loads((config_file.parent / entry['values']).read_text()))
    collect(json.loads((config_file.parent / config['catalogTemplate']).read_text()))
    try:
        verify_images(config, refs)
        result('REGISTRY_IMAGES', True, '内网仓库已确认所有声明镜像的原摘要')
    except RuntimeError:
        result('REGISTRY_IMAGES', False, '内网仓库镜像未确认；检查仓库、CA、只读权限和摘要')
    status='attention-required' if any(r['ok'] is False for r in results) else 'observed-with-limitations' if any(r['ok'] is None for r in results) else 'healthy'
    return {'status': status, 'readOnly': True, 'checks': results, 'businessE2E': 'NOT_RUN'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True)
    parser.add_argument('--state', required=True)
    args = parser.parse_args()
    report = diagnose(args.site, args.state)
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(1 if report['status'] == 'attention-required' else 0)
