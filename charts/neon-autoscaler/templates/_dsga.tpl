{{- define "neon-autoscaler.dsga.agentConfig" -}}
{{- $config := .Files.Get "files/agent-config.json" | fromJson -}}
{{- if .Values.dsga.enabled -}}
{{- $a := .Values.dsga.agent -}}
{{- $dsga := dict "gatewayURL" $a.gatewayURL "managementCAFile" "/etc/neon-dsga/management/ca.crt" "projectedTokenFile" "/var/run/secrets/neon-dsga/token" "requestTimeoutSeconds" $a.requestTimeoutSeconds "computeTimeoutSeconds" $a.computeTimeoutSeconds "pollIntervalSeconds" $a.pollIntervalSeconds "prepareQualifications" $a.prepareQualifications "automaticMemory" $a.automaticMemory -}}
{{- if $a.resourceReadSocket.enabled -}}
{{- $_ := set $dsga "resourceReadSocketPath" (printf "%s/%s" $a.resourceReadSocket.mountDirectory $a.resourceReadSocket.name) -}}
{{- end -}}
{{- $_ := set $config "dsga" $dsga -}}
{{- end -}}
{{- $config | toPrettyJson -}}
{{- end -}}

{{- define "neon-autoscaler.dsga.schedulerConfig" -}}
{{- $config := .Files.Get "files/scheduler-plugin-config.json" | fromJson -}}
{{- if .Values.dsga.enabled -}}
{{- $_ := set $config "dsgaHost" (dict "nodes" .Values.dsga.scheduler.nodes) -}}
{{- end -}}
{{- $config | toPrettyJson -}}
{{- end -}}

{{- define "neon-autoscaler.dsga.decimal" -}}
{{- $value := .value -}}
{{- if or (not (kindIs "string" $value)) (not (regexMatch "^[1-9][0-9]{0,19}$" (toString $value))) -}}
{{- fail "DSGA byte values must be positive canonical decimal strings, never JSON/YAML numbers" -}}
{{- end -}}
{{- if or (gt (len $value) (len .maximum)) (and (eq (len $value) (len .maximum)) (gt $value .maximum)) -}}
{{- fail "DSGA decimal exceeds its exact integer range" -}}
{{- end -}}
{{- end -}}

