"""Cluster-resident Neon proxy and storage-controller adapter.

This first release runs one replica. Route data lives in a Kubernetes Secret,
notification receipts in a ConfigMap. The adapter keeps the existing two lab
routes and supports dynamically provisioned endpoints. It never returns a
compute address until the workload is ready. Migration to another pageserver
or safekeeper set is blocked until a compute reconfiguration driver is added.
"""

from __future__ import annotations

import base64
import errno
import hashlib
import hmac
import json
import os
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import Request, urlopen


NAMESPACE = os.getenv("POD_NAMESPACE", "neon")
PROXY_TOKEN = os.environ["PROXY_API_TOKEN"]
CONTROLLER_TOKEN = os.environ["CONTROLLER_HOOK_TOKEN"]
ROUTES_SECRET = os.getenv("ROUTES_SECRET", "neon-control-routes")
NOTIFICATIONS = os.getenv("NOTIFICATIONS_CONFIGMAP", "neon-control-notifications")
KUBE_HOST = os.environ["KUBERNETES_SERVICE_HOST"]
KUBE_PORT = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS", "443")
KUBE_BASE = f"https://{KUBE_HOST}:{KUBE_PORT}"
KUBE_TOKEN_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/token"
KUBE_CA_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
LOCK = threading.RLock()
WAKE_LOCKS: dict[str, threading.RLock] = {}


class KubeRequestError(RuntimeError):
    def __init__(self, method: str, path: str, status: int):
        super().__init__(f"Kubernetes {method} {path} returned {status}")
        self.status = status


class KubeTransportError(RuntimeError):
    """Expose the failed operation without logging tokens or API bodies."""
    def __init__(self, method: str, path: str, cause: Exception, attempts: int = 1):
        super().__init__(f"Kubernetes {method} {path} transport={type(cause).__name__} attempts={attempts}")
        self.method, self.path, self.attempts = method, path, attempts


def transient_read_error(error: Exception) -> bool:
    """Retry network reads only; TLS/HTTP/JSON failures are not hidden."""
    cause = error.reason if isinstance(error, URLError) else error
    if isinstance(cause, ssl.SSLError):
        return False
    return isinstance(cause, (TimeoutError, ConnectionResetError, ConnectionRefusedError)) or \
        isinstance(cause, OSError) and cause.errno in (errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNREFUSED)


def kube(method: str, path: str, payload=None) -> dict:
    token = open(KUBE_TOKEN_FILE, encoding="utf-8").read().strip()
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    # 2026-10-03: actual cold wakes failed at the VM GET while later probes
    # were healthy. Permit one fresh read after a transient transport failure.
    # POST/PUT/DELETE outcomes can be unknown: never replay those mutations.
    attempts = 2 if method == "GET" and data is None else 1
    context = ssl.create_default_context(cafile=KUBE_CA_FILE)
    for attempt in range(attempts):
        request = Request(KUBE_BASE + path, data=data, method=method, headers=headers)
        try:
            with urlopen(request, context=context, timeout=15) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except HTTPError as exc:
            raise KubeRequestError(method, path, exc.code) from exc
        except (OSError, URLError) as exc:
            if attempt + 1 < attempts and transient_read_error(exc):
                print(f"adapter read retry: {method} {path} transport={type(exc).__name__} attempt={attempt + 1}", flush=True)
                time.sleep(0.2)
                continue
            raise KubeTransportError(method, path, exc, attempt + 1) from exc
    raise AssertionError("unreachable Kubernetes request state")


def get_routes() -> dict:
    raw = kube("GET", f"/api/v1/namespaces/{NAMESPACE}/secrets/{ROUTES_SECRET}")
    routes = json.loads(base64.b64decode(raw["data"]["routes.json"]))
    return routes


