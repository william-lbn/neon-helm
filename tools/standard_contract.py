"""标准部署共用合同：私有状态、完整输入、原集群身份和只读镜像检查。"""
import contextlib
import base64
import fcntl
import hashlib
import json
import os
import pathlib
import re
import ssl
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(path):
    """先检查原始路径的每级目录，不能先 resolve 再判断链接。"""
    path = pathlib.Path(os.path.abspath(path))
    for item in (*reversed(path.parents), path):
        if item.is_symlink():
            raise RuntimeError('状态或发行输入不能经过符号链接')
    return path


def private_state(path, readonly=False):
    path = safe_path(path)
    if not readonly:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError('状态目录必须由当前用户独占，权限为 0700')
    return path


def lock_state(path, readonly=False):
    flags = os.O_RDONLY if readonly else os.O_RDWR | os.O_CREAT
    fd = os.open(safe_path(path / 'lock'), flags | os.O_NOFOLLOW, 0o600)
    file = os.fdopen(fd, 'r' if readonly else 'r+')
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        file.close()
        raise RuntimeError('状态锁必须是当前用户独占的普通文件')
    fcntl.flock(fd, (fcntl.LOCK_SH if readonly else fcntl.LOCK_EX) | fcntl.LOCK_NB)
    return file


def atomic_json(path, value):
    path = safe_path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(value, file, indent=2, ensure_ascii=False)
            file.write('\n')
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return path


def input_manifest(site_file, config, tools=None):
    """散列内容，不记录凭据；Chart、引用值、目录、执行工具和发行二进制均入锁。"""
    site_file = safe_path(site_file)
    base = site_file.parent
    tools = pathlib.Path(tools or __file__).resolve().parent
    files = {'site': site_file, 'catalog': base / config['catalogTemplate']}
    for name in ('standard-source-lock.json', 'SHA256SUMS'):
        path = tools.parent / name
        if path.exists():
            files['release/' + name] = path
    ca_file = config.get('registryAccess', {}).get('caFile')
    if ca_file:
        if not pathlib.Path(ca_file).is_absolute():
            raise RuntimeError('仓库 CA 必须为显式绝对路径')
        files['registry-ca'] = pathlib.Path(ca_file)
    for name, entry in sorted(config['releases'].items()):
        files['values/' + name] = base / entry['values']
        chart = safe_path(base / entry['chart'])
        if not chart.is_dir():
            raise RuntimeError('发行 Chart 目录不存在：' + name)
        for path in sorted(chart.rglob('*')):
            safe_path(path)
            if path.is_file():
                files['charts/' + name + '/' + path.relative_to(chart).as_posix()] = path
    for label, directory in [('tools', tools), ('bin', tools.parent / 'bin')]:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob('*')):
            safe_path(path)
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                files[label + '/' + path.relative_to(directory).as_posix()] = path
    manifest = {name: sha(safe_path(path).read_bytes()) for name, path in sorted(files.items())}
    return {'sha256': sha(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()), 'files': manifest}


class OperationContract:
    def __init__(self, site_file, config, report, tools=None, fresh=False):
        self.site_file, self.config, self.report, self.tools = site_file, config, report, tools
        current = input_manifest(site_file, config, tools)
        previous = report.get('inputSet')
        if previous is None and not fresh:
            raise RuntimeError('历史收据没有完整输入锁，仅可只读检查；不能直接接续变更')
        if previous is not None and previous != current:
            raise RuntimeError('原发行输入已变化，禁止在原操作中混用新 Chart、values 或工具')
        report['inputSet'] = current

    def check(self, cluster_uid):
        if input_manifest(self.site_file, self.config, self.tools) != self.report['inputSet']:
            raise RuntimeError('发行输入在执行期间发生变化，已停止后续变更')
        previous = self.report.get('clusterUID')
        if not cluster_uid or previous is not None and previous != cluster_uid:
            raise RuntimeError('目标集群身份变化，禁止继续原操作')
        self.report['clusterUID'] = cluster_uid


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('镜像检查禁止跨端点重定向')


