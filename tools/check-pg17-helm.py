#!/usr/bin/env python3
"""PG17 Helm 离线基础门槛。仅调用 helm lint/template；不访问或修改集群。"""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTS = ("neonvm", "neon-autoscaler", "neon-core", "neon-compute",
          "neon-adapter", "neon-managed-pageserver", "compute-management-gateway")
NODES = ("worker-117", "worker-118", "worker-119")
POOL_KEY = "neon.tech/pg17-memory-pool"
POOL_VALUE = "-".join(NODES)
PIN = re.compile(r"^[^\s]+@sha256:[a-f0-9]{64}$")
SOURCE_SHA = "02a1b0c90e58e3dfed2bb9f2c7c44e98a207ca28"

class UniqueKeyLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError("Duplicate YAML mapping key: " + str(key))
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def documents(text):
    return list(yaml.load_all(text, Loader=UniqueKeyLoader))



def require(condition, message):
    if not condition:
        raise AssertionError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def image(name):
    # 合成地址只用于离线模板测试，绝不是发行镜像或可部署输入。
    return "example.invalid/pg17-offline/" + name + "@sha256:" + hashlib.sha256(name.encode()).hexdigest()


def merge(base, overlay):
    value = copy.deepcopy(base)
    for key, item in overlay.items():
        if isinstance(item, dict) and isinstance(value.get(key), dict):
            value[key] = merge(value[key], item)
        else:
            value[key] = copy.deepcopy(item)
    return value


def check_nodes(snapshot):
    """调用方提供只读 NodeList 快照；本工具绝不调用 kubectl 或写标签。"""
    require(snapshot.get("kind") == "NodeList", "Expected a real NodeList JSON snapshot")
    items = snapshot.get("items")
    require(isinstance(items, list), "NodeList.items must be a list")
    names = [n.get("metadata", {}).get("name") for n in items]
    require(len(names) == len(set(names)), "Duplicate node identity in snapshot")
    by_name = dict(zip(names, items))
    require("ubuntu" in by_name and not snapshot.get("metadata", {}).get("continue"),
            "Complete unpaginated NodeList including excluded ubuntu/116 is required")
    selected = {n["metadata"]["name"] for n in items
                if n.get("metadata", {}).get("labels", {}).get(POOL_KEY) == POOL_VALUE}
    require(selected == set(NODES), "Pool membership must equal worker-117/118/119 exactly; ubuntu/116 is forbidden")
    for name in NODES:
        require(name in by_name, "Missing explicit candidate: " + name)
        node = by_name[name]
        labels = node["metadata"].get("labels", {})
        require(labels.get("kubernetes.io/hostname") == name, "Hostname identity differs: " + name)
        require(labels.get("kubernetes.io/arch") == "amd64" and labels.get("kubernetes.io/os") == "linux",
                "Candidate must be Linux/amd64: " + name)
        require(node.get("status", {}).get("nodeInfo", {}).get("architecture") == "amd64",
                "Node status architecture differs: " + name)
        require(not node.get("spec", {}).get("unschedulable", False), "Candidate is cordoned: " + name)
        conditions = node.get("status", {}).get("conditions", [])
        require(any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions),
                "Candidate is not Ready: " + name)
        require(not any(c.get("type") in ("MemoryPressure", "DiskPressure", "PIDPressure") and c.get("status") == "True"
                        for c in conditions), "Candidate has resource pressure: " + name)
        require(not any(t.get("effect") in ("NoSchedule", "NoExecute") for t in node.get("spec", {}).get("taints", [])),
                "Candidate has a hard taint; current storage/VM profile has no corresponding toleration: " + name)
    return {"allowlist": list(NODES), "poolLabel": {POOL_KEY: POOL_VALUE},
            "snapshotNodeCount": len(items), "roleLabelsDoNotDeterminePlacement": True}


