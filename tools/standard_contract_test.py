"""验证危险边界：输入漂移、集群切换、符号链接、只读观察与仓库认证。"""
import argparse
import hashlib
import http.server
import importlib.util
import json
import os
import pathlib
import tempfile
import threading
import unittest
import shutil
import ssl
import subprocess
from unittest.mock import patch
from standard_contract import OperationContract, atomic_json, input_manifest, lock_state, private_state, verify_images


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), pathlib.Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InputContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        (self.root / 'chart').mkdir()
        (self.root / 'tools').mkdir()
        self.config = {'catalogTemplate': 'catalog.json', 'releases': {'core': {'values': 'values.json', 'chart': 'chart'}}}
        for file, text in [('site.json', json.dumps(self.config)), ('catalog.json', '{}'), ('values.json', '{}'), ('chart/template.yaml', 'kind: Service'), ('tools/action.py', '# 原工具')]:
            (self.root / file).write_text(text)
        self.file, self.tools = self.root / 'site.json', self.root / 'tools/action.py'

    def contract(self, report=None):
        return OperationContract(self.file, self.config, report if report is not None else {}, self.tools, fresh=not bool(report))

    def test_each_referenced_input_change_blocks_continuation(self):
        for file in ('site.json', 'catalog.json', 'values.json', 'chart/template.yaml', 'tools/action.py'):
            with self.subTest(file=file):
                original = (self.root / file).read_bytes()
                contract = self.contract()
                (self.root / file).write_bytes(original + b' ')
                with self.assertRaisesRegex(RuntimeError, '输入'):
                    contract.check('cluster-a')
                (self.root / file).write_bytes(original)

    def test_changed_cluster_cannot_continue(self):
        contract = self.contract()
        contract.check('cluster-a')
        with self.assertRaisesRegex(RuntimeError, '集群'):
            contract.check('cluster-b')

    def test_resume_checks_complete_manifest(self):
        report = {}
        self.contract(report)
        report['steps'] = {'installed': {'status': 'completed'}}
        self.contract(report)
        (self.root / 'chart/new.yaml').write_text('kind: Secret')
        with self.assertRaises(RuntimeError):
            self.contract(report)

    def test_legacy_mutation_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, '历史收据'):
            self.contract({'steps': {'submitted': {}}})
        with self.assertRaisesRegex(RuntimeError, '历史收据'):
            self.contract({'status':'installed','steps':{}})

    def test_parent_symlink_rejected_before_resolve(self):
        actual = self.root / 'real'
        actual.mkdir(mode=0o700)
        link = self.root / 'link'
        link.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            private_state(link / 'nested')
        self.assertFalse((actual / 'nested').exists())

    def test_symlink_lock_and_receipt_cannot_overwrite_target(self):
        state = private_state(self.root / 'state')
        target = self.root / 'unrelated'
        target.write_text('preserve')
        for name in ('lock', 'receipt.json'):
            (state / name).symlink_to(target)
            with self.assertRaises(RuntimeError):
                lock_state(state) if name == 'lock' else atomic_json(state / name, {'changed': True})
            (state / name).unlink()
        self.assertEqual(target.read_text(), 'preserve')

    def test_inspect_does_not_create_state(self):
        with self.assertRaises(FileNotFoundError):
            private_state(self.root / 'absent', readonly=True)
        self.assertFalse((self.root / 'absent').exists())

    def test_install_inspect_is_offline_and_preserves_receipt_bytes(self):
        state = private_state(self.root / 'state')
        lock_state(state).close()
        receipt = {'inputSHA256': hashlib.sha256(self.file.read_bytes()).hexdigest(), 'status': 'installed', 'steps': {}}
        atomic_json(state / 'receipt.json', receipt)
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in state.iterdir()}
        with patch('subprocess.run', side_effect=AssertionError('只读离线检查不能执行命令')):
            site = load('standard-site').Site(argparse.Namespace(action='inspect', site=str(self.file), state=str(state)))
        site.lock.close()
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in state.iterdir()})


