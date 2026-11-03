#!/usr/bin/env python3
"""PG17 primary-only定向离线渲染：12项，禁止apply，不连接集群。
依赖：python3、PyYAML、helm、git；全部fixture为渲染占位，不创建VM/Secret。
"""
import argparse, copy, hashlib, io, json, pathlib, subprocess, tarfile, time
import yaml

BASELINE = "d7569450ea13058c8f25afa3ee37c940a5e63023"
# 固定原已验收fixture；包括公共镜像digest，无私钥或认证资料。
FIXTURES = {'vm-default-before': {'experimentalAcknowledged': True, 'images': {'controller': '127.0.0.1:5001/neon-candidate/neonvm-controller@sha256:0597396bbafce733f657d9f3761712ad2691b5a0164858984b3658d01b3d5216', 'runner': '127.0.0.1:5001/neon-candidate/neonvm-runner@sha256:8f3f5e50bb27b13ec348cbfd60277cffea03f456983796454543b4b4108d39ee', 'vxlanController': '127.0.0.1:5001/neon-candidate/neonvm-vxlan-controller@sha256:898c2ef8fcebd2811630c01dfddde57e35fc5ff60cabd1f6cbd55816140ac103'}}, 'compute-default-before': {'experimentalAcknowledged': True, 'compute': {'image': '127.0.0.1:5001/neon-candidate/pg17-guest@sha256:70e74c42c415793a6556132e3385b14335e52801d487a3deb8ba3ae099bde0d1', 'tenantId': '11111111111111111111111111111111', 'timelineId': '22222222222222222222222222222222'}}, 'vm-primary-only': {'experimentalAcknowledged': True, 'images': {'controller': '127.0.0.1:5001/neon-candidate/neonvm-controller@sha256:0597396bbafce733f657d9f3761712ad2691b5a0164858984b3658d01b3d5216', 'runner': '127.0.0.1:5001/neon-candidate/neonvm-runner@sha256:8f3f5e50bb27b13ec348cbfd60277cffea03f456983796454543b4b4108d39ee', 'vxlanController': '127.0.0.1:5001/neon-candidate/neonvm-vxlan-controller@sha256:898c2ef8fcebd2811630c01dfddde57e35fc5ff60cabd1f6cbd55816140ac103'}, 'network': {'secondary': {'enabled': False}}, 'controller': {'replicas': 1, 'nodeSelector': {'kubernetes.io/hostname': 'worker-118'}, 'runnerCgroupEnabled': True}}, 'compute-trusted-primary-render-only': {'experimentalAcknowledged': True, 'compute': {'image': '127.0.0.1:5001/neon-candidate/pg17-guest@sha256:70e74c42c415793a6556132e3385b14335e52801d487a3deb8ba3ae099bde0d1', 'tenantId': '11111111111111111111111111111111', 'timelineId': '22222222222222222222222222222222', 'startupMode': 'trusted-runtime-v1', 'name': 'cp-d8d85ed796068ab5', 'existingConfigSecret': 'cp-d8d85ed796068ab5-config', 'cpu': {'min': 2, 'use': 2, 'max': 2}, 'memory': {'slotSize': '1Gi', 'minSlots': 7, 'useSlots': 7, 'maxSlots': 8, 'minBound': '7Gi', 'maxBound': '8Gi'}, 'runtime': {'executionModel': 'trusted-controller-v1', 'projectId': 'render-only-project', 'endpointId': 'ep_d8d85ed796068ab5', 'incarnation': '33333333333333333333333333333333', 'computeInstanceId': 'cp-d8d85ed796068ab5', 'runnerImage': '127.0.0.1:5001/neon-candidate/neonvm-runner@sha256:8f3f5e50bb27b13ec348cbfd60277cffea03f456983796454543b4b4108d39ee', 'kernelImage': '127.0.0.1:5001/neon-candidate/vm-kernel@sha256:6f4c2cf013b56212be2cc206daa2f096ada54a2fd43a9a3e804a127aabb51bea', 'serviceAccountName': 'render-only-account', 'configMountPath': '/neonvm/config', 'configFile': 'compute-public.json', 'postgresPort': 55432}}, 'network': {'secondary': {'enabled': False}}}}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def objects(path):
    docs = [x for x in yaml.safe_load_all(path.read_text()) if x]
    result = {(x["kind"], x["metadata"].get("namespace", ""), x["metadata"]["name"]): x for x in docs}
    require(len(result) == len(docs), "duplicate rendered object")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=pathlib.Path, required=True, help="新的归档目录；拒绝覆盖历史结果")
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    # 精确Git基线，不下载、不依赖/data中的临时fixture。
    archive = subprocess.check_output(["git", "-C", str(repo), "archive", BASELINE, "charts/neonvm", "charts/neon-compute"])
    baseline = output / "baseline"
    baseline.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tf:
        for entry in tf.getmembers():
            require(not entry.name.startswith("/") and ".." not in pathlib.PurePosixPath(entry.name).parts, "unsafe baseline path")
        tf.extractall(baseline)
    vm = copy.deepcopy(FIXTURES["vm-default-before"])
    compute = copy.deepcopy(FIXTURES["compute-default-before"])
    primary = copy.deepcopy(FIXTURES["vm-primary-only"])
    compute_primary = copy.deepcopy(compute)
    compute_primary["network"] = {"secondary": {"enabled": False}}
    cases = [
        ("vm-default-before", "neonvm", baseline, vm, None),
        ("vm-default-after", "neonvm", repo, vm, None),
        ("compute-default-before", "neon-compute", baseline, compute, None),
        ("compute-default-after", "neon-compute", repo, compute, None),
        ("vm-primary-only", "neonvm", repo, primary, None),
        ("compute-primary-only", "neon-compute", repo, compute_primary, None),
        ("compute-trusted-primary-render-only", "neon-compute", repo, FIXTURES["compute-trusted-primary-render-only"], None),
    ]
    # 仅验证此次新增hostname约束和boolean合同，不扩展其它功能矩阵。
    for name, selector, error in [
        ("negative-forbidden-node", {"kubernetes.io/hostname": "ubuntu"}, "controller.nodeSelector.kubernetes.io/hostname"),
        ("negative-override-arch", {"kubernetes.io/arch": "arm64"}, "Additional property kubernetes.io/arch"),
        ("negative-override-pool", {"neon.tech/pg17-memory-pool": "other"}, "Additional property neon.tech/pg17-memory-pool"),
        ("negative-wrong-map", "worker-118", "Expected: object"),
    ]:
        values = copy.deepcopy(primary)
        values["controller"]["nodeSelector"] = selector
        cases.append((name, "neonvm", repo, values, error))
    values = copy.deepcopy(primary)
    values["network"]["secondary"]["enabled"] = "false"
    cases.append(("negative-network-string", "neonvm", repo, values, "Expected: boolean"))
    receipt = {"baseline_commit": BASELINE, "cases": [], "cluster_apply_performed": False, "host_network_changed": False}
    for name, chart, root, values, expected_error in cases:
        fixture = output / (name + "-values.json")
        fixture.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n")
        namespace = "neonvm-system" if chart == "neonvm" else "neon-render-only"
        command = ["helm", "template", "primary-contract", str(root / "charts" / chart), "--namespace", namespace,
                   "--kube-version", "1.31.2", "--include-crds", "-f", str(fixture)]
        run = subprocess.run(command, capture_output=True, text=True)
        (output / (name + ".yaml")).write_text(run.stdout)
        (output / (name + ".stderr")).write_text(run.stderr)
        require((run.returncode == 0) == (expected_error is None), name + ": unexpected exit")
        if expected_error:
            require(expected_error in run.stderr, name + ": failed for unrelated reason")
        receipt["cases"].append({"name": name, "exit": run.returncode, "expected_success": expected_error is None, "command": command})
    before, after = objects(output / "vm-default-before.yaml"), objects(output / "vm-default-after.yaml")
    extra = ("CustomResourceDefinition", "", "network-attachment-definitions.k8s.cni.cncf.io")
    require(set(after) - set(before) == {extra}, "unexpected new default object")
    require({k: v for k, v in after.items() if k != extra} == before, "default NeonVM AST differs")
    require(objects(output / "compute-default-before.yaml") == objects(output / "compute-default-after.yaml"), "default Compute AST differs")
    current = objects(output / "vm-primary-only.yaml")
    require([v["metadata"]["name"] for v in current.values() if v["kind"] == "NetworkAttachmentDefinition"] == ["neonvm-overlay-ipam"], "primary NAD set differs")
    require(not any("vxlan" in k[2] for k in current), "VXLAN resource leaked")
    require("cp -rf" not in (output / "vm-primary-only.yaml").read_text(), "host CNI copy leaked")
    deployment = current[("Deployment", "neonvm-system", "neonvm-controller")]
    require(deployment["spec"]["replicas"] == 1, "controller replicas differs")
    expected_selector = {"kubernetes.io/os": "linux", "kubernetes.io/arch": "amd64", "neon.tech/pg17-memory-pool": "worker-117-worker-118-worker-119"}
    require(deployment["spec"]["template"]["spec"]["nodeSelector"] == dict(expected_selector, **{"kubernetes.io/hostname": "worker-118"}), "controller selector weakened")
    for obj in current.values():
        if obj["kind"] == "DaemonSet":
            pod = obj["spec"]["template"]["spec"]
            require(pod["nodeSelector"] == expected_selector, "DS selector changed")
            terms = pod["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
            require(all({"key": "kubernetes.io/hostname", "operator": "In", "values": ["worker-117", "worker-118", "worker-119"]} in term["matchExpressions"] for term in terms), "DS node pool changed")
    for name in ["compute-primary-only", "compute-trusted-primary-render-only"]:
        spec = next(v["spec"] for v in objects(output / (name + ".yaml")).values() if v["kind"] == "VirtualMachine")
        require("extraNetwork" not in spec, "ExtraNetwork must be absent, not disabled")
        if name.startswith("compute-trusted"):
            require(spec["dsgaBootstrap"]["ready"] is False, "render fixture must remain held")
            require(spec["guest"]["cpus"] == {"min": 2, "use": 2, "max": 2}, "CPU geometry differs")
            require(spec["guest"]["memorySlots"] == {"min": 7, "use": 7, "max": 8}, "memory geometry differs")
    receipt.update(status="PASS_FOCUSED_RENDER_CONTRACT", focused_commands=len(cases),
                   default_old_AST_equal=True, only_new_default_object=extra[2],
                   primary_only_ipam_NAD_retained=True, primary_only_no_extraNetwork_no_VXLAN_no_host_CNI_copy=True,
                   controller118_replica1_DS_three_worker_pool=True, render_only_fixtures_not_actual_service_birth=True,
                   script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(), seconds=time.monotonic()-started)
    result = output / "result.json"
    result.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "focused_commands": len(cases), "result": str(result), "sha256": hashlib.sha256(result.read_bytes()).hexdigest(), "seconds": receipt["seconds"]}))


if __name__ == "__main__":
    main()