def fixture_nodes():
    items = []
    for name in ("ubuntu",) + NODES:
        labels = {"kubernetes.io/hostname": name, "kubernetes.io/arch": "amd64", "kubernetes.io/os": "linux"}
        if name in NODES:
            labels[POOL_KEY] = POOL_VALUE
        if name in ("ubuntu", "worker-119"):
            labels["node-role.kubernetes.io/control-plane"] = "true"
        items.append({"metadata": {"name": name, "labels": labels}, "spec": {},
                      "status": {"nodeInfo": {"architecture": "amd64"}, "conditions": [{"type": "Ready", "status": "True"}]}})
    return {"apiVersion": "v1", "kind": "NodeList", "items": items}


def pod_specs(objects):
    for obj in objects:
        kind = obj.get("kind")
        if kind in ("Deployment", "StatefulSet", "DaemonSet", "Job"):
            yield obj, obj["spec"]["template"]["spec"]
        elif kind == "CronJob":
            yield obj, obj["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        elif kind == "Pod":
            yield obj, obj["spec"]
        elif kind == "VirtualMachine":
            yield obj, obj["spec"]


def check_render(objects):
    checked = []
    for obj, spec in pod_specs(objects):
        identity = obj["kind"] + "/" + obj["metadata"]["name"]
        require("nodeName" not in spec, "Direct nodeName bypass: " + identity)
        selector = spec.get("nodeSelector", {})
        require(selector == {"kubernetes.io/os": "linux", "kubernetes.io/arch": "amd64", POOL_KEY: POOL_VALUE},
                "Missing or broadened pool/Linux/amd64 selector: " + identity)
        terms = spec.get("affinity", {}).get("nodeAffinity", {}).get(
            "requiredDuringSchedulingIgnoredDuringExecution", {}).get("nodeSelectorTerms", [])
        require(terms, "Missing required hostname affinity: " + identity)
        for term in terms:
            constraints = term.get("matchExpressions", [])
            require(any(c.get("key") == "kubernetes.io/hostname" and c.get("operator") == "In"
                        and sorted(c.get("values", [])) == list(NODES) for c in constraints),
                    "An OR affinity branch escapes the allowlist: " + identity)
        if obj["kind"] == "VirtualMachine":
            require(PIN.fullmatch(spec["guest"]["rootDisk"]["image"]), "Unpinned VM rootdisk: " + identity)
            require(next(v["value"] for v in spec["guest"]["env"] if v["name"] == "PG_VERSION") == "17",
                    "Static VM is not PG17")
        else:
            for container in spec.get("containers", []) + spec.get("initContainers", []) + spec.get("ephemeralContainers", []):
                require(PIN.fullmatch(container.get("image", "")), "Unpinned container: " + identity)
        checked.append(identity)
    require(checked, "No workloads rendered")
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kube-version", default="1.31.2")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--autoscaling-source", type=Path, default=ROOT.parent / "autoscaling")
    parser.add_argument("--check-nodes", type=Path,
                        help="只验证调用方提供的实际 NodeList JSON；不会连接集群，不会运行离线 fixture")
    args = parser.parse_args()
    if args.check_nodes:
        result = check_nodes(json.loads(args.check_nodes.read_text()))
        print(json.dumps({"gate": "PG17-S-H04", "mode": "provided-node-snapshot", "status": "pass",
                          "snapshotSha256": hashlib.sha256(args.check_nodes.read_bytes()).hexdigest(), **result},
                         ensure_ascii=False, indent=2))
        return 0
    require(re.fullmatch(r"1\.31\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", args.kube_version),
            "This batch is qualified only for the explicit Kubernetes 1.31 target")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    out = args.output or ROOT / "artifacts" / "pg17-helm" / stamp
    out.mkdir(parents=True, exist_ok=False)
    (out / "fixtures").mkdir()
    (out / "logs").mkdir()
    results = []
    sequence = 0
    empty_kubeconfig = out / "offline-only.kubeconfig"
    empty_kubeconfig.write_text("apiVersion: v1\nkind: Config\nclusters: []\nusers: []\ncontexts: []\ncurrent-context: \"\"\n")
    empty_kubeconfig.chmod(0o600)
    environment = dict(os.environ, KUBECONFIG=str(empty_kubeconfig), HELM_NO_PLUGINS="1")
    binary = os.environ.get("HELM_BIN", "helm")

    def helm(chart, values, action="template", chart_path=None, expected_failure=False):
        nonlocal sequence
        sequence += 1
        fixture = out / "fixtures" / (str(sequence) + "-" + chart + ".json")
        fixture.write_text(json.dumps(values, indent=2) + "\n")
        cmd = [binary, action, str(chart_path or ROOT / "charts" / chart), "-f", str(fixture)]
        if action == "lint":
            cmd.append("--strict")
        else:
            cmd += ["--namespace", "neon" if chart not in ("neonvm", "neon-autoscaler") else "default",
                    "--kube-version", args.kube_version]
        process = subprocess.run(cmd, cwd=ROOT, env=environment, text=True, capture_output=True, timeout=60)
        for suffix, text in (("stdout", process.stdout), ("stderr", process.stderr)):
            (out / "logs" / (str(sequence) + "-" + chart + "." + suffix + ".txt")).write_text(text)
        if expected_failure:
            require(process.returncode != 0, "Unsafe input was accepted: " + chart)
            return process
        require(process.returncode == 0, "Helm " + action + " failed for " + chart + "; see log " + str(sequence))
        return process

    def record(identity, description, run):
        started = time.monotonic()
        try:
            detail = run()
            result = {"id": identity, "description": description, "status": "pass", "detail": detail}
        except Exception as error:
            result = {"id": identity, "description": description, "status": "fail",
                      "error": type(error).__name__ + ": " + str(error)}
        result["seconds"] = round(time.monotonic() - started, 3)
        results.append(result)
        (out / (identity + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(identity + " " + result["status"] + (" " + result.get("error", "")), flush=True)

    profiles = {}
    for chart in CHARTS:
        profile = json.loads((ROOT / "profiles/lab" / (chart + ".json")).read_text())
        profile["placement"] = {"allowedNodeNames": list(NODES)}
        if chart in ("neonvm", "neon-autoscaler"):
            profile["compatibility"] = {"expectedKubernetesMinor": "31", "allowUntestedKubernetes": False}
            profile["images"] = {key: image(chart + "-" + key)
                                 for key in yaml.safe_load((ROOT / "charts" / chart / "values.yaml").read_text())["images"]}
        if chart == "neonvm":
            profile["controller"]["runnerCgroupEnabled"] = True
        if chart == "neon-compute":
            profile["compute"] = merge(profile["compute"], {"enabled": True, "pgVersion": 17, "image": image("compute-pg17"),
                                                          "tenantId": "1" * 32, "timelineId": "2" * 32})
        if chart == "neon-core":
            profile = merge(profile, {"minio": {"productStorage": {"enabled": False}},
                                     "proxy": {"enabled": False}, "storageController": {"enabled": False},
                                     "compute": {"enabled": False}, "computeResize": {"enabled": False}})
        profiles[chart] = profile

    def invalid_placement():
        rejected = 0
        for chart in CHARTS:
            for names in ([], ["worker-117", "worker-118", "ubuntu"], ["worker-117", "worker-118", "172.24.79.116"],
                          ["worker-117", "worker-118", "worker-120"], ["worker-117"] * 3, ["worker-117", "worker-118"]):
                process = helm(chart, merge(profiles[chart], {"placement": {"allowedNodeNames": names}}), expected_failure=True)
                require("placement" in process.stderr + process.stdout, "Rejection did not identify placement")
                rejected += 1
            for overlay in ({"placement": {"unknown": True}}, {"placement": None}, {"unknownSetting": True}):
                helm(chart, merge(profiles[chart], overlay), expected_failure=True)
                rejected += 1
        return {"schemaRejections": rejected}

    record("PG17-U-H01", "七个 chart 拒绝空、缺项、重复、116、未知节点及未知 placement 字段", invalid_placement)

    def template_guards():
        checked = 0
        for chart in CHARTS:
            target = out / "guard-chart" / chart
            shutil.copytree(ROOT / "charts" / chart, target)
            (target / "values.schema.json").unlink()
            bad = merge(profiles[chart], {"placement": {"allowedNodeNames": ["worker-117", "worker-118", "ubuntu"]}})
            process = helm(chart, bad, chart_path=target, expected_failure=True)
            require("ubuntu/116" in process.stdout + process.stderr, "Template guard failed for an unrelated reason")
            checked += 1
        return {"schemaIndependentTemplateRejections": checked}
    record("PG17-U-H02", "即使移除测试副本 schema，模板也拒绝越界节点", template_guards)

    def pg17_only():
        for version in (16, 18, "17"):
            helm("neon-compute", merge(profiles["neon-compute"], {"compute": {"pgVersion": version}}), expected_failure=True)
        return {"rejectedVersions": [16, 18, "17"]}
    record("PG17-U-H03", "静态 VM 参数只接受整数 PG17", pg17_only)

    def device_plugin():
        override = image("separately-imported-device-plugin")
        objects = list(documents(helm("neonvm", merge(profiles["neonvm"],
                             {"images": {"devicePlugin": override}})).stdout))
        plugin = next(o for o in objects if o and o.get("kind") == "DaemonSet" and o["metadata"]["name"] == "neonvm-device-plugin")
        require(plugin["spec"]["template"]["spec"]["containers"][0]["image"] == override, "Device plugin override not wired")
        helm("neonvm", merge(profiles["neonvm"], {"images": {"devicePlugin": "example.invalid/plugin:latest"}}), expected_failure=True)
        return {"digestOverrideWired": True, "tagRejected": True}
    record("PG17-U-H04", "外部 device-plugin digest 可覆盖且 tag 被拒绝", device_plugin)

    def pool_isolation():
        snapshot = fixture_nodes()
        check_nodes(snapshot)
        rejects = 0
        for change in ("ubuntu-in-pool", "missing-worker", "worker-119-not-ready", "hostname-drift", "hard-taint"):
            bad = copy.deepcopy(snapshot)
            if change == "ubuntu-in-pool":
                bad["items"][0]["metadata"]["labels"][POOL_KEY] = POOL_VALUE
            elif change == "missing-worker":
                del bad["items"][2]
            elif change == "worker-119-not-ready":
                bad["items"][3]["status"]["conditions"][0]["status"] = "False"
            elif change == "hostname-drift":
                bad["items"][3]["metadata"]["labels"]["kubernetes.io/hostname"] = "ubuntu"
            else:
                bad["items"][3]["spec"]["taints"] = [{"key": "example.invalid/unconfigured", "effect": "NoSchedule"}]
            try:
                check_nodes(bad)
            except AssertionError:
                rejects += 1
            else:
                raise AssertionError("Unsafe node snapshot accepted: " + change)
        # 即使 Controller 追加宽泛 Linux/amd64 OR 分支，独立 selector 仍将候选集限定在池内。
        candidates = [n["metadata"]["name"] for n in snapshot["items"]
                      if n["metadata"]["labels"].get(POOL_KEY) == POOL_VALUE
                      and n["metadata"]["labels"].get("kubernetes.io/os") == "linux"
                      and n["metadata"]["labels"].get("kubernetes.io/arch") == "amd64"]
        require(candidates == list(NODES), "Pool does not bound the Controller OR case")
        return {"fixtureOnly": True, "negativeSnapshotsRejected": rejects, "controllerBroadOrStillConfined": candidates,
                "controlPlaneRoleOn119Accepted": True, "actualClusterMembership": "pending"}
    record("PG17-U-H05", "节点快照防错及 VM 独立 selector 的 OR 绕过保护", pool_isolation)

    def crd_integrity():
        lock = json.loads((ROOT / "locks/pg17-helm-crd-source.json").read_text())
        require(lock["commit"] == SOURCE_SHA, "Unexpected AS CRD source")
        bundled = {x["metadata"]["name"]: x for x in documents((ROOT / "charts/neonvm/crds/neonvm.yaml").read_text()) if x}
        original_text = subprocess.check_output(["git", "show", lock["chartBaseCommit"] + ":charts/neonvm/crds/neonvm.yaml"], cwd=ROOT, text=True)
        original = {x["metadata"]["name"]: x for x in documents(original_text) if x}
        for entry in lock["files"]:
            raw = subprocess.check_output(["git", "-C", str(args.autoscaling_source), "show", SOURCE_SHA + ":" + entry["path"]])
            require(hashlib.sha256(raw).hexdigest() == entry["sourceBlobSha256"], "Source blob digest drift")
            source = yaml.safe_load(raw)
            actual = bundled[entry["crd"]]
            spec = copy.deepcopy(actual["spec"])
            spec.pop("conversion", None)
            require(spec == source["spec"], "CRD spec differs from accurate AS source")
            require(hashlib.sha256(canonical(spec).encode()).hexdigest() == entry["specSha256"], "CRD lock digest drift")
            require(actual["spec"].get("conversion") == original[entry["crd"]]["spec"].get("conversion"),
                    "Original Chart conversion webhook changed")
            require(actual["metadata"]["annotations"].get("cert-manager.io/inject-ca-from") ==
                    original[entry["crd"]]["metadata"]["annotations"].get("cert-manager.io/inject-ca-from"),
                    "Original Chart CA injection changed")
        vm = bundled["virtualmachines.vm.neon.tech"]
        schema = next(v for v in vm["spec"]["versions"] if v["name"] == "v1")["schema"]["openAPIV3Schema"]
        bootstrap = schema["properties"]["spec"]["properties"]["dsgaBootstrap"]
        require("ready" in bootstrap["properties"], "Missing held/release schema")
        def count_rules(value):
            if isinstance(value, dict):
                return len(value.get("x-kubernetes-validations", [])) + sum(count_rules(v) for v in value.values())
            if isinstance(value, list):
                return sum(count_rules(v) for v in value)
            return 0
        rules = count_rules(schema)
        require(rules > 0, "Missing CEL guards")
        return {"source": SOURCE_SHA, "crdCount": len(bundled), "CELRuleCount": rules,
                "bootstrapFields": sorted(bootstrap["properties"]), "serverSideCRDValidation": "pending"}
    record("PG17-U-H06", "准确 AS 三 CRD/schema/CEL 与保留 webhook 的来源比对", crd_integrity)

    def lint_all():
        for chart in CHARTS:
            helm(chart, profiles[chart], action="lint")
        return {"charts": list(CHARTS), "strict": True, "kubeVersion": args.kube_version}
    record("PG17-S-H01", "七个相关 chart 的严格离线 lint", lint_all)

    rendered = {}
    def render_all():
        checked = []
        hooks = []
        for chart in CHARTS:
            result = helm(chart, profiles[chart])
            objects = [x for x in documents(result.stdout) if x]
            rendered[chart] = objects
            (out / (chart + ".yaml")).write_text(result.stdout)
            checked.extend(check_render(objects))
            hooks += [o["metadata"]["name"] for o in objects if o.get("kind") == "Job" and o["metadata"].get("annotations", {}).get("helm.sh/hook")]
        require(any(n.endswith("-minio-init") for n in hooks), "MinIO init hook not covered")
        controller = next(o for o in rendered["neonvm"] if o.get("kind") == "Deployment")
        require(controller["spec"]["template"]["spec"]["affinity"].get("podAntiAffinity"),
                "Controller spread anti-affinity was lost")
        for obj in rendered["neon-core"]:
            if obj.get("kind") == "Deployment" and obj["metadata"]["name"].startswith("safekeeper"):
                require(obj["spec"]["template"]["spec"]["affinity"].get("podAntiAffinity"),
                        "Safekeeper anti-affinity was lost")
        return {"workloads": checked, "hookJobs": hooks, "actualRuntimePlacement": "pending"}
    record("PG17-S-H02", "所有基本 PodSpec/VM/hook selector 与每个 affinity 分支及反亲和", render_all)

    def optional_coverage():
        overlay = {"minio": {"productStorage": {"enabled": True, "existingSecret": "offline-product-secret"}},
                   "storageController": {"enabled": True}, "compute": {"enabled": True, "pgVersion": 17,
                     "tenantId": "1" * 32, "timelineId": "2" * 32,
                     "image": {"repository": "example.invalid/pg17-offline/legacy-wrapper", "tag": "offline",
                               "digest": image("legacy-wrapper")}},
                   "computeResize": {"enabled": True, "image": image("legacy-cpu-resizer")},
                   "proxy": {"enabled": True, "legacyApiEnabled": True}}
        objects = [x for x in documents(helm("neon-core", merge(profiles["neon-core"], overlay)).stdout) if x]
        checked = check_render(objects)
        expected = {"compute", "compute-resizer", "proxy", "proxy-api", "storage-controller", "controller-db"}
        names = {o["metadata"]["name"] for o in objects if o.get("kind") == "Deployment"}
        require(expected <= names, "Optional PodSpec coverage missing: " + str(expected - names))
        require(any(o.get("kind") == "Job" and o["metadata"]["name"].endswith("-product-storage-init") for o in objects),
                "Optional product hook not covered")
        no_separation = [x for x in documents(helm("neon-core", merge(profiles["neon-core"],
                         {"safekeeper": {"requireNodeSeparation": False}})).stdout) if x]
        check_render(no_separation)
        reversed_nodes = [x for x in documents(helm("neon-compute", merge(profiles["neon-compute"],
                           {"placement": {"allowedNodeNames": list(reversed(NODES))}})).stdout) if x]
        check_render(reversed_nodes)
        return {"fixtureOnly": True, "workloads": checked, "unrelatedFeaturesEnabledOnlyOfflineForPlacementCoverage": True,
                "separationDisabledStillConfined": True, "allowlistOrderCanonicalized": True}
    record("PG17-S-H03", "仅离线启用旧可选分支以穷尽 PodSpec/hook；本轮运行不启用这些功能", optional_coverage)

    # 精确绑定本次未提交工作区；主代理统一提交后可重新执行并绑定提交。
    source_files = set()
    for chart in CHARTS:
        source_files.update(p for p in (ROOT / "charts" / chart).rglob("*") if p.is_file())
        source_files.add(ROOT / "profiles/lab" / (chart + ".json"))
    source_files.update((ROOT / "tools/check-pg17-helm.py", ROOT / "tools/check-source.mjs", ROOT / "locks/pg17-helm-crd-source.json",
                         ROOT / "profiles/pg17-memory/placement.json", ROOT / "package.json"))
    source_inputs = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(source_files)}
    (out / "source-inputs.json").write_text(json.dumps(source_inputs, ensure_ascii=False, indent=2) + "\n")
    summary = {"sourceInputsSha256": hashlib.sha256(canonical(source_inputs).encode()).hexdigest(),
               "suite": "PG17 Helm foundation", "mode": "offline-only-no-cluster-access",
               "startedAt": stamp, "kubeVersion": args.kube_version,
               "helmVersion": subprocess.check_output([binary, "version", "--short"], text=True).strip(),
               "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
               "baseCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "status": "pass" if all(r["status"] == "pass" for r in results) else "fail",
               "results": results, "liveGatesPending": ["PG17-S-H04 actual NodeList pool/Ready/taint validation",
                  "server-side CRD/CEL dry-run and existing storedVersions adoption",
                  "real source-built image provenance and CRI digest verification", "DSGA runtime wiring and PG17 autoscaling E2E"]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("Evidence: " + str(out))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        sys.exit(1)