class RegistryContract(unittest.TestCase):
    def setUp(self):
        owner = self
        self.auth, self.wrong_digest, self.external_realm, self.redirect = False, False, False, False
        self.requests = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_HEAD(self):
                owner.requests.append((self.command, self.path))
                if owner.redirect:
                    self.send_response(302)
                    self.send_header('Location', 'http://untrusted.invalid/collect')
                elif owner.auth and self.headers.get('Authorization') != 'Bearer read-only-fixture':
                    self.send_response(401)
                    realm = 'http://untrusted.invalid/token' if owner.external_realm else 'http://' + owner.registry + '/token'
                    self.send_header('WWW-Authenticate', 'Bearer realm="' + realm + '",service="generic-registry"')
                else:
                    self.send_response(200)
                    self.send_header('Docker-Content-Digest', 'sha256:' + ('b' if owner.wrong_digest else 'a') * 64)
                self.end_headers()
            def do_GET(self):
                owner.requests.append((self.command, self.path))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"token":"read-only-fixture"}')
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.registry = '127.0.0.1:' + str(server.server_port)
        self.config = {'registry': self.registry, 'registryAccess': {'scheme': 'http', 'allowPlainHTTP': True}}
        self.ref = self.registry + '/product/component@sha256:' + 'a' * 64

    def test_anonymous_v2_without_harbor_specific_token_endpoint(self):
        self.assertEqual(verify_images(self.config, [self.ref]), [self.ref])
        self.assertEqual(len(self.requests), 1)

    def test_bearer_challenge_uses_declared_same_origin_and_pull_scope(self):
        self.auth = True
        verify_images(self.config, [self.ref])
        self.assertEqual([r[0] for r in self.requests], ['HEAD', 'GET', 'HEAD'])
        self.assertIn('scope=repository%3Aproduct%2Fcomponent%3Apull', self.requests[1][1])

    def test_untrusted_token_origin_never_contacted(self):
        self.auth = self.external_realm = True
        with self.assertRaisesRegex(RuntimeError, '同源'):
            verify_images(self.config, [self.ref])
        self.assertEqual(len(self.requests), 1)

    def test_wrong_digest_rejected(self):
        self.wrong_digest = True
        with self.assertRaisesRegex(RuntimeError, '摘要'):
            verify_images(self.config, [self.ref])

    def test_http_requires_explicit_opt_in(self):
        self.config['registryAccess'].pop('allowPlainHTTP')
        with self.assertRaisesRegex(RuntimeError, '显式'):
            verify_images(self.config, [self.ref])
        self.assertFalse(self.requests)

    def test_redirect_never_followed(self):
        self.redirect = True
        with self.assertRaisesRegex(RuntimeError, '重定向'):
            verify_images(self.config, [self.ref])
        self.assertEqual(len(self.requests), 1)

    def test_external_or_mutable_reference_never_contacted(self):
        for ref in ('other.invalid/product/image@sha256:' + 'a'*64, self.registry + '/product/image:latest'):
            with self.assertRaises(RuntimeError):
                verify_images(self.config, [ref])
        self.assertFalse(self.requests)

    def test_private_registry_requires_both_explicit_credentials(self):
        self.config['registryAccess'].update(usernameEnv='NEON_TEST_REGISTRY_USER', passwordEnv='NEON_TEST_REGISTRY_PASSWORD')
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, '环境变量'):
            verify_images(self.config, [self.ref])
        self.assertFalse(self.requests)

    def test_https_private_ca_is_verified_and_never_downgraded(self):
        with tempfile.TemporaryDirectory() as directory:
            key, cert = pathlib.Path(directory)/'key', pathlib.Path(directory)/'ca.crt'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1'],check=True,capture_output=True,timeout=20)
            class Handler(http.server.BaseHTTPRequestHandler):
                def log_message(self, *args):pass
                def do_HEAD(self):
                    self.send_response(200);self.send_header('Docker-Content-Digest','sha256:'+'a'*64);self.end_headers()
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
            server.socket = context.wrap_socket(server.socket,server_side=True)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                registry='127.0.0.1:'+str(server.server_port);ref=registry+'/project/image@sha256:'+'a'*64
                config={'registry':registry,'registryAccess':{'scheme':'https','caFile':str(cert)}}
                self.assertEqual(verify_images(config,[ref]),[ref])
                config['registryAccess'].pop('caFile')
                with self.assertRaisesRegex(RuntimeError,'未确认'):verify_images(config,[ref])
            finally:server.shutdown();server.server_close()


class SiteGeneration(unittest.TestCase):
    def test_two_independent_sites_preserve_digest_and_do_not_reuse_addresses(self):
        module = load('standard-init')
        original = pathlib.Path(__file__).resolve().parents[1] / 'profiles/standard-site'
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for number in (1, 2):
                settings = json.loads((original/'site-input.example.json').read_text())
                settings.update(name='site-'+str(number), registry='registry-'+str(number)+'.invalid:5000',storageClass='storage-'+str(number),workloadNamespace='product-'+str(number),platformNamespace='neon-control-'+str(number),computeNodeSelector={'example/pool':str(number)},allowLabHTTPObjectStorage=True)
                output = root / str(number)
                file = module.generate(settings, output)
                generated = json.loads(file.read_text())
                self.assertEqual(generated['registry'],settings['registry'])
                self.assertEqual(generated['computeNodeSelector'],settings['computeNodeSelector'])
                site=object.__new__(load('standard-site').Site);site.config=generated;site.ns=generated['namespaces'];site.entries=generated['releases'];site.domain=generated['clusterDomain'];site.values={name:json.loads((output/entry['values']).read_text()) for name,entry in site.entries.items()};site.wireNamespaces()
                wired=json.dumps(site.values)
                self.assertNotIn('.neon.svc',wired);self.assertNotIn('neon-control-runtime',wired)
                self.assertEqual(site.values['control']['dsga']['nodeReadClusterRole'],site.values['runtime-access']['nodeReadClusterRole'])
                for entry in generated['releases'].values():
                    value=(output/entry['values']).read_text()
                    self.assertNotIn('10.11.',value)
                    self.assertNotIn('registry.invalid/neon/',value)
                    self.assertNotIn('"local-path"',value)
                catalog=json.loads((output/generated['catalogTemplate']).read_text())
                old=json.loads((original/generated['catalogTemplate']).read_text())
                self.assertEqual(catalog['releases'][0]['creation']['image'].split('@')[-1],old['releases'][0]['creation']['image'].split('@')[-1])
                with self.assertRaises(FileExistsError):module.generate(settings,output)

    def test_missing_or_unsafe_inputs_fail_before_output_creation(self):
        module=load('standard-init')
        profile=pathlib.Path(__file__).resolve().parents[1]/'profiles/standard-site'
        settings=json.loads((profile/'site-input.example.json').read_text());settings['allowLabHTTPObjectStorage']=True
        with tempfile.TemporaryDirectory() as directory:
            output=pathlib.Path(directory)/'site'
            for change in ({'computeNodeSelector':{}},{'storageRoots':['/']},{'registry':'10.0.0.1:5000/path'},{'platformNamespace':'default'},{'allowLabHTTPObjectStorage':False},{'clusterDomain':'bad..domain'},{'kubernetesMinor':'999'},{'consoleService':{'type':'NodePort'}}):
                with self.subTest(change=change),self.assertRaises(RuntimeError):module.generate(dict(settings,**change),output)
                self.assertFalse(output.exists())