def get_workload(route: dict) -> dict:
    kind, name = route["kind"], route["workload"]
    if kind == "deployment":
        return kube("GET", f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{quote(name)}")
    if kind == "neonvm":
        return kube("GET", f"/apis/vm.neon.tech/v1/namespaces/{NAMESPACE}/virtualmachines/{quote(name)}")
    raise ValueError("unsupported workload kind")


def wake(selector: str, route: dict) -> tuple[str, str]:
    with LOCK:
        endpoint_lock = WAKE_LOCKS.setdefault(selector, threading.RLock())
    with endpoint_lock:
        cold = False
        deadline = time.monotonic() + 300
        if route["kind"] == "deployment":
            item = get_workload(route)
            if item["spec"].get("replicas", 1) == 0:
                name = quote(route["workload"])
                # PUT scale with resourceVersion; a concurrent change is retried by the proxy.
                scale = kube("GET", f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{name}/scale")
                scale["spec"]["replicas"] = 1
                kube("PUT", f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{name}/scale", scale)
                cold = True
        elif route["kind"] == "neonvm" and route.get("vm_template"):
            template = route["vm_template"]
            if template.get("kind") != "VirtualMachine" or \
                    template.get("metadata", {}).get("name") != route["workload"] or \
                    template.get("metadata", {}).get("labels", {}).get("neon-control/project-id") != route["project_id"]:
                raise ValueError("invalid VM resume template")
            # A deleting VM retains its name until its finalizer completes.
            # One adapter replica serializes requests; Kubernetes 409 protects
            # against a second replica or a simultaneous manual start.
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("VM deletion did not finish before wake")
                try:
                    item = get_workload(route)
                except KubeRequestError as exc:
                    if exc.status != 404:
                        raise
                    try:
                        kube("POST", f"/apis/vm.neon.tech/v1/namespaces/{NAMESPACE}/virtualmachines", template)
                    except KubeRequestError as create_exc:
                        if create_exc.status != 409:
                            raise
                    cold = True
                    break
                if not item.get("metadata", {}).get("deletionTimestamp"):
                    break
                time.sleep(2)
        while time.monotonic() < deadline:
            item = get_workload(route)
            if route["kind"] == "deployment":
                ready = item.get("status", {}).get("readyReplicas", 0) >= 1
            else:
                ready = item.get("status", {}).get("phase") == "Running"
            if ready:
                return route["address"], "pool_miss" if cold else "warm"
            time.sleep(2)
        raise TimeoutError("compute readiness timeout")


def verify_controller_state(tenant: str, shards: list[dict]) -> None:
    request = Request(f"http://storage-controller:1234/control/v1/tenant/{tenant}")
    with urlopen(request, timeout=10) as response:
        authoritative = json.load(response)
    # The exact controller response varies by Neon version. Reject any attach
    # to unknown nodes. Node 2 is the isolated managed pageserver in this lab.
    if any(int(shard["node_id"]) != 2 for shard in shards):
        raise RuntimeError("pageserver migration is not enabled")
    if not authoritative:
        raise RuntimeError("controller tenant state missing")


def persist_notification(kind: str, payload: dict) -> None:
    # ConfigMap is a durable, bounded receipt for this one-region lab release.
    # A future HA release moves these records to the control database.
    key = f"{kind}:{payload['tenant_id']}:{payload.get('timeline_id', '')}"
    receipt = {
        "hash": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        "payload": payload,
        "received_at": time.time(),
    }
    with LOCK:
        path = f"/api/v1/namespaces/{NAMESPACE}/configmaps/{NOTIFICATIONS}"
        for _ in range(4):
            item = kube("GET", path)
            records = json.loads(item.get("data", {}).get("receipts.json", "{}"))
            previous = records.get(key)
            if kind == "safekeepers" and previous:
                old_generation = int(previous["payload"].get("generation", 0))
                new_generation = int(payload["generation"])
                if new_generation < old_generation:
                    return
                if new_generation == old_generation and previous["hash"] != receipt["hash"]:
                    raise RuntimeError("conflicting safekeeper generation")
            records[key] = receipt
            item["data"] = {"receipts.json": json.dumps(records, separators=(",", ":"))}
            try:
                kube("PUT", path, item)
                return
            except RuntimeError as exc:
                if "returned 409" not in str(exc):
                    raise
        raise RuntimeError("notification update conflict")


class Handler(BaseHTTPRequestHandler):
    def reply(self, status: int, value: dict):
        data = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self, token: str) -> bool:
        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)

    def do_GET(self):
        uri = urlsplit(self.path)
        path = uri.path.replace("//", "/")
        if path == "/healthz":
            self.reply(200, {"status": "ok"})
            return
        if not self.authorized(PROXY_TOKEN):
            self.reply(401, {"error": "unauthorized"})
            return
        query = parse_qs(uri.query)
        selector = query.get("endpointish", [""])[0]
        try:
            route = get_routes().get(selector)
            if not route:
                self.reply(404, {"error": "unknown endpoint"})
                return
            if path == "/cplane/get_endpoint_access_control":
                role = query.get("role", [""])[0]
                roles = route.get("roles") or {route["role"]: route["verifier"]}
                if role not in roles:
                    self.reply(404, {"error": "unknown role"})
                    return
                self.reply(200, {
                    "role_secret": roles[role],
                    "allowed_ips": route.get("allowed_ips", ["0.0.0.0/0"]),
                })
            elif path == "/cplane/wake_compute":
                address, info = wake(selector, route)
                self.reply(200, {
                    "address": address,
                    "aux": {
                        "endpoint_id": selector,
                        "project_id": route["project_id"],
                        "branch_id": route["branch_id"],
                        "compute_id": route["workload"],
                        "cold_start_info": info,
                    },
                })
            elif path.endswith("/jwks"):
                self.reply(200, {"jwks": []})
            else:
                self.reply(404, {"error": "unknown path"})
        except Exception as exc:
            print(f"adapter GET failure: {type(exc).__name__}: {exc}", flush=True)
            self.reply(503, {"error": "adapter_unavailable"})

    def do_PUT(self):
        path = urlsplit(self.path).path
        if path not in ("/notify-attach", "/notify-safekeepers"):
            self.reply(404, {"error": "unknown path"})
            return
        if not self.authorized(CONTROLLER_TOKEN):
            self.reply(401, {"error": "unauthorized"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 64_000:
                raise ValueError("invalid body size")
            payload = json.loads(self.rfile.read(size))
            tenant = payload["tenant_id"]
            if len(tenant) != 32:
                raise ValueError("invalid tenant")
            kind = "attach" if path == "/notify-attach" else "safekeepers"
            if kind == "attach":
                verify_controller_state(tenant, payload["shards"])
            else:
                int(payload["generation"])
                payload["timeline_id"]
            # Existing compute configuration is immutable in this release.
            # If a tenant has a running route and the authoritative location
            # differs, block migration instead of acknowledging stale config.
            routes = get_routes()
            active = [r for r in routes.values() if r.get("tenant_id") == tenant]
            if active and kind == "attach" and any(
                r.get("pageserver_node_id", 2) != 2 for r in active
            ):
                self.reply(423, {"error": "compute_reconfiguration_pending"})
                return
            persist_notification(kind, payload)
            self.reply(200, {"status": "applied"})
        except (ValueError, KeyError, json.JSONDecodeError):
            self.reply(400, {"error": "invalid_notification"})
        except Exception as exc:
            print(f"adapter notify failure: {type(exc).__name__}: {exc}", flush=True)
            self.reply(503, {"error": "notification_unavailable"})

    def log_message(self, fmt, *args):
        # Never log query strings or SCRAM verifiers.
        print("neon-control-adapter", self.client_address[0], args[1] if len(args) > 1 else "", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
