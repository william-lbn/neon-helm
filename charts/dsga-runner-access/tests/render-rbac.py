#!/usr/bin/env python3
"""只渲染本 chart；核实际授权集合，不连接集群。"""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import yaml

chart = Path(__file__).resolve().parents[1]
helm = os.environ.get("HELM", "helm")
def render(values, wanted=True):
    with tempfile.TemporaryDirectory(prefix="runner-rbac-render-") as d:
        f = Path(d) / "values.json"
        f.write_text(json.dumps(values))
        r = subprocess.run([helm, "template", "runner-check", str(chart), "--namespace", "neon", "-f", str(f)], capture_output=True, text=True)
        if not wanted:
            assert r.returncode != 0, "illegal values rendered successfully"
            return []
        assert r.returncode == 0, r.stderr
        return [v for v in yaml.safe_load_all(r.stdout) if v]

assert render({}) == [], "default off must create no objects"
pre = {"enabled": True, "serviceAccountName": "fixture-runner", "vmName": "cp-0123456789abcdef", "configSecretName": "cp-0123456789abcdef-config", "hostLeases": [{"namespace": "neon", "name": "neon-dsga-host-worker-" + str(n)} for n in [117, 118, 119]]}
post = {**pre, "ownerLease": {"namespace": "neon", "name": "dsga-" + "c" * 56}, "stateClaimName": "dsga-s-" + "a" * 56}

def check(values, state):
    docs = render(values)
    assert {v["kind"] for v in docs} <= {"ServiceAccount", "Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding"}
    sa = [v for v in docs if v["kind"] == "ServiceAccount"]
    assert len(sa) == 1 and sa[0]["metadata"]["name"] == "fixture-runner" and sa[0]["metadata"]["namespace"] == "neon"
    assert sa[0]["automountServiceAccountToken"] is False
    roles = [v for v in docs if v["kind"] in {"Role", "ClusterRole"}]
    update = []
    vm = secret = nodes = cm = 0
    leases = set()
    for role in roles:
        ns = role["metadata"].get("namespace")
        for rule in role["rules"]:
            assert set(rule["verbs"]) <= {"get", "create", "update"}
            assert len(rule["resources"]) == 1
            resource = rule["resources"][0]
            assert rule["apiGroups"] == [{"virtualmachines": "vm.neon.tech", "leases": "coordination.k8s.io"}.get(resource, "")]
            verbs = set(rule["verbs"])
            if resource == "virtualmachines":
                assert ns == "neon" and verbs == {"get"} and rule["resourceNames"] == ["cp-0123456789abcdef"]
                vm += 1
            elif resource == "secrets":
                assert ns == "neon" and verbs == {"get"} and rule["resourceNames"] == ["cp-0123456789abcdef-config"]
                secret += 1
            elif resource == "pods":
                assert ns == "neon" and verbs == {"get"}
            elif resource == "nodes":
                assert role["kind"] == "ClusterRole" and verbs == {"get"} and sorted(rule["resourceNames"]) == ["worker-117", "worker-118", "worker-119"]
                nodes += 1
            elif resource == "configmaps":
                assert ns == "neon"
                if verbs == {"update"}:
                    update.append(rule["resourceNames"])
                else:
                    assert verbs == {"get", "create"} and "resourceNames" not in rule
                    cm += 1
            elif resource == "leases":
                assert verbs == {"get"} and len(rule["resourceNames"]) == 1
                leases.add((ns, rule["resourceNames"][0]))
            else:
                raise AssertionError(resource)
    assert (vm, secret, nodes, cm) == (1, 1, 1, 1)
    assert update == ([[state]] if state else [])
    expected = {("neon", "neon-dsga-host-worker-" + str(n)) for n in [117, 118, 119]}
    if state:
        expected.add(("neon", post["ownerLease"]["name"]))
    assert leases == expected
    for doc in docs:
        if doc["kind"] in {"RoleBinding", "ClusterRoleBinding"}:
            assert doc["subjects"] == [{"kind": "ServiceAccount", "name": "fixture-runner", "namespace": "neon"}]
            ref = doc["roleRef"]
            assert any(role["kind"] == ref["kind"] and role["metadata"]["name"] == ref["name"] and role["metadata"].get("namespace") == doc["metadata"].get("namespace") for role in roles)

render({"enabled": True}, wanted=False)  # 仅打开开关不能借旧默认身份授权
check(pre, "")
check(post, post["stateClaimName"])
negatives = [
    {"configSecretName": "cp-0000000000000000-config"},
    {"vmName": "neon-k8s-old-id"},
    {"serviceAccountName": "default"},
    {"allowedNodeNames": ["worker-116", "worker-118", "worker-119"]},
    {"allowedNodeNames": ["worker-117", "worker-118", "worker-118"]},
    {"stateClaimName": "*"},
    {"stateClaimName": "dsga-s-" + "b" * 56},
    {"hostLeases": [{"namespace": "neon", "name": "neon-dsga-host-worker-116"}]},
    {"hostLeases": [{"namespace": str(n), "name": "neon-dsga-host-worker-117"} for n in [1, 2, 3]]},
    {"ownerLease": {"namespace": "neon", "name": "a..b"}},
    {"unsafeVerbs": ["*"]},
]
for bad in negatives:
    render({**pre, **bad}, wanted=False)
print(json.dumps({"default_off": True, "positive_render_cases": 2, "negative_rejections": len(negatives) + 1, "only_SA_RBAC": True, "cluster_accessed": False}))