class ReadOnlyDiagnosis(unittest.TestCase):
    def test_wrong_cluster_and_pending_system_pod_report_without_writes(self):
        module=load('standard-doctor')
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);state=private_state(root/'state');lock_state(state).close()
            config={'kubeconfig':'/explicit/cluster','registry':'registry.invalid','namespaces':{'workload':'product','agent':'kube-system'},'catalogTemplate':'catalog.json','releases':{'core':{'release':'core','namespace':'product','values':'values.json'}}}
            for name,value in [('site.json',config),('values.json',{}),('catalog.json',{}),('state/receipt.json',{'status':'installed','clusterUID':'original-cluster','steps':{}})]:atomic_json(root/name,value)
            before=(state/'receipt.json').read_bytes();modified=(state/'receipt.json').stat().st_mtime_ns;calls=[]
            def run(args,**kwargs):
                calls.append(args)
                if args[0]=='helm':value=[{'name':'core','namespace':'product','status':'deployed'}]
                elif args[2]=='namespace':value={'metadata':{'uid':'different-cluster'}}
                elif args[2]=='pods':value={'items':[{'metadata':{'namespace':'kube-system','name':'network-pod'},'status':{'phase':'Pending'}}]}
                else:value={'items':[]}
                return subprocess.CompletedProcess(args,0,json.dumps(value).encode(),b'')
            with patch.object(module.subprocess,'run',side_effect=run),patch.object(module,'verify_images',return_value=[]):report=module.diagnose(root/'site.json',state)
            self.assertEqual(report['status'],'attention-required')
            failed={r['code'] for r in report['checks'] if r['ok'] is False}
            self.assertIn('CLUSTER_IDENTITY',failed);self.assertIn('POD_kube-system/network-pod',failed)
            self.assertTrue(all(c[0]=='helm' and c[1]=='list' or c[0]=='kubectl' and c[1]=='get' for c in calls))
            self.assertEqual(before,(state/'receipt.json').read_bytes());self.assertEqual(modified,(state/'receipt.json').stat().st_mtime_ns)

    def test_registry_failure_precedes_any_preflight_cluster_mutation(self):
        module=load('standard-site')
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);(root/'catalog.json').write_text('{}')
            site=object.__new__(module.Site);site.base=root;site.config={'kubernetesMinor':'36','catalogTemplate':'catalog.json','toolsImage':'registry.invalid/p/image@sha256:'+'a'*64};site.values={}
            with patch.object(site,'kube',return_value={'serverVersion':{'major':'1','minor':'36','gitVersion':'v1.36.6'}}),patch.object(site,'checkImages',side_effect=RuntimeError('registry unavailable')),patch.object(site,'command',side_effect=AssertionError('不得先操作集群')):
                with self.assertRaisesRegex(RuntimeError,'registry unavailable'):site.preflight()

    def test_node_selector_filters_observed_hosts_before_binding(self):
        module=load('standard-site');site=object.__new__(module.Site);site.config={'computeNodeSelector':{'example/pool':'selected'}}
        nodes=[]
        for name,pool in [('arbitrary-worker-a','selected'),('arbitrary-worker-b','other')]:
            nodes.append({'metadata':{'name':name,'uid':name+'-uid','labels':{'kubernetes.io/os':'linux','kubernetes.io/arch':'amd64','example/pool':pool}},'spec':{},'status':{'allocatable':{'neonvm/kvm':'1'},'conditions':[{'type':'Ready','status':'True'}]}})
        with patch.object(site,'kube',return_value={'items':nodes}):self.assertEqual([n['metadata']['name'] for n in site.eligibleNodes()],['arbitrary-worker-a'])


if __name__ == '__main__':
    unittest.main()
