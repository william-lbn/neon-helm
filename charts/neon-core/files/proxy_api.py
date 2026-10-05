"""Small, statically provisioned adapter for the open-source Neon proxy v1 API.

The primary endpoint supports Deployment 0/1 scaling. An optional second endpoint
routes to an independently managed NeonVM compute in the autoscaling laboratory.
"""

import hmac
import json
import os
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


TOKEN = os.environ["PROXY_API_TOKEN"]
ENDPOINT = os.environ["ENDPOINT_ID"]
ROLE = os.environ["ROLE_NAME"]
SCRAM_VERIFIER = os.environ["SCRAM_VERIFIER"]
COMPUTE_ADDRESS = os.environ["COMPUTE_ADDRESS"]
VM_ENDPOINT = os.environ.get("VM_ENDPOINT_ID", "").strip()
VM_COMPUTE_ADDRESS = os.environ.get("VM_COMPUTE_ADDRESS", "").strip()
ALLOWED_IPS = json.loads(os.environ.get("ALLOWED_IPS", '["0.0.0.0/0"]'))
SCALE_ENABLED = os.environ.get("SCALE_TO_ZERO_ENABLED", "false").lower() == "true"
SCALE_ADMIN_TOKEN = os.environ.get("SCALE_ADMIN_TOKEN", "").strip()
NAMESPACE = os.environ.get("POD_NAMESPACE", "neon")
IDLE_SECONDS = int(os.environ.get("SCALE_IDLE_SECONDS", "180"))
SCALE_LOCK = threading.RLock()
LAST_WAKE = time.monotonic()

if not TOKEN or not SCRAM_VERIFIER.startswith("SCRAM-SHA-256$"):
    raise SystemExit("proxy API requires a token and PostgreSQL SCRAM verifier")
if SCALE_ENABLED and (not SCALE_ADMIN_TOKEN or IDLE_SECONDS < 30):
    raise SystemExit("scale-to-zero requires a separate admin token and >=30s idle threshold")
if bool(VM_ENDPOINT) != bool(VM_COMPUTE_ADDRESS) or (VM_ENDPOINT and VM_ENDPOINT == ENDPOINT):
    raise SystemExit("VM endpoint ID and address must both be set and distinct from primary")


def endpoint_address(requested):
    if requested == ENDPOINT:
        return COMPUTE_ADDRESS
    if VM_ENDPOINT and requested == VM_ENDPOINT:
        return VM_COMPUTE_ADDRESS
    return None


def kube(path, method="GET", body=None):
    token = open("/var/run/secrets/kubernetes.io/serviceaccount/token", encoding="utf-8").read()
    host = os.environ["KUBERNETES_SERVICE_HOST"]
    port = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
    payload = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/merge-patch+json"
    req = Request(f"https://{host}:{port}{path}", data=payload, headers=headers, method=method)
    ca = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    with urlopen(req, context=ssl.create_default_context(cafile=ca), timeout=10) as response:
        return json.load(response)


