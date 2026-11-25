#!/usr/bin/env python3
"""从无站点绑定的发行模板生成独立站点，拒绝覆盖既有输入。"""
import argparse
import copy
import json
import os
import pathlib
import re
from standard_contract import atomic_json, registry_options, safe_path


def generate(settings, output, profile=None):
    os.umask(0o077)
    profile = pathlib.Path(profile or pathlib.Path(__file__).resolve().parents[1] / 'profiles/standard-site')
    required = ('name', 'region', 'objectStoreRegion', 'kubernetesMinor', 'kubeconfig', 'registry', 'registryAccess', 'storageClass', 'storageRoots', 'clusterDomain', 'workloadNamespace', 'platformNamespace', 'computeNodeSelector', 'systemBytes', 'allowLabHTTPObjectStorage')
    if set(required) - settings.keys():
        raise RuntimeError('缺少站点输入：' + ', '.join(sorted(set(required) - settings.keys())))
    registry_options(settings)
    for key in ('name', 'region', 'workloadNamespace', 'platformNamespace', 'storageClass'):
        if not isinstance(settings[key], str) or len(settings[key]) > 63 or not re.fullmatch('[a-z0-9]([-a-z0-9]*[a-z0-9])?', settings[key]):
            raise RuntimeError('站点名称、命名空间和存储类必须为有效 DNS 名称')
    if not settings['platformNamespace'].startswith('neon-control-') or settings['platformNamespace'] == settings['workloadNamespace']:
        raise RuntimeError('当前协议要求独立的 neon-control-* 平台命名空间')
    if not pathlib.Path(settings['kubeconfig']).is_absolute():
        raise RuntimeError('kubeconfig 必须为显式绝对路径')
    if not settings['storageRoots'] or any(not isinstance(x, str) or not x.startswith('/') or x == '/' or '..' in pathlib.PurePosixPath(x).parts for x in settings['storageRoots']):
        raise RuntimeError('必须声明独占本地卷的实际父目录，禁止使用根目录')
    if not isinstance(settings['computeNodeSelector'], dict) or not settings['computeNodeSelector'] or not all(isinstance(k, str) and isinstance(v, str) for k, v in settings['computeNodeSelector'].items()):
        raise RuntimeError('必须显式提供 Compute 节点标签选择器')
    if not re.fullmatch('[1-9][0-9]*', str(settings['systemBytes'])) or int(settings['systemBytes']) > 2**63-1:
        raise RuntimeError('systemBytes 必须为明确的正整数字节数')
    if not isinstance(settings['allowLabHTTPObjectStorage'], bool):
        raise RuntimeError('必须显式选择内网对象存储 HTTP 策略')
    if settings['allowLabHTTPObjectStorage'] is not True:
        raise RuntimeError('本发行采用内置 HTTP 对象存储；内网使用需显式允许 allowLabHTTPObjectStorage，完整 TLS 方案另行认证')
    if not re.fullmatch('[a-z0-9]([-a-z0-9.]*[a-z0-9])?', settings['clusterDomain']) or '..' in settings['clusterDomain'] or len(settings['clusterDomain']) > 253:
        raise RuntimeError('必须提供有效的集群 DNS 后缀')
    if settings['workloadNamespace'] in ('default','kube-system','kube-public','kube-node-lease','neonvm-system','cert-manager'):
        raise RuntimeError('产品必须使用独占命名空间，不能与平台共享')
    if not re.fullmatch('[a-z0-9-]+',settings['objectStoreRegion']):
        raise RuntimeError('必须声明对象存储区域')
    for component in ('neonvm','autoscaler'):
        compatibility=json.loads((profile/'values'/ (component+'.json')).read_text())['compatibility']
        if str(settings['kubernetesMinor'])!=compatibility['expectedKubernetesMinor']:
            raise RuntimeError('目标 Kubernetes 小版本尚不属于本发行的资格范围，不能仅修改版本值绕过')
    console=settings.get('consoleService',{'type':'ClusterIP'})
    if not isinstance(console,dict) or console.get('type') not in ('ClusterIP','NodePort') or set(console)-{'type','nodePort'}:
        raise RuntimeError('consoleService 只能声明 ClusterIP 或明确的 NodePort')
    if console['type']=='NodePort' and (not isinstance(console.get('nodePort'),int) or not 30000<=console['nodePort']<=32767):
        raise RuntimeError('当前 Chart 的 NodePort 模式要求显式声明 30000..32767 端口；默认 ClusterIP 不占固定节点端口')
    project = settings.get('imageProject', 'neon')
    if not re.fullmatch('[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*', project):
        raise RuntimeError('镜像项目路径无效')
    config = json.loads((profile / 'site.json').read_text())
    config.update({k: copy.deepcopy(settings[k]) for k in ('name', 'kubeconfig', 'registry', 'registryAccess', 'storageRoots', 'clusterDomain', 'allowLabHTTPObjectStorage')})
    config['namespaces'].update(workload=settings['workloadNamespace'], platform=settings['platformNamespace'])
    config['computeNodeSelector'] = settings['computeNodeSelector']
    config['kubernetesMinor'] = str(settings['kubernetesMinor'])
    config['hostPolicy']['systemBytes'] = str(settings['systemBytes'])
    # 发行模板中的摘要保持不变；地址映射不等于搬运镜像或重新认证平台能力。
    prefix = settings['registry'] + '/' + project + '/'
    def rewrite(value):
        if isinstance(value, dict):
            return {k: settings['storageClass'] if k in ('storageClass', 'storageClassName') else rewrite(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        if isinstance(value, str):
            return value.replace('registry.invalid/neon/', prefix)
        return value
    output = safe_path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        for file in [profile / config['catalogTemplate']] + [profile / entry['values'] for entry in config['releases'].values()]:
            value = rewrite(json.loads(file.read_text()))
            if file == profile / config['catalogTemplate']:
                for release in value['releases']:
                    release['region'] = settings['region']
            elif file.name=='core.json':value['minio']['region']=settings['objectStoreRegion']
            elif file.name=='pageserver.json':value['config'].update(availabilityZone=settings.get('availabilityZone',settings['region']),objectStoreRegion=settings['objectStoreRegion'])
            elif file.name=='control.json':value['service'].update(console)
            atomic_json(output / file.relative_to(profile), value)
        for entry in config['releases'].values():
            entry['chart'] = str((profile / entry['chart']).resolve())
        for name in ('metadata', 'adapter', 'core', 'pageserver', 'gateway', 'control'):
            config['releases'][name]['namespace'] = settings['workloadNamespace']
        config['releases']['runtime-access']['namespace'] = settings['platformNamespace']
        atomic_json(output / 'site.json', rewrite(config))
    except Exception:
        # 保留不完整现场，不覆盖或删除操作者输入；尚未对 Kubernetes 产生变更。
        raise
    return output / 'site.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(json.dumps({'status': 'generated', 'site': str(generate(json.loads(pathlib.Path(args.config).read_text()), args.out)), 'clusterChanged': False}, ensure_ascii=False))
