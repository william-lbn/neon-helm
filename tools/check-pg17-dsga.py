#!/usr/bin/env python3
"""PG17 DSGA Helm 配置门槛；离线渲染或读取调用方提供的快照，不执行 kubectl/部署。"""
import sys
sys.dont_write_bytecode = True
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import yaml

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("pg17_helm_foundation", ROOT / "tools/check-pg17-helm.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
CHART = ROOT / "charts/neon-autoscaler"
AUDIENCE = "neon-dsga-credential-broker"
SOURCE = "79ec6501da167e6ae7abb47a48065e722865e611"
VM_UID = "00000000-0000-0000-0000-000000000017"
FACTS = json.loads((CHART / "files/pg17-node-identities.json").read_text())
require = base.require
merge = base.merge

GO_HELPER = r'''package main

import (
 "context"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "io/fs"
 "fmt"
 "os"
 "path/filepath"
 "runtime"
 "strings"

 "go.uber.org/zap"
 "github.com/neondatabase/autoscaling/pkg/agent"
 "github.com/neondatabase/autoscaling/pkg/dsga/hostscheduler"
)

func must(ok bool, message string) { if !ok { panic(message) } }
func sourceSnapshot() (string, int) {
 inputs := map[string]string{}
 err := filepath.WalkDir("/workspace", func(path string, entry fs.DirEntry, err error) error {
  if err != nil { return err }
  if entry.IsDir() { return nil }
  if filepath.Ext(path) != ".go" && entry.Name() != "go.mod" && entry.Name() != "go.sum" { return nil }
  raw, err := os.ReadFile(path)
  if err != nil { return err }
  sum := sha256.Sum256(raw)
  relative, err := filepath.Rel("/workspace", path)
  if err != nil { return err }
  inputs[relative] = hex.EncodeToString(sum[:])
  return nil
 })
 must(err == nil, "AS immutable build-context source walk failed")
 raw, err := json.Marshal(inputs)
 must(err == nil, "AS source manifest encode failed")
 raw = append(raw, '\n')
 must(os.WriteFile("/receipt/as-go-context-inputs.json", raw, 0644) == nil, "AS source manifest export failed")
 sum := sha256.Sum256(raw)
 return hex.EncodeToString(sum[:]), len(inputs)
}
func main() {
 cfg, err := agent.ReadConfig("/helm-fixture/agent.json")
 must(err == nil && cfg != nil && cfg.DSGA != nil, fmt.Sprintf("actual Agent.ReadConfig rejected Helm output: %v", err))
 var plugin struct { Host *hostscheduler.Config `json:"dsgaHost"` }
 raw, err := os.ReadFile("/helm-fixture/plugin.json")
 must(err == nil && json.Unmarshal(raw, &plugin) == nil && plugin.Host != nil, "typed Host config decode failed")
 must(plugin.Host.Validate("autoscale-scheduler") == nil, "actual Host Config.Validate rejected Helm output")
 must(uint64(plugin.Host.Nodes[0].SystemBytes) == uint64(9007199254740993), "exact uint64 string lost precision")
 runner := agent.MainRunner{Config: cfg}
 err = runner.Run(zap.NewNop(), context.Background())
 must(err != nil && strings.Contains(err.Error(), "K8S_POD_UID"), "missing DownwardAPI Pod UID was not rejected before Kubernetes access")
 original, err := os.ReadFile("/helm-fixture/agent.json")
 must(err == nil, "missing original Agent fixture")
 rejected := 0
 for _, variant := range []string{"missing-qualification", "invalid-window", "http-gateway"} {
  var value map[string]any
  must(json.Unmarshal(original, &value) == nil, "bad original fixture")
  dsga := value["dsga"].(map[string]any)
  if variant == "missing-qualification" { dsga["prepareQualifications"] = map[string]any{} }
  if variant == "invalid-window" {
   for _, v := range dsga["automaticMemory"].(map[string]any) { v.(map[string]any)["shrinkWindowSeconds"] = float64(1) }
  }
  if variant == "http-gateway" { dsga["gatewayURL"] = "http://offline-gateway.invalid:8444" }
  encoded, err := json.Marshal(value)
  must(err == nil, "failed to encode negative fixture")
  path := filepath.Join("/tmp", variant+".json")
  must(os.WriteFile(path, encoded, 0600) == nil, "failed to write negative fixture")
  _, err = agent.ReadConfig(path)
  must(err != nil, "actual Agent.ReadConfig accepted "+variant)
  rejected++
 }
 sourceHash, sourceCount := sourceSnapshot()
 data, _ := json.Marshal(map[string]any{"mode":"actual-linux-go-typed-contract", "goVersion":runtime.Version(),
  "immutableASGoContextManifestSha256":sourceHash, "immutableASGoContextFileCount":sourceCount,
  "agentReadConfig":"pass","hostConfigValidate":"pass","missingPodUIDRejectedBeforeKubeAccess":true,
  "actualAgentNegativeConfigsRejected":rejected,"networkAccess":"disabled",
  "platformQualification":"not-certified; synthetic offline inputs only"})
 must(os.WriteFile("/receipt/typed-contract.json", append(data, '\n'), 0644) == nil, "receipt write failed")
}
'''

DOCKERFILE = """FROM 127.0.0.1:5001/neon/pg17-dev-tools:linux-v1 AS check
WORKDIR /workspace
ENV GOPATH=/go GOMODCACHE=/go/pkg/mod GOCACHE=/root/.cache/go-build GOPROXY=off GOSUMDB=off
COPY . .
COPY --from=helmfixture . /helm-fixture
ARG PG17_CONTRACT_NONCE
RUN --mount=type=cache,id=autoscaling-gomod-amd64-shared-v2,target=/go/pkg/mod,sharing=shared \\
    --mount=type=cache,id=autoscaling-gobuild-amd64,target=/root/.cache/go-build,sharing=shared \\
    printf 'ACTUAL_PG17_HELM_CONTRACT=%s\\n' "$PG17_CONTRACT_NONCE" && mkdir /receipt && \\
    /opt/go/bin/go run /helm-fixture/contract.go
FROM scratch
COPY --from=check /receipt/ /
"""


def prepare_cache(args):
    """仅显式准备依赖缓存；与禁网契约分开，绝不运行测试或改 mod/sum。"""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    out = ROOT / "artifacts/pg17-dsga-cache" / stamp
    out.mkdir(parents=True, exist_ok=False)
    shared_env = ROOT.parents[1] / "config/env.sh"
    require(shared_env.is_file(), "Existing trusted explicit proxy environment is required")
    probes = []
    chosen = None
    for endpoint in ("https://proxy.golang.org", "https://goproxy.cn"):
        url = endpoint + "/github.com/coder/websocket/@v/v1.8.13.info"
        command = ["bash", "-c",
                   'source "$1"; test -n "$HTTP_PROXY"; exec curl --silent --show-error --noproxy "" --proxy "$HTTP_PROXY" --connect-timeout 8 --max-time 25 --output /dev/null --write-out "%{http_code}" "$2"',
                   "pg17-explicit-proxy-probe", str(shared_env), url]
        probe = subprocess.run(command, text=True, capture_output=True, timeout=35)
        probes.append({"url": url, "exitCode": probe.returncode, "httpStatus": probe.stdout.strip(),
                       "explicitExistingProxy": True})
        if probe.returncode == 0 and probe.stdout.strip() == "200":
            chosen = endpoint
            break
    (out / "proxy-probes.json").write_text(json.dumps(probes, indent=2) + "\n")
    require(chosen is not None, "Existing explicit proxy did not pass an actual Go module info request")
    dockerfile = """FROM 127.0.0.1:5001/neon/pg17-dev-tools:linux-v1 AS prepare
WORKDIR /workspace
ENV GOPATH=/go GOMODCACHE=/go/pkg/mod GOCACHE=/root/.cache/go-build GOSUMDB=off
COPY . .
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG MODULE_PROXY
ENV GOPROXY=$MODULE_PROXY
ARG PG17_CACHE_PREP_NONCE
RUN --mount=type=cache,id=autoscaling-gomod-amd64-shared-v2,target=/go/pkg/mod,sharing=shared \\
    --mount=type=cache,id=autoscaling-gobuild-amd64,target=/root/.cache/go-build,sharing=shared \\
    printf 'ACTUAL_DEPENDENCY_PREP=%s\\n' "$PG17_CACHE_PREP_NONCE" && mkdir /receipt && \\
    sha256sum go.mod go.sum > /receipt/modsum-before.txt && \\
    /opt/go/bin/go list -mod=readonly -deps ./pkg/agent ./pkg/dsga/hostscheduler > /receipt/dependencies.txt && \\
    sha256sum go.mod go.sum > /receipt/modsum-after.txt && cmp /receipt/modsum-before.txt /receipt/modsum-after.txt
FROM scratch
COPY --from=prepare /receipt/ /
"""
    path = out / "Dockerfile"
    path.write_text(dockerfile)
    export = out / "export"
    command = ["docker", "buildx", "build", "--builder", "neon-data", "--network", "host", "--allow", "network.host",
               "--progress", "plain", "--build-arg", "MODULE_PROXY=" + chosen,
               "--build-arg", "PG17_CACHE_PREP_NONCE=" + str(time.time_ns())]
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"):
        command += ["--build-arg", name]
    command += ["--output", "type=local,dest=" + str(export), "-f", str(path), str(args.autoscaling_source)]
    command = ["bash", "-c", 'source "$1"; export HTTPS_PROXY="$HTTP_PROXY" http_proxy="$HTTP_PROXY" https_proxy="$HTTP_PROXY"; shift; exec "$@"', "pg17-cache-prepare", str(shared_env), *command]
    (out / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (out / "prepare.log").open("w") as log:
        process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, timeout=900)
    result = {"id": "PG17-ENV-H01", "mode": "dependency-cache-preparation-only", "status": "pass" if process.returncode == 0 else "fail",
              "explicitProxyProbed": True, "moduleProxy": chosen, "goModuleCacheID": "autoscaling-gomod-amd64-shared-v2",
              "sourceModSumChanges": "none: readonly plus before/after cmp" if process.returncode == 0 else "inspect log",
              "testsExecuted": False, "clusterMutation": False,
              "loadedDockerfileSha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("PG17-ENV-H01 " + result["status"] + " Evidence: " + str(out), flush=True)
    return 0 if process.returncode == 0 else 1


def load(path):
    docs = base.documents(Path(path).read_text())
    require(len(docs) == 1 and isinstance(docs[0], dict), "Expected one strict YAML/JSON object")
    return docs[0]


def validate_original_inputs(values, nodes, leases):
    """只验证原身份/范围，不把结构正确或正数字节当平台预算认证。"""
    base.check_nodes(nodes)
    d = values.get("dsga", {})
    require(d.get("enabled") is True and d.get("pgVersion") == 17, "PG17 DSGA must be explicitly enabled")
    domains = d.get("scheduler", {}).get("nodes", [])
    require(len(domains) == 3, "Exactly three original Host domains required")
    by_node = {n["metadata"]["name"]: n for n in nodes["items"]}
    require(leases.get("kind") in ("LeaseList", "List"), "Expected a complete original LeaseList snapshot")
    by_lease = {(x["metadata"]["namespace"], x["metadata"]["name"]): x for x in leases["items"]}
    seen = set()
    lease_uids = set()
    for domain in domains:
        b = domain["binding"]
        name = b["node_name"]
        require(name in base.NODES and name not in seen, "Duplicate or excluded Host Node")
        seen.add(name)
        node = by_node[name]
        require(b["node_uid"] == node["metadata"]["uid"] == FACTS["allowedNodeUIDs"][name],
                "Original Node UID differs; same-name recreation cannot be adopted")
        key = (b["namespace"], b["lease_name"])
        require(key in by_lease, "Original Host Lease absent; Helm never creates/replaces it")
        lease = by_lease[key]
        require(lease["metadata"]["uid"] == b["lease_uid"] and b["lease_uid"] not in lease_uids,
                "Original Lease UID differs or repeats")
        lease_uids.add(b["lease_uid"])
        require(lease["metadata"].get("resourceVersion") and not lease["metadata"].get("deletionTimestamp"),
                "Lease must be a retained original object")
        require(lease["metadata"].get("annotations", {}).get("internal.autoscaling.neon.tech/dsga-host-lease-v1") ==
                "1:" + b["node_uid"] + ":" + name, "Original Host Lease marker differs")
        owners = lease["metadata"].get("ownerReferences", [])
        require(len(owners) == 1 and owners[0].get("apiVersion") == "v1" and owners[0].get("kind") == "Node"
                and owners[0].get("name") == name and owners[0].get("uid") == b["node_uid"]
                and owners[0].get("controller") is True, "Original Host Lease Node owner differs")
        if "initialize_at_resource_version" in domain:
            require(domain["initialize_at_resource_version"] == node["metadata"]["resourceVersion"],
                    "Frozen first-initialization Node resourceVersion changed; never refresh it automatically")
        else:
            require(node["metadata"].get("annotations", {}).get("internal.autoscaling.neon.tech/dsga-host-ledger-v1"),
                    "Uninitialized Node requires an explicit frozen original resourceVersion")
    require(seen == set(base.NODES), "Original Host domain list differs from the explicit allowlist")
    return {"identityAndScope": "pass", "nodeUIDs": FACTS["allowedNodeUIDs"],
            "leaseCount": len(domains), "platformBudgetsAndQualifications": "not-certified-by-this-check",
            "sourceTypedRuntimeValidation": "required", "deploymentAuthorization": "not-issued"}


def fixture():
    value = json.loads((ROOT / "profiles/lab/neon-autoscaler.json").read_text())
    defaults = yaml.safe_load((CHART / "values.yaml").read_text())
    value = merge(defaults, value)
    value["compatibility"] = {"expectedKubernetesMinor": "31", "allowUntestedKubernetes": False}
    value["images"] = {key: base.image("dsga-" + key) for key in defaults["images"]}
    value["dsga"]["enabled"] = True
    a = value["dsga"]["agent"]
    a["gatewayURL"] = "https://offline-gateway.invalid:8444"
    a["managementCASecret"] = "offline-public-management-ca"
    a["prepareQualifications"] = {VM_UID: {"claim": {"name": "offline-qualification-only",
                                      "uid": "00000000-0000-0000-0000-000000000099"}, "sha256": "a" * 64}}
    a["automaticMemory"] = {VM_UID: {"targets": [{"vmMemoryBytes": "1073741824", "buffers": 16384},
         {"vmMemoryBytes": "2147483648", "buffers": 32768}], "sampleIntervalSeconds": 5,
         "maximumSampleGapSeconds": 20, "growWindowSeconds": 15, "shrinkWindowSeconds": 60,
         "cooldownSeconds": 30, "requestDeadlineSeconds": 120, "shrinkThresholdPermille": 200,
         "growThresholdPermille": 700, "emergencyThresholdPermille": 900}}
    value["dsga"]["scheduler"]["nodes"] = []
    for i, name in enumerate(base.NODES):
        value["dsga"]["scheduler"]["nodes"].append({
            "binding": {"node_name": name, "node_uid": FACTS["allowedNodeUIDs"][name],
                        "namespace": "offline-host-domain", "lease_name": "offline-lease-" + name,
                        "lease_uid": "00000000-0000-0000-0000-" + str(i + 1).zfill(12)},
            "profile": {"id": "OFFLINE-NOT-CERTIFIED", "scheduler_name": "autoscale-scheduler",
                        "vm_overhead_bytes": "1048576", "pod_overhead_bytes": "1048576"},
            "system_bytes": "9007199254740993" if i == 0 else "1048576",
            "initialize_at_resource_version": str(i + 1)})
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--autoscaling-source", type=Path, default=ROOT.parent / "autoscaling")
    parser.add_argument("--prepare-cache", action="store_true", help="显式探测现有代理并仅 go list 预取 Agent/Host 依赖；与禁网测试分开")
    parser.add_argument("--typed-contract", action="store_true", help="复用既有 BuildKit/Go 缓存执行真实 AS ReadConfig/Validate；不部署")
    parser.add_argument("--check-inputs", type=Path)
    parser.add_argument("--nodes", type=Path)
    parser.add_argument("--leases", type=Path)
    args = parser.parse_args()
    if args.prepare_cache:
        require(not args.typed_contract and not args.check_inputs, "Cache preparation and actual test modes must be separate")
        return prepare_cache(args)
    if args.check_inputs:
        require(args.nodes and args.leases, "Actual NodeList and original LeaseList snapshots are required")
        print(json.dumps(validate_original_inputs(load(args.check_inputs), load(args.nodes), load(args.leases)),
                         ensure_ascii=False, indent=2))
        return 0
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    out = args.output or ROOT / "artifacts/pg17-dsga" / stamp
    out.mkdir(parents=True, exist_ok=False)
    empty = out / "offline-only.kubeconfig"
    empty.write_text("apiVersion: v1\nkind: Config\nclusters: []\nusers: []\ncontexts: []\ncurrent-context: \"\"\n")
    empty.chmod(0o600)
    environment = dict(os.environ, KUBECONFIG=str(empty), HELM_NO_PLUGINS="1")
    values = fixture()
    (out / "OFFLINE-NOT-DEPLOYABLE.json").write_text(json.dumps(values, indent=2) + "\n")
    sequence = 0
    results = []
    output = {}

    def helm(value, action="template", fail=False, kube="1.31.2"):
        nonlocal sequence
        sequence += 1
        path = out / (str(sequence) + "-OFFLINE.json")
        path.write_text(json.dumps(value, indent=2) + "\n")
        command = [os.environ.get("HELM_BIN", "helm"), action, str(CHART), "-f", str(path)]
        if action == "lint":
            command.append("--strict")
        else:
            command += ["-n", "default", "--kube-version", kube]
        run = subprocess.run(command, cwd=ROOT, env=environment, text=True, capture_output=True, timeout=60)
        (out / (str(sequence) + ".stdout.txt")).write_text(run.stdout)
        (out / (str(sequence) + ".stderr.txt")).write_text(run.stderr)
        require((run.returncode != 0) if fail else (run.returncode == 0), "Helm result differs; see log " + str(sequence))
        return run

    def record(identity, description, run):
        started = time.monotonic()
        try:
            result = {"id": identity, "description": description, "status": "pass", "detail": run()}
        except Exception as error:
            result = {"id": identity, "description": description, "status": "fail",
                      "error": type(error).__name__ + ": " + str(error)}
        result["seconds"] = round(time.monotonic() - started, 3)
        results.append(result)
        (out / (identity + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(identity + " " + result["status"] + " " + result.get("error", ""), flush=True)

    def render():
        helm(values, "lint")
        objects = [x for x in base.documents(helm(values).stdout) if x]
        base.check_render(objects)
        agent_cm = next(x for x in objects if x["kind"] == "ConfigMap" and x["metadata"]["name"] == "autoscaler-agent-config")
        scheduler_cm = next(x for x in objects if x["kind"] == "ConfigMap" and x["metadata"]["name"] == "scheduler-plugin-config")
        output["agent"] = json.loads(agent_cm["data"]["config.json"])
        output["scheduler"] = json.loads(scheduler_cm["data"]["autoscale-enforcer-config.json"])
        output["objects"] = objects
        ds = next(x for x in objects if x["kind"] == "DaemonSet")
        pod = ds["spec"]["template"]["spec"]
        container = pod["containers"][0]
        require(next(x for x in container["env"] if x["name"] == "K8S_POD_UID")["valueFrom"]["fieldRef"]["fieldPath"] == "metadata.uid",
                "Pod UID must come from actual DownwardAPI, never a values literal")
        token = next(x for x in pod["volumes"] if x["name"] == "dsga-broker-token")["projected"]["sources"]
        require(token == [{"serviceAccountToken": {"audience": AUDIENCE, "expirationSeconds": 600, "path": "token"}}],
                "Dedicated audience projection differs")
        secret = next(x for x in pod["volumes"] if x["name"] == "dsga-management-ca")["secret"]
        require(secret["items"] == [{"key": "ca.crt", "path": "ca.crt"}], "Agent CA projection exposes other Secret keys")
        require(all(m.get("readOnly") is True and "subPath" not in m for m in container["volumeMounts"]),
                "Config/CA/token must be read-only and preserve atomic projection rotation")
        config = output["agent"]["dsga"]
        require(config["managementCAFile"] == "/etc/neon-dsga/management/ca.crt" and
                config["projectedTokenFile"] == "/var/run/secrets/neon-dsga/token", "Trusted file paths not wired")
        require(output["scheduler"]["dsgaHost"]["nodes"] == values["dsga"]["scheduler"]["nodes"], "Host inputs changed")
        require(output["scheduler"]["dsgaHost"]["nodes"][0]["system_bytes"] == "9007199254740993", "Exact uint64 string rounded")
        (out / "agent.json").write_text(agent_cm["data"]["config.json"])
        (out / "plugin.json").write_text(scheduler_cm["data"]["autoscale-enforcer-config.json"])
        return {"fixtureOnly": True, "pgVersion": 17, "podUID": "DownwardAPI", "tokenAudience": AUDIENCE,
                "trustedSourceOnly": True, "exactUint64StringsPreserved": True}
    record("PG17-U-H07", "DSGA Agent CA/token/PodUID 与 Scheduler 精确原输入渲染接线", render)

    def negatives():
        cases = [
          {"dsga": {"pgVersion": 16}},
          {"compatibility": {"allowUntestedKubernetes": True}},
          {"compatibility": {"expectedKubernetesMinor": "36"}},
          {"dsga": {"agent": {"gatewayURL": "http://offline-gateway.invalid"}}},
          {"dsga": {"agent": {"gatewayURL": "https://user:pass@offline-gateway.invalid"}}},
          {"dsga": {"agent": {"gatewayURL": "https://offline-gateway.invalid/changed-path"}}},
          {"dsga": {"agent": {"gatewayURL": "https://offline-gateway.invalid?query=1"}}},
          {"dsga": {"agent": {"managementCASecret": ""}}},
          {"dsga": {"agent": {"tokenAudience": "neon-dsga"}}},
          {"dsga": {"agent": {"tokenAudience": "https://kubernetes.default.svc"}}},
          {"dsga": {"agent": {"tokenExpirationSeconds": 86400}}},
          {"dsga": {"agent": {"computeTimeoutSeconds": 30}}},
          {"dsga": {"agent": {"requestTimeoutSeconds": 31}}},
          {"dsga": {"agent": {"pollIntervalSeconds": 0}}},
          {"dsga": {"agent": {"prepareQualifications": {VM_UID: {"sha256": "not-a-source"}}}}},
          {"dsga": {"agent": {"prepareQualifications": {VM_UID: None}}}},
          {"dsga": {"agent": {"automaticMemory": {VM_UID: {"shrinkWindowSeconds": 1}}}}},
          {"dsga": {"agent": {"automaticMemory": {VM_UID: {"shrinkThresholdPermille": 800}}}}},
          {"dsga": {"scheduler": {"nodes": []}}},
          {"dsga": {"scheduler": {"unknownBudget": "1"}}},
          {"dsga": {"unknown": True}}]
        for overlay in cases:
            helm(merge(values, overlay), fail=True)
        for mutation in ("foreign-node-uid", "duplicate-domain", "numeric-budget", "zero-budget", "overflow-budget",
                         "wrong-scheduler", "unknown-node-field", "reversed-targets"):
            bad = copy.deepcopy(values)
            n = bad["dsga"]["scheduler"]["nodes"]
            if mutation == "foreign-node-uid": n[0]["binding"]["node_uid"] = "00000000-0000-0000-0000-000000000777"
            if mutation == "duplicate-domain": n[1]["binding"]["lease_name"] = n[0]["binding"]["lease_name"]
            if mutation == "numeric-budget": n[0]["system_bytes"] = 1
            if mutation == "zero-budget": n[0]["profile"]["vm_overhead_bytes"] = "0"
            if mutation == "overflow-budget": n[0]["system_bytes"] = "18446744073709551616"
            if mutation == "wrong-scheduler": n[0]["profile"]["scheduler_name"] = "default-scheduler"
            if mutation == "unknown-node-field": n[0]["guessBudget"] = "1"
            if mutation == "reversed-targets": bad["dsga"]["agent"]["automaticMemory"][VM_UID]["targets"].reverse()
            helm(bad, fail=True)
        helm(values, fail=True, kube="1.36.4")
        # 准确 required overlay 未补真实域/CA 时必须失败，不能静默走 legacy。
        required = merge(json.loads((ROOT / "profiles/lab/neon-autoscaler.json").read_text()),
                         json.loads((ROOT / "profiles/pg17-memory/neon-autoscaler-required.json").read_text()))
        helm(required, fail=True)
        return {"rejectedConfigs": len(cases) + 10, "requiredIncompleteProfileRejected": True}
    record("PG17-U-H08", "PG17/专用身份/原域/精确预算/策略非法输入与不完整启用拒绝", negatives)

    def rbac():
        objects = output["objects"]
        node = next(x for x in objects if x["kind"] == "ClusterRole" and x["metadata"]["name"] == "neon-dsga-scheduler-node-ledger")
        require(node["rules"] == [{"apiGroups": [""], "resources": ["nodes"], "resourceNames": list(base.NODES), "verbs": ["get", "patch"]}],
                "Node ledger mutations escaped the exact three-node list")
        roles = [x for x in objects if x["kind"] == "Role" and x["metadata"]["name"].startswith("neon-dsga")]
        for role in roles:
            for rule in role["rules"]:
                require("*" not in rule["resources"] + rule["verbs"], "Wildcard RBAC added")
                require("secrets" not in rule["resources"], "Agent/Scheduler must not read private signing Secrets")
                if role["metadata"]["name"].startswith("neon-dsga-host"):
                    require("create" not in rule["verbs"] and "delete" not in rule["verbs"], "Original Host Lease may not be recreated")
        require(not any(x["kind"] == "ClusterRole" and any("pods" in r["resources"] and "patch" in r["verbs"] for r in x["rules"])
                        for x in objects), "Do not silently grant writes to all existing system Pods")
        agent_role = next(x for x in roles if x["metadata"]["name"] == "neon-dsga-agent-runtime")
        require(next(x["verbs"] for x in agent_role["rules"] if x["resources"] == ["configmaps"]) == ["get", "create"],
                "Qualified Agent needs only original Outside get/create; no patch/update/list/GC")
        for domain in values["dsga"]["scheduler"]["nodes"]:
            host_role = next(x for x in roles if x["metadata"]["name"] == "neon-dsga-host-read-" + domain["binding"]["node_name"])
            require(host_role["metadata"]["namespace"] == domain["binding"]["namespace"] and
                    host_role["rules"] == [{"apiGroups": ["coordination.k8s.io"], "resources": ["leases"],
                                           "resourceNames": [domain["binding"]["lease_name"]], "verbs": ["get"]}],
                    "Agent original Host Lease read crossed configured name/namespace or gained mutation")
        standby = copy.deepcopy(values)
        standby["dsga"]["agent"]["prepareQualifications"] = {}
        standby["dsga"]["agent"]["automaticMemory"] = {}
        standby_objects = [x for x in base.documents(helm(standby).stdout) if x]
        standby_role = next(x for x in standby_objects if x["kind"] == "Role" and x["metadata"]["name"] == "neon-dsga-agent-runtime")
        require(next(x["verbs"] for x in standby_role["rules"] if x["resources"] == ["configmaps"]) == ["get"],
                "Unqualified standby Agent acquired ConfigMap create")
        disabled = [x for x in base.documents(helm(merge(values, {"dsga": {"enabled": False}})).stdout) if x]
        require(not any(x.get("metadata", {}).get("name", "").startswith("neon-dsga-") for x in disabled), "Disabled DSGA retained mutation rules")
        legacy_agent = next(x for x in disabled if x["kind"] == "ConfigMap" and x["metadata"]["name"] == "autoscaler-agent-config")
        legacy_scheduler = next(x for x in disabled if x["kind"] == "ConfigMap" and x["metadata"]["name"] == "scheduler-plugin-config")
        require(json.loads(legacy_agent["data"]["config.json"]) == json.loads((CHART / "files/agent-config.json").read_text()),
                "Disabled Agent legacy JSON semantics changed")
        require(json.loads(legacy_scheduler["data"]["autoscale-enforcer-config.json"]) ==
                json.loads((CHART / "files/scheduler-plugin-config.json").read_text()), "Disabled Scheduler legacy JSON changed")
        legacy_ds = next(x for x in disabled if x["kind"] == "DaemonSet")
        require(not any(v["name"].startswith("dsga-") for v in legacy_ds["spec"]["template"]["spec"]["volumes"]),
                "Disabled DSGA retained credential projections")
        return {"newNodeWrites": list(base.NODES), "newPodWrites": values["dsga"]["vmNamespace"],
                "allNamespaceHostPodProtection": "pending-runtime-design-gate",
                "originalHostLeaseCreationDenied": True, "secretReadNotGranted": True}
    record("PG17-U-H09", "新增运行角色只写明确节点/VM namespace/原 Host Lease，停用撤销", rbac)

    def source():
        lock = json.loads((ROOT / "locks/pg17-dsga-runtime-source.json").read_text())
        require(lock["commit"] == SOURCE and lock["credentialAudience"] == AUDIENCE, "Runtime interface source drift")
        for path, digest in lock["interfaceFiles"].items():
            raw = subprocess.check_output(["git", "-C", str(args.autoscaling_source), "show", SOURCE + ":" + path])
            require(hashlib.sha256(raw).hexdigest() == digest, "Accurate runtime interface file changed: " + path)
        require(hashlib.sha256((ROOT / lock["observedNodeIdentityFile"]).read_bytes()).hexdigest() ==
                lock["observedNodeIdentitySha256"], "Observed real Node identity lock drift")
        return {"source": SOURCE, "interfaceFiles": len(lock["interfaceFiles"]), "nodeUIDSource": "actual-read-only-cluster-snapshot",
                "budgetsAndPerVMQualifications": "not-invented-not-certified"}
    record("PG17-U-H10", "准确 AS 运行接口与真实 Node UID 来源锁", source)

    def original_input_negatives():
        nodes = base.fixture_nodes()
        by_node = {n["metadata"]["name"]: n for n in nodes["items"]}
        leases = {"apiVersion": "coordination.k8s.io/v1", "kind": "LeaseList", "items": []}
        for domain in values["dsga"]["scheduler"]["nodes"]:
            b = domain["binding"]
            node = by_node[b["node_name"]]
            node["metadata"]["uid"] = b["node_uid"]
            node["metadata"]["resourceVersion"] = domain["initialize_at_resource_version"]
            leases["items"].append({"apiVersion": "coordination.k8s.io/v1", "kind": "Lease",
              "metadata": {"namespace": b["namespace"], "name": b["lease_name"], "uid": b["lease_uid"], "resourceVersion": "1",
               "annotations": {"internal.autoscaling.neon.tech/dsga-host-lease-v1": "1:" + b["node_uid"] + ":" + b["node_name"]},
               "ownerReferences": [{"apiVersion": "v1", "kind": "Node", "name": b["node_name"], "uid": b["node_uid"], "controller": True}]}})
        result = validate_original_inputs(values, nodes, leases)
        require(result["platformBudgetsAndQualifications"] == "not-certified-by-this-check", "Identity check overclaimed certification")
        rejected = 0
        for variant in ("node-uid", "lease-uid", "lease-owner", "lease-marker", "frozen-rv", "missing-lease", "partial-node-list"):
            n, l = copy.deepcopy(nodes), copy.deepcopy(leases)
            if variant == "node-uid": n["items"][1]["metadata"]["uid"] = "recreated-node"
            if variant == "lease-uid": l["items"][0]["metadata"]["uid"] = "recreated-lease"
            if variant == "lease-owner": l["items"][0]["metadata"]["ownerReferences"][0]["uid"] = "another-node"
            if variant == "lease-marker": l["items"][0]["metadata"]["annotations"].clear()
            if variant == "frozen-rv": n["items"][1]["metadata"]["resourceVersion"] = "999"
            if variant == "missing-lease": l["items"].pop()
            if variant == "partial-node-list": n["items"] = n["items"][1:]
            try:
                validate_original_inputs(values, n, l)
            except AssertionError:
                rejected += 1
            else:
                raise AssertionError("Invalid original source accepted: " + variant)
        return {"fixtureOnly": True, "originalIdentityAndScopeNegativeCasesRejected": rejected,
                "budgetsAndQualifications": "not-certified", "actualOriginalLeases": "absent-not-invented"}
    record("PG17-U-H11", "原Node/Lease快照检查拒绝同名重建、owner/marker/RV漂移和不完整快照", original_input_negatives)

    if args.typed_contract:
        def typed():
            require("agent" in output, "Rendered Agent config is unavailable")
            context = out / "typed-context"
            context.mkdir()
            (context / "contract.go").write_text(GO_HELPER)
            (context / "Dockerfile").write_text(DOCKERFILE)
            for name in ("agent.json", "plugin.json"):
                (context / name).write_bytes((out / name).read_bytes())
            export = out / "typed-export"
            command = ["docker", "buildx", "build", "--builder", "neon-data", "--network", "none", "--progress", "plain",
                       "--build-context", "helmfixture=" + str(context), "--build-arg", "PG17_CONTRACT_NONCE=" + str(time.time_ns()),
                       "--output", "type=local,dest=" + str(export), "-f", str(context / "Dockerfile"), str(args.autoscaling_source)]
            # Buildx 位于既有受信 DOCKER_CONFIG；只 source 原环境，不打印环境/凭据。
            shared_env = ROOT.parents[1] / "config/env.sh"
            if shared_env.is_file():
                command = ["bash", "-c", 'source "$1"; shift; exec "$@"', "pg17-dsga-contract", str(shared_env), *command]
            def go_inputs():
                names = subprocess.check_output(["git", "-C", str(args.autoscaling_source), "ls-files", "-c", "-o",
                                                 "--exclude-standard", "--", "*.go", "go.mod", "go.sum"], text=True).splitlines()
                return {name: hashlib.sha256((args.autoscaling_source / name).read_bytes()).hexdigest()
                        for name in sorted(set(names)) if (args.autoscaling_source / name).is_file()}
            actual_go_inputs = go_inputs()
            (out / "typed-as-source-inputs.json").write_text(json.dumps(actual_go_inputs, indent=2) + "\n")
            (out / "typed-command.json").write_text(json.dumps(command, indent=2) + "\n")
            with (out / "typed-build.log").open("w") as log:
                process = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=900)
            require(process.returncode == 0, "Actual Linux typed contract failed; inspect typed-build.log")
            receipt = json.loads((export / "typed-contract.json").read_text())
            context_manifest = export / "as-go-context-inputs.json"
            require(context_manifest.is_file() and hashlib.sha256(context_manifest.read_bytes()).hexdigest() ==
                    receipt["immutableASGoContextManifestSha256"], "Actual immutable build-context source proof differs")
            # 运行证据绑定容器内实际 COPY 快照。宿主并行改动独立记录，不冒充执行源码。
            receipt["hostASGoInputsChangedDuringBuild"] = actual_go_inputs != go_inputs()
            receipt["preBuildHostASGoInputsSha256"] = hashlib.sha256(base.canonical(actual_go_inputs).encode()).hexdigest()
            receipt["loadedDockerfileSha256"] = hashlib.sha256((context / "Dockerfile").read_bytes()).hexdigest()
            receipt["goCacheSharing"] = "shared"
            receipt["goModuleCacheID"] = "autoscaling-gomod-amd64-shared-v2"
            return receipt
        record("PG17-S-H06", "真实 Linux/Go1.24 Agent.ReadConfig 与 Host Config.Validate、无PodUID拒绝", typed)
    else:
        results.append({"id": "PG17-S-H06", "status": "not-executed", "reason": "Run with --typed-contract using existing BuildKit caches"})

    files = set(p for p in CHART.rglob("*") if p.is_file())
    files.update(ROOT / x for x in ("tools/check-pg17-dsga.py", "tools/check-pg17-helm.py", "tools/check-source.mjs",
                                    "locks/pg17-dsga-runtime-source.json", "profiles/pg17-memory/neon-autoscaler-required.json"))
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    (out / "source-inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    summary = {"mode": "linux-offline-templates-and-config-contracts-no-cluster-mutation", "fixtureOnly": True,
               "sourceInputsSha256": hashlib.sha256(base.canonical(manifest).encode()).hexdigest(),
               "status": "fail" if any(x["status"] == "fail" for x in results) else "pass",
               "results": results, "actualRuntimeGates": {"PG17-S-H04": "not-prepared: actual pool labels absent",
               "PG17-S-H07": "not-executed: original Host Lease/profile/system budget and per-VM qualifications absent",
               "PG17-S-H08": "not-executed: full Host ordinary-Pod hard-limit and protection scope unresolved",
               "PG17-S-H09": "not-executed: gateway/Runner/RBAC/CA/token/PG17 memory E2E requires single-machine gate first"}}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("Evidence: " + str(out), flush=True)
    return 1 if summary["status"] == "fail" else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        sys.exit(1)