def registry_options(config):
    registry = config['registry']
    # registry 字段仅为主机与可选端口，仓库项目属于镜像路径。
    if not re.fullmatch(r'[a-zA-Z0-9.-]+(?::[0-9]{1,5})?', registry):
        raise RuntimeError('请显式配置内网镜像仓库主机和端口')
    options = config.get('registryAccess')
    if not isinstance(options, dict) or options.get('scheme') not in ('http', 'https'):
        raise RuntimeError('必须显式声明 registryAccess.scheme；不再隐式使用 HTTP')
    if options['scheme'] == 'http' and options.get('allowPlainHTTP') is not True:
        raise RuntimeError('内网明文仓库必须显式允许 allowPlainHTTP')
    return registry, options


def verify_images(config, refs):
    """只做 V2 HEAD/令牌 GET；不推送、不降级 TLS、不读取容器运行时密码。"""
    registry, options = registry_options(config)
    base = options['scheme'] + '://' + registry
    context = ssl.create_default_context(cafile=options.get('caFile'))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=context))
    deadline = time.monotonic() + min(max(float(options.get('timeoutSeconds', 120)), 1), 300)
    accept = 'application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json'
    credentials = {}
    if options.get('usernameEnv') or options.get('passwordEnv'):
        names = [options.get('usernameEnv', ''), options.get('passwordEnv', '')]
        if not all(re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', n) and os.environ.get(n) for n in names):
            raise RuntimeError('声明的仓库只读认证环境变量缺失')
        credentials['Authorization'] = 'Basic ' + base64.b64encode((os.environ[names[0]] + ':' + os.environ[names[1]]).encode()).decode()

    def request(url, headers=None, method='GET'):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('镜像检查超过本次总时限')
        return opener.open(urllib.request.Request(url, headers=headers or {}, method=method), timeout=min(20, remaining))

    verified = []
    try:
        for ref in sorted(set(refs)):
            match = re.fullmatch(re.escape(registry) + r'/([a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*)@(sha256:[a-f0-9]{64})', ref)
            if not match:
                raise RuntimeError('所有镜像必须来自声明的仓库，且锁定 sha256 摘要')
            repo, pin = match.groups()
            url = base + '/v2/' + repo + '/manifests/' + pin
            headers = dict(credentials, Accept=accept)
            try:
                response = request(url, headers, 'HEAD')
            except urllib.error.HTTPError as error:
                challenge = error.headers.get('WWW-Authenticate', '')
                status = error.code
                error.close()
                if status != 401 or not challenge.lower().startswith('bearer '):
                    raise RuntimeError('镜像不可读，请检查仓库存在性、权限和摘要') from None
                fields = dict(re.findall(r'([a-zA-Z]+)="([^"\r\n]*)"', challenge[7:]))
                realm = urllib.parse.urlsplit(fields.get('realm', ''))
                # 令牌端点必须与仓库同源；其他认证拓扑应另行显式评审，不向任意地址发令牌请求。
                if realm.scheme != options['scheme'] or realm.netloc != registry or realm.username or realm.fragment:
                    raise RuntimeError('仓库令牌端点必须与显式仓库同源')
                query = urllib.parse.parse_qsl(realm.query) + [('service', fields.get('service', registry)), ('scope', 'repository:' + repo + ':pull')]
                token_url = urllib.parse.urlunsplit((realm.scheme, realm.netloc, realm.path, urllib.parse.urlencode(query), ''))
                with contextlib.closing(request(token_url, credentials)) as issued:
                    payload = issued.read(1024 * 1024 + 1)
                if len(payload) > 1024 * 1024:
                    raise RuntimeError('仓库令牌响应过大')
                value = json.loads(payload)
                token = value.get('token') or value.get('access_token')
                if not isinstance(token, str) or not token or '\n' in token or '\r' in token:
                    raise RuntimeError('仓库未返回可用的只读令牌')
                headers['Authorization'] = 'Bearer ' + token
                response = request(url, headers, 'HEAD')
            with contextlib.closing(response):
                if response.status != 200 or response.headers.get('Docker-Content-Digest') != pin:
                    raise RuntimeError('仓库未确认所需镜像的原始摘要')
            verified.append(ref)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        raise RuntimeError('镜像检查未确认；请检查内网仓库、CA、权限和原摘要') from None
    return verified
