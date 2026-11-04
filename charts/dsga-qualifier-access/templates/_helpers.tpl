{{/* 名称含 release namespace 与原完整身份摘要，跨 namespace/截断时也不冲突。 */}}
{{- define "dsga-qualifier-access.fullname" -}}
{{- $identity := printf "%s/%s" .Release.Namespace .Release.Name -}}
{{- printf "%s-%s" (printf "%s-%s" .Release.Namespace .Release.Name | trunc 42 | trimSuffix "-") (sha256sum $identity | trunc 8) -}}
{{- end -}}

{{/* 即使调用方跳过 schema，也不得渲染空值、宽资源名或其它 Node。 */}}
{{- define "dsga-qualifier-access.validate" -}}
{{- $subject := .Values.subject | default dict -}}
{{- $namespace := required "subject.namespace must select the original Collector ServiceAccount" $subject.namespace -}}
{{- $name := required "subject.name must select the original Collector ServiceAccount" $subject.name -}}
{{- $secret := required "configSecretName must select one original Compute config Secret" .Values.configSecretName -}}
{{- $node := required "nodeName must select one deployment worker" .Values.nodeName -}}
{{- range $value := list $namespace $name -}}
{{- if not (kindIs "string" $value) -}}{{- fail "Collector subject must be a DNS label" -}}{{- end -}}
{{- if or (gt (len $value) 63) (not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$" $value)) -}}{{- fail "Collector subject must be a DNS label" -}}{{- end -}}
{{- end -}}
{{- if not (kindIs "string" $secret) -}}{{- fail "configSecretName must be an original Compute config reference" -}}{{- end -}}
{{- if not (regexMatch "^cp-[a-f0-9]{16}-config$" $secret) -}}{{- fail "configSecretName must be an original Compute config reference" -}}{{- end -}}
{{- if not (has $node (list "worker-117" "worker-118" "worker-119")) -}}{{- fail "nodeName must be worker-117, worker-118 or worker-119" -}}{{- end -}}
{{- end -}}
