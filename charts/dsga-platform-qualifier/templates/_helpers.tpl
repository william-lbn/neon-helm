{{- define "dsga-platform-qualifier.name" -}}
{{- $identity := printf "%s/%s" .Release.Namespace .Release.Name -}}
{{- printf "%s-%s" (printf "%s-%s-qualifier" .Release.Namespace .Release.Name | trunc 54 | trimSuffix "-") ($identity | sha256sum | trunc 8) -}}
{{- end -}}
{{- define "dsga-platform-qualifier.ownerLease" -}}
{{- $b := .Values.binding -}}
{{- printf "dsga-%s" (printf "neon-dsga-lease-binding-v1\x00%s" (list .Release.Namespace $b.vmName $b.vmUID $b.incarnation | toJson) | sha256sum | trunc 56) -}}
{{- end -}}
{{- define "dsga-platform-qualifier.canonicalDirectory" -}}
{{- if or (not (hasPrefix "/" .)) (eq . "/") (ne (clean .) .) (regexMatch "[[:space:]]" .) -}}
{{- fail "qualifier requires explicit canonical private absolute directories" -}}
{{- end -}}
{{- end -}}
{{- define "dsga-platform-qualifier.guard" -}}
{{- if .Values.enabled -}}
{{- $v := .Values -}}
{{- if ne (toString .Capabilities.KubeVersion.Minor) "31" -}}{{- fail "qualifier targets the observed Kubernetes 1.31 contract" -}}{{- end -}}
{{- if or (not (regexMatch "^[a-z0-9.-]+(:[0-9]+)?(/[a-z0-9]+([._-][a-z0-9]+)*)+$" $v.image.repository)) (not (regexMatch "^sha256:[a-f0-9]{64}$" $v.image.digest)) -}}{{- fail "qualifier requires explicit repository and immutable sha256 image digest" -}}{{- end -}}
{{- $b := $v.binding -}}
{{- $pins := (.Files.Get "files/pg17-node-identities.json" | fromJson).allowedNodeUIDs -}}
{{- if or (not (hasKey $pins $b.nodeName)) (ne (index $pins $b.nodeName) $b.nodeUID) -}}{{- fail "qualifier Node must be original worker-117/118/119 UID; ubuntu is excluded" -}}{{- end -}}
{{- if or (not $b.vmName) (not $b.vmUID) (not $b.runnerPodName) (not (regexMatch "^[a-f0-9]{32}$" $b.incarnation)) (lt (len $b.runnerConfigMapNames) 4) -}}{{- fail "qualifier requires original VM/incarnation/Runner and exact source ConfigMap names" -}}{{- end -}}
{{- if or (not $v.hostLease.namespace) (not $v.hostLease.name) -}}{{- fail "qualifier requires the original Host Lease read binding" -}}{{- end -}}
{{- range $d := list $v.inputs.hostDirectory $v.inputs.mountDirectory $v.agentResourceReadSocket.hostDirectory $v.agentResourceReadSocket.mountDirectory -}}
{{- include "dsga-platform-qualifier.canonicalDirectory" $d -}}
{{- end -}}
{{- range $pair := list (list $v.inputs.hostDirectory $v.agentResourceReadSocket.hostDirectory) (list $v.inputs.mountDirectory $v.agentResourceReadSocket.mountDirectory) (list $v.inputs.mountDirectory "/var/run/secrets/kubernetes.io/serviceaccount") (list $v.agentResourceReadSocket.mountDirectory "/var/run/secrets/kubernetes.io/serviceaccount") -}}
{{- $a := index $pair 0 -}}{{- $b := index $pair 1 -}}
{{- if or (eq $a $b) (hasPrefix (printf "%s/" $a) $b) (hasPrefix (printf "%s/" $b) $a) -}}{{- fail "original input, resource socket and API mounts must be disjoint" -}}{{- end -}}
{{- end -}}
{{- range $f := list $v.inputs.configFileName $v.agentResourceReadSocket.name -}}
{{- if not (regexMatch "^[A-Za-z0-9][A-Za-z0-9._-]*$" $f) -}}{{- fail "qualifier source filenames must be explicit safe basenames" -}}{{- end -}}
{{- end -}}
{{- if gt (len (printf "%s/%s" $v.agentResourceReadSocket.mountDirectory $v.agentResourceReadSocket.name)) 100 -}}{{- fail "original Agent socket path exceeds existing UDS contract" -}}{{- end -}}
{{- range $hash := list $v.inputs.configSHA256 $v.inputs.reportSHA256 $v.agentResourceReadSocket.sourceManifestSHA256 -}}
{{- if not (regexMatch "^[a-f0-9]{64}$" $hash) -}}{{- fail "qualifier requires explicit original config/report/Agent-manifest SHA256" -}}{{- end -}}
{{- end -}}
{{- if ne $v.placement.schedulerName "autoscale-scheduler" -}}{{- fail "qualifier must enter the existing Host scheduler allocator" -}}{{- end -}}
{{- if or (not (regexMatch "^[1-9][0-9]*(Ki|Mi|Gi)$" (toString $v.resources.limits.memory))) (not (regexMatch "^[1-9][0-9]*(m)?$" (toString $v.resources.limits.cpu))) -}}{{- fail "all qualifier containers require positive hard resource limits" -}}{{- end -}}
{{- if or (lt (int $v.job.activeDeadlineSeconds) 1) (gt (int $v.job.activeDeadlineSeconds) 600) -}}{{- fail "qualifier Job lifetime must be bounded to 1..600 seconds" -}}{{- end -}}
{{- end -}}
{{- end -}}
