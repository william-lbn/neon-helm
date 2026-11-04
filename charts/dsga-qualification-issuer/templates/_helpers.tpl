{{- define "dsga-qualification-issuer.fullname" -}}
{{- $identity := printf "%s/%s" .Release.Namespace .Release.Name -}}
{{- printf "%s-%s" (printf "%s-%s" .Release.Namespace .Release.Name | trunc 42 | trimSuffix "-") (sha256sum $identity | trunc 8) -}}
{{- end -}}

{{/* 只在显式原对象名齐备时创建专用身份；绕过schema仍必须拒绝宽名/配错。 */}}
{{- define "dsga-qualification-issuer.validate" -}}
{{- $subject := .Values.subject | default dict -}}
{{- $namespace := required "subject.namespace must name the dedicated Issuer namespace" $subject.namespace -}}
{{- $account := required "subject.name must name the dedicated Issuer ServiceAccount" $subject.name -}}
{{- if or (ne $namespace .Release.Namespace) (ne $account .Release.Name) (eq $account "autoscaler-agent") (eq $account "neon-pg17-runner") -}}{{ fail "Issuer subject must be the dedicated release namespace/name, never Agent or Runner" }}{{- end -}}
{{- $vm := required "vmName is required" .Values.vmName -}}
{{- $secret := required "configSecretName is required" .Values.configSecretName -}}
{{- $pod := required "runnerPodName is required" .Values.runnerPodName -}}
{{- $owner := required "ownerLeaseName is required" .Values.ownerLeaseName -}}
{{- $qualification := required "qualificationConfigMapName is required" .Values.qualificationConfigMapName -}}
{{- $host := required "hostLeaseName is required" .Values.hostLeaseName -}}
{{- $node := required "nodeName is required" .Values.nodeName -}}
{{- if or (not (regexMatch "^cp-[a-f0-9]{16}$" $vm)) (ne $secret (printf "%s-config" $vm)) (not (hasPrefix (printf "%s-" $vm) $pod)) -}}{{ fail "Issuer VM, config Secret and original Runner Pod must name the same Compute" }}{{- end -}}
{{- if or (not (has $node (list "worker-117" "worker-118" "worker-119"))) (ne $host (printf "neon-dsga-host-%s" $node)) -}}{{ fail "Issuer HostLease must exactly match one permitted worker" }}{{- end -}}
{{- if not (regexMatch "^dsga-[a-f0-9]{56}$" $owner) -}}{{ fail "Issuer requires one exact OwnerLease" }}{{- end -}}
{{- if not (regexMatch "^dsga-q-[a-f0-9]{56}$" $qualification) -}}{{ fail "Issuer requires its exact report-derived qualification ConfigMap" }}{{- end -}}
{{- $claims := .Values.runnerClaims | default dict -}}
{{- $birth := required "runnerClaims.birth is required" $claims.birth -}}
{{- $state := required "runnerClaims.state is required" $claims.state -}}
{{- $exit := required "runnerClaims.exit is required" $claims.exit -}}
{{- $stopped := required "runnerClaims.stoppedPod is required" $claims.stoppedPod -}}
{{- if or (not (regexMatch "^dsga-b-[a-f0-9]{56}$" $birth)) (ne $state (printf "dsga-s-%s" (trimPrefix "dsga-b-" $birth))) (not (regexMatch "^dsga-x-[a-f0-9]{56}$" $exit)) (not (regexMatch "^dsga-t-[a-f0-9]{56}$" $stopped)) -}}{{ fail "Issuer requires exact original Birth, State, Exit and StoppedPod claims" }}{{- end -}}
{{- end -}}