{{- define "neon-autoscaler.dsga.guard" -}}
{{- $d := .Values.dsga -}}
{{- if ne (int $d.pgVersion) 17 -}}{{- fail "DSGA qualification is PG17 only" -}}{{- end -}}
{{- $resource := $d.agent.resourceReadSocket -}}
{{- if and $resource.enabled (not $d.enabled) -}}{{- fail "Agent resource-read socket requires DSGA enabled" -}}{{- end -}}
{{- if $resource.enabled -}}
{{- range $directory := list $resource.hostDirectory $resource.mountDirectory -}}
{{- if or (not (kindIs "string" $directory)) (not (regexMatch "^(/[A-Za-z0-9_.-]+)+$" (toString $directory))) (regexMatch "(^|/)\\.\\.?(/|$)" (toString $directory)) -}}
{{- fail "Agent resource-read socket requires canonical absolute private directories" -}}{{- end -}}
{{- end -}}
{{- if or (not (kindIs "string" $resource.name)) (not (regexMatch "^[A-Za-z0-9][A-Za-z0-9_.-]*[.]sock$" (toString $resource.name))) (gt (len (printf "%s/%s" $resource.mountDirectory $resource.name)) 100) -}}
{{- fail "Agent resource-read socket requires a short original socket filename" -}}{{- end -}}
{{- end -}}
{{- if $d.enabled -}}
{{- if or (ne (toString .Capabilities.KubeVersion.Minor) "31") (ne (toString .Values.compatibility.expectedKubernetesMinor) "31") .Values.compatibility.allowUntestedKubernetes -}}
{{- fail "PG17 DSGA requires the actually observed Kubernetes 1.31 target; untested-minor bypass is forbidden" -}}{{- end -}}
{{- $a := $d.agent -}}
{{- if or (not (regexMatch "^https://[A-Za-z0-9.-]+(:[1-9][0-9]{0,4})?/?$" $a.gatewayURL)) (not $a.managementCASecret) -}}
{{- fail "DSGA requires a trusted HTTPS gateway root URL and existing public management CA Secret" -}}
{{- end -}}
{{- if ne $a.tokenAudience "neon-dsga-credential-broker" -}}{{- fail "DSGA projected token must use the dedicated credential-broker audience" -}}{{- end -}}
{{- if or (lt (int $a.requestTimeoutSeconds) 1) (gt (int $a.requestTimeoutSeconds) 30) (lt (int $a.computeTimeoutSeconds) 90) (gt (int $a.computeTimeoutSeconds) 120) (lt (int $a.pollIntervalSeconds) 1) (gt (int $a.pollIntervalSeconds) 60) (lt (int $a.tokenExpirationSeconds) 600) (gt (int $a.tokenExpirationSeconds) 3600) -}}
{{- fail "DSGA timeouts/token lifetime exceed bounded runtime contracts" -}}{{- end -}}
{{- $expected := (.Files.Get "files/pg17-node-identities.json" | fromJson).allowedNodeUIDs -}}
{{- $seen := dict -}}{{- $domains := dict -}}{{- $leaseUIDs := dict -}}
{{- if ne (len $d.scheduler.nodes) 3 -}}{{- fail "DSGA Host domains require the three explicit original Node/Lease/profile/system-budget inputs" -}}{{- end -}}
{{- range $n := $d.scheduler.nodes -}}
{{- $name := $n.binding.node_name -}}
{{- if or (not (hasKey $expected $name)) (hasKey $seen $name) (ne $n.binding.node_uid (index $expected $name)) -}}
{{- fail "DSGA Host Node identity differs from the actual observed original worker-117/118/119 UID" -}}{{- end -}}
{{- $_ := set $seen $name true -}}
{{- if or (not $n.binding.namespace) (not $n.binding.lease_name) (not $n.binding.lease_uid) -}}{{- fail "DSGA Host domains require actual original Lease identity; Helm never invents or creates it" -}}{{- end -}}
{{- $domain := printf "%s/%s" $n.binding.namespace $n.binding.lease_name -}}
{{- if or (hasKey $domains $domain) (hasKey $leaseUIDs $n.binding.lease_uid) -}}{{- fail "DSGA Host Lease domains and original UIDs must be distinct" -}}{{- end -}}
{{- $_ := set $domains $domain true -}}{{- $_ := set $leaseUIDs $n.binding.lease_uid true -}}
{{- if or (not $n.profile.id) (ne $n.profile.scheduler_name "autoscale-scheduler") -}}{{- fail "DSGA Host profile must be explicit for autoscale-scheduler" -}}{{- end -}}
{{- include "neon-autoscaler.dsga.decimal" (dict "value" $n.system_bytes "maximum" "18446744073709551615") -}}
{{- include "neon-autoscaler.dsga.decimal" (dict "value" $n.profile.vm_overhead_bytes "maximum" "18446744073709551615") -}}
{{- include "neon-autoscaler.dsga.decimal" (dict "value" $n.profile.pod_overhead_bytes "maximum" "18446744073709551615") -}}
{{- /* 显式 Host K8s 容量策略不是全 Host 内核物理认证；Guest 资格另行完整核验。 */ -}}
{{- if hasKey $n "kubernetes_budget" -}}
{{- $p := $n.kubernetes_budget -}}
{{- if or (not $p) (ne (int $p.protocol_version) 1) (ne $p.scope "kubernetes-node-memory-budget-v1") (ne $p.node_name $name) (ne $p.node_uid $n.binding.node_uid) (ne $p.system_reservation_bytes $n.system_bytes) -}}
{{- fail "DSGA Kubernetes budget must match the explicit original Node and system reservation" -}}
{{- end -}}
{{- range $bytes := list $p.capacity_bytes $p.allocatable_bytes $p.system_reservation_bytes -}}
{{- include "neon-autoscaler.dsga.decimal" (dict "value" $bytes "maximum" "18446744073709551615") -}}
{{- end -}}
{{- /* Profile 为 Go 固定 struct 字段顺序；不可对 map toJson 后改变摘要合同。 */ -}}
{{- $profileRaw := printf "{\"id\":%s,\"scheduler_name\":%s,\"vm_overhead_bytes\":%s,\"pod_overhead_bytes\":%s}" (toJson $n.profile.id) (toJson $n.profile.scheduler_name) (toJson $n.profile.vm_overhead_bytes) (toJson $n.profile.pod_overhead_bytes) -}}
{{- if ne $p.profile_sha256 (sha256sum $profileRaw) -}}{{- fail "DSGA Kubernetes budget must match the original Host profile SHA256" -}}{{- end -}}
{{- /* Capacity/Allocatable 的实际 Node 漂移与防超卖算术由 AS 生产入口核验。 */ -}}
{{- end -}}
{{- end -}}
{{- range $vmUID, $p := $a.automaticMemory -}}
{{- if not (hasKey $a.prepareQualifications $vmUID) -}}{{- fail "Automatic DSGA memory requires the same original VM UID qualification" -}}{{- end -}}
{{- if or (lt (int $p.maximumSampleGapSeconds) (int $p.sampleIntervalSeconds)) (lt (int $p.growWindowSeconds) (int $p.sampleIntervalSeconds)) (le (int $p.shrinkWindowSeconds) (int $p.growWindowSeconds)) (lt (int $p.cooldownSeconds) (int $p.sampleIntervalSeconds)) (ge (int $p.shrinkThresholdPermille) (int $p.growThresholdPermille)) (ge (int $p.growThresholdPermille) (int $p.emergencyThresholdPermille)) -}}
{{- fail "Automatic DSGA memory windows/thresholds violate the source policy ordering" -}}{{- end -}}
{{- $lastMemory := "" -}}{{- $lastBuffers := 0 -}}
{{- range $t := $p.targets -}}
{{- include "neon-autoscaler.dsga.decimal" (dict "value" $t.vmMemoryBytes "maximum" "9223372036854775807") -}}
{{- if $lastMemory -}}
{{- if or (lt (len $t.vmMemoryBytes) (len $lastMemory)) (and (eq (len $t.vmMemoryBytes) (len $lastMemory)) (lt $t.vmMemoryBytes $lastMemory)) (lt (int $t.buffers) $lastBuffers) (and (eq $t.vmMemoryBytes $lastMemory) (eq (int $t.buffers) $lastBuffers)) -}}
{{- fail "Automatic DSGA memory targets must be exact ordered non-reversing specifications" -}}{{- end -}}
{{- end -}}
{{- $lastMemory = $t.vmMemoryBytes -}}{{- $lastBuffers = int $t.buffers -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
