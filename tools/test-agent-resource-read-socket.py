#!/usr/bin/env python3
"""只离线渲染资源读取UDS；所有预算和Lease均为明确测试输入，不可用于部署认证。"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import uuid
import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = Path(args.output_dir)
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    values = json.loads((repo / "profiles/lab/neon-autoscaler.json").read_text())
    uids = json.loads((repo / "charts/neon-autoscaler/files/pg17-node-identities.json").read_text())["allowedNodeUIDs"]
    values["compatibility"] = {"expectedKubernetesMinor": "31", "allowUntestedKubernetes": False}
    values["dsga"] = {"enabled": True, "agent": {"gatewayURL": "https://render-only.invalid", "managementCASecret": "render-only-no-certification", "resourceReadSocket": {"enabled": True, "hostDirectory": "/data/neon-k8s-pg17/private/resource-reader", "mountDirectory": "/run/neon-dsga-resource", "name": "state.sock"}}, "scheduler": {"nodes": [{"binding": {"node_name": name, "node_uid": uid, "namespace": "render-only", "lease_name": "render-"+name, "lease_uid": str(uuid.uuid5(uuid.NAMESPACE_DNS, "render-only-"+name))}, "profile": {"id": "render-only-not-certified", "scheduler_name": "autoscale-scheduler", "vm_overhead_bytes": "1", "pod_overhead_bytes": "1"}, "system_bytes": "1"} for name, uid in uids.items()]}}
    cases = [("enabled", values, True, "")]
    disabled = copy.deepcopy(values)
    disabled["dsga"]["agent"]["resourceReadSocket"]["enabled"] = False
    cases.append(("disabled", disabled, True, ""))
    no_dsga = copy.deepcopy(values)
    no_dsga["dsga"]["enabled"] = False
    cases.append(("no-dsga", no_dsga, False, "requires DSGA enabled"))
    for field, entry in [("hostDirectory", "relative"), ("mountDirectory", "/run/../resource"), ("mountDirectory", "/run//resource"), ("hostDirectory", "/"), ("name", "../state.sock"), ("name", "state"), ("name", "x"*100+".sock")]:
        modified = copy.deepcopy(values)
        modified["dsga"]["agent"]["resourceReadSocket"][field] = entry
        reason = "canonical absolute private directories" if field != "name" else "short original socket filename"
        cases.append((field+"-"+str(len(cases)), modified, False, reason))
    results = []
    for name, case, expected, reason in cases:
        path = out / (name+".json")
        path.write_text(json.dumps(case, indent=2)+"\n")
        process = subprocess.run(["helm", "template", "render-only", str(repo / "charts/neon-autoscaler"), "--namespace", "kube-system", "--kube-version", "1.31.0", "-f", str(path)], capture_output=True, text=True, timeout=20)
        (out / (name+".stderr")).write_text(process.stderr)
        row = {"case": name, "expected_success": expected, "exit": process.returncode, "passed": (process.returncode == 0) == expected}
        if not expected:
            row["correct_rejection_reason"] = reason in process.stderr
            row["passed"] = row["passed"] and row["correct_rejection_reason"]
        if process.returncode == 0:
            docs = [doc for doc in yaml.safe_load_all(process.stdout) if doc]
            config = next(doc for doc in docs if doc["kind"] == "ConfigMap" and doc["metadata"]["name"] == "autoscaler-agent-config")
            config = json.loads(config["data"]["config.json"])
            spec = next(doc for doc in docs if doc["kind"] == "DaemonSet" and doc["metadata"]["name"] == "autoscaler-agent")["spec"]["template"]["spec"]
            volumes = [v for v in spec["volumes"] if v["name"] == "dsga-resource-read"]
            mounts = [v for v in spec["containers"][0]["volumeMounts"] if v["name"] == "dsga-resource-read"]
            if name == "enabled":
                wiring = config["dsga"]["resourceReadSocketPath"] == "/run/neon-dsga-resource/state.sock" and len(volumes) == 1 and volumes[0]["hostPath"] == {"path": "/data/neon-k8s-pg17/private/resource-reader", "type": "Directory"} and len(mounts) == 1 and mounts[0]["mountPath"] == "/run/neon-dsga-resource" and not mounts[0].get("readOnly", False) and not config["dsga"].get("controlSocketPath")
            else:
                wiring = "resourceReadSocketPath" not in config["dsga"] and not volumes and not mounts
            row["wiring"] = wiring
            row["passed"] = row["passed"] and wiring
            (out / (name+".rendered-public.yaml")).write_text(process.stdout)
        results.append(row)
    result = {"scope": "offline resource-only socket template regression; synthetic non-certified budgets", "cases": results, "passed": all(row["passed"] for row in results), "Source": False, "E": 0, "K8s": False, "no_cluster_mutation": True}
    (out / "result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"cases": len(results), "passed": result["passed"], "report": str(out / "result.json")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