def deployment():
    return kube(f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/compute")


def set_replicas(count):
    return kube(f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/compute/scale",
                "PATCH", {"spec": {"replicas": count}})


def active_proxy_connections():
    with urlopen("http://proxy:7001/metrics", timeout=5) as response:
        metrics = response.read(2_000_000).decode()
    values = {}
    for name in ("proxy_opened_db_connections_total", "proxy_closed_db_connections_total"):
        matches = [float(line.rsplit(" ", 1)[-1]) for line in metrics.splitlines()
                   if line.startswith(name + "{") or line.startswith(name + " ")]
        # Prometheus counters are absent until their first event; absence is zero.
        values[name] = sum(matches)
    return max(0, int(values["proxy_opened_db_connections_total"] -
                      values["proxy_closed_db_connections_total"]))


def scale_one():
    global LAST_WAKE
    with SCALE_LOCK:
        state = deployment()
        cold = state["spec"].get("replicas", 1) == 0
        LAST_WAKE = time.monotonic()
        if cold:
            set_replicas(1)
            print("compute scale 0 -> 1 requested by proxy wake", flush=True)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = deployment()
            if state.get("status", {}).get("readyReplicas", 0) >= 1:
                LAST_WAKE = time.monotonic()
                return cold
            time.sleep(2)
        raise TimeoutError("compute did not become Ready within 180s")


def scale_zero():
    global LAST_WAKE
    with SCALE_LOCK:
        if active_proxy_connections() != 0:
            raise RuntimeError("proxy still has active database connections")
        if deployment()["spec"].get("replicas", 1) == 0:
            return
        set_replicas(0)
        LAST_WAKE = time.monotonic()
        print("compute scale 1 -> 0 requested after idle", flush=True)


def idle_loop():
    idle_samples = 0
    while True:
        time.sleep(15)
        try:
            if time.monotonic() - LAST_WAKE < IDLE_SECONDS:
                idle_samples = 0
                continue
            if deployment()["spec"].get("replicas", 1) == 0:
                idle_samples = 0
                continue
            idle_samples = idle_samples + 1 if active_proxy_connections() == 0 else 0
            if idle_samples >= 3:
                scale_zero()
                idle_samples = 0
        except Exception as exc:
            idle_samples = 0
            print(f"idle scaling skipped: {exc}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def answer(self, code, value):
        data = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        uri = urlsplit(self.path)
        # The upstream proxy appends a path segment to a base URL ending in '/'.
        # url.path_segments_mut().push() can retain that empty trailing segment.
        path = uri.path.replace("//", "/")
        if path == "/healthz":
            self.answer(200, {"status": "ok"})
            return
        if path == "/admin/status" and SCALE_ENABLED:
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + SCALE_ADMIN_TOKEN):
                self.answer(401, {"error": "unauthorized"})
                return
            try:
                state = deployment()
                self.answer(200, {"desired_replicas": state["spec"].get("replicas", 1),
                                  "ready_replicas": state.get("status", {}).get("readyReplicas", 0),
                                  "active_proxy_connections": active_proxy_connections()})
            except Exception as exc:
                self.answer(503, {"error": str(exc)})
            return
        header = self.headers.get("Authorization", "")
        if not hmac.compare_digest(header, "Bearer " + TOKEN):
            self.answer(401, {"error": "unauthorized"})
            return

        params = parse_qs(uri.query)
        requested_endpoint = params.get("endpointish", [""])[0]
        if path == "/cplane/get_endpoint_access_control":
            if endpoint_address(requested_endpoint) is None or params.get("role", [""])[0] != ROLE:
                self.answer(404, {"error": "unknown endpoint or role"})
                return
            self.answer(200, {"role_secret": SCRAM_VERIFIER, "allowed_ips": ALLOWED_IPS})
        elif path == "/cplane/wake_compute":
            address = endpoint_address(requested_endpoint)
            if address is None:
                self.answer(404, {"error": "unknown endpoint"})
                return
            try:
                cold = scale_one() if SCALE_ENABLED and requested_endpoint == ENDPOINT else False
            except Exception as exc:
                self.answer(503, {"error": f"compute wake failed: {exc}"})
                return
            self.answer(200, {
                "address": address,
                "aux": {
                    "endpoint_id": requested_endpoint,
                    "project_id": "self-hosted",
                    "branch_id": "main",
                    "compute_id": "compute-1" if requested_endpoint == ENDPOINT else "vm-neon-compute",
                    "cold_start_info": "pool_miss" if cold else "warm",
                },
            })
        elif path in (f"/cplane/endpoints/{ENDPOINT}/jwks", f"/cplane/endpoints/{VM_ENDPOINT}/jwks" if VM_ENDPOINT else ""):
            self.answer(200, {"jwks": []})
        else:
            self.answer(404, {"error": "unknown path"})

    def do_POST(self):
        if self.path != "/admin/scale" or not SCALE_ENABLED:
            self.answer(404, {"error": "unknown path"})
            return
        if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + SCALE_ADMIN_TOKEN):
            self.answer(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 256:
                raise ValueError("invalid request length")
            count = json.loads(self.rfile.read(length))["replicas"]
            if type(count) is not int or count not in (0, 1):
                raise ValueError("replicas must be 0 or 1")
        except (ValueError, KeyError, json.JSONDecodeError):
            self.answer(400, {"error": "expected replicas 0 or 1"})
            return
        try:
            if count == 0:
                scale_zero()
            else:
                scale_one()
            state = deployment()
            self.answer(200, {"desired_replicas": state["spec"].get("replicas", 1),
                              "ready_replicas": state.get("status", {}).get("readyReplicas", 0)})
        except Exception as exc:
            self.answer(409, {"error": str(exc)})

    def log_message(self, fmt, *args):
        # Do not put URL query strings or authorization headers in pod logs.
        print("proxy-api", self.client_address[0], args[1] if len(args) > 1 else "", flush=True)


if __name__ == "__main__":
    if SCALE_ENABLED:
        threading.Thread(target=idle_loop, name="compute-idle-scaler", daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
