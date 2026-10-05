"""Small CPU request controller for a single Neon compute Pod on Kubernetes >=1.35.

This adjusts the Kubernetes Pod /resize subresource. It does not provide
NeonVM memory hotplug, VM migration, or additional compute replicas.
"""

import json
import os
import ssl
import time
from decimal import Decimal
from urllib.error import HTTPError
from urllib.request import Request, urlopen


NAMESPACE = os.environ["POD_NAMESPACE"]
HOST = os.environ["KUBERNETES_SERVICE_HOST"]
PORT = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
BASE = f"https://{HOST}:{PORT}"
TOKEN = open("/var/run/secrets/kubernetes.io/serviceaccount/token", encoding="utf-8").read()
CA = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
TLS = ssl.create_default_context(cafile=CA)
MIN = int(os.environ["MIN_CPU_MILLI"])
MAX = int(os.environ["MAX_CPU_MILLI"])
INTERVAL = int(os.environ["INTERVAL_SECONDS"])
UP = Decimal(os.environ["UP_UTILIZATION"])
DOWN = Decimal(os.environ["DOWN_UTILIZATION"])
UP_SAMPLES = int(os.environ["UP_SAMPLES"])
DOWN_SAMPLES = int(os.environ["DOWN_SAMPLES"])
COOLDOWN = int(os.environ["COOLDOWN_SECONDS"])

if not (0 < MIN <= MAX and 0 < DOWN < UP < 1 and INTERVAL > 0 and COOLDOWN > 0):
    raise SystemExit("invalid CPU resize policy")


def api(path, method="GET", body=None):
    payload = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": "Bearer " + TOKEN, "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/strategic-merge-patch+json"
    request = Request(BASE + path, data=payload, headers=headers, method=method)
    try:
        with urlopen(request, context=TLS, timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read(500).decode(errors="replace")
        raise RuntimeError(f"Kubernetes API {method} {path}: HTTP {exc.code}: {detail}") from exc


def cpu_milli(value):
    if value.endswith("n"):
        return Decimal(value[:-1]) / 1_000_000
    if value.endswith("u"):
        return Decimal(value[:-1]) / 1_000
    if value.endswith("m"):
        return Decimal(value[:-1])
    return Decimal(value) * 1_000


def target_cpu(current, used, up_count, down_count):
    utilization = used / current
    if utilization > UP and up_count >= UP_SAMPLES and current < MAX:
        return min(MAX, current * 2)
    if utilization < DOWN and down_count >= DOWN_SAMPLES and current > MIN:
        return max(MIN, current // 2)
    return current


def run():
    current_uid = None
    above = below = 0
    last_change = 0.0
    while True:
        try:
            pods = api(f"/api/v1/namespaces/{NAMESPACE}/pods?labelSelector=app%3Dcompute")["items"]
            live = [p for p in pods if p["status"]["phase"] == "Running" and
                    p["metadata"].get("deletionTimestamp") is None]
            if len(live) != 1:
                above = below = 0
                print(f"waiting for exactly one running compute Pod; found {len(live)}", flush=True)
                time.sleep(INTERVAL)
                continue
            pod = live[0]
            name = pod["metadata"]["name"]
            uid = pod["metadata"]["uid"]
            if uid != current_uid:
                current_uid = uid
                above = below = 0
                last_change = time.monotonic()
            container = next(c for c in pod["spec"]["containers"] if c["name"] == "compute")
            resources = container.get("resources", {})
            requests = resources.get("requests", {})
            current = int(cpu_milli(requests["cpu"]))
            if not MIN <= current <= MAX:
                raise RuntimeError(f"compute CPU request {current}m outside configured range")
            metrics = api(f"/apis/metrics.k8s.io/v1beta1/namespaces/{NAMESPACE}/pods/{name}")
            usage = next(c["usage"]["cpu"] for c in metrics["containers"] if c["name"] == "compute")
            used = cpu_milli(usage)
            utilization = used / current
            above = above + 1 if utilization > UP else 0
            below = below + 1 if utilization < DOWN else 0
            if time.monotonic() - last_change >= COOLDOWN:
                target = target_cpu(current, used, above, below)
                if target != current:
                    patch = {"spec": {"containers": [{"name": "compute", "resources": {
                        "requests": {"cpu": f"{target}m", "memory": requests["memory"]}}}]}}
                    api(f"/api/v1/namespaces/{NAMESPACE}/pods/{name}/resize", "PATCH", patch)
                    print(f"resize {name} CPU {current}m -> {target}m; measured {used:.0f}m", flush=True)
                    above = below = 0
                    last_change = time.monotonic()
            time.sleep(INTERVAL)
        except Exception as exc:
            print(f"reconcile error: {exc}", flush=True)
            above = below = 0
            time.sleep(INTERVAL)


if __name__ == "__main__":
    run()
