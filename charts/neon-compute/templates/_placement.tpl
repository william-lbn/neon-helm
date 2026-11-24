{{/* Site selectors are configuration. Empty hostname list permits node discovery. */}}
{{- define "neon-compute.placement.guard" -}}
{{- if not (kindIs "map" .Values.placement) -}}
{{- fail "placement.allowedNodeNames must be an explicit list of Kubernetes hostnames" -}}
{{- end -}}
{{- if not (kindIs "slice" .Values.placement.allowedNodeNames) -}}
{{- fail "placement.allowedNodeNames must be an explicit list" -}}
{{- end -}}

{{- $selector := .Values.placement.nodeSelector | default dict -}}
{{- if not (kindIs "map" $selector) -}}{{ fail "placement.nodeSelector must be a label map" }}{{- end -}}
{{- range $key, $value := $selector -}}
{{- if not (kindIs "string" $value) -}}{{ fail "placement.nodeSelector values must be strings" }}{{- end -}}
{{- if or (and (eq $key "kubernetes.io/os") (ne $value "linux")) (and (eq $key "kubernetes.io/arch") (ne $value "amd64")) -}}
{{- fail "selected runtime requires linux/amd64" -}}{{- end -}}
{{- end -}}
{{- $seen := dict -}}
{{- range .Values.placement.allowedNodeNames -}}
{{- if not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$" .) -}}
{{- fail (printf "invalid Kubernetes hostname in placement.allowedNodeNames: %s" .) -}}
{{- end -}}
{{- if hasKey $seen . -}}
{{- fail (printf "duplicate hostname in placement.allowedNodeNames: %s" .) -}}
{{- end -}}
{{- $_ := set $seen . true -}}
{{- end -}}
{{- end -}}

{{- define "neon-compute.placement.pool" -}}
{{- join "-" (sortAlpha .Values.placement.allowedNodeNames) -}}
{{- end -}}

{{- define "neon-compute.placement.selector" -}}
{{- $selector := merge (dict "kubernetes.io/os" "linux" "kubernetes.io/arch" "amd64") (.Values.placement.nodeSelector | default dict) -}}
nodeSelector:
  {{- toYaml $selector | nindent 2 }}
{{- end -}}

{{- define "neon-compute.placement.hostMatch" -}}
- key: kubernetes.io/hostname
  operator: In
  values: {{ toJson (sortAlpha .Values.placement.allowedNodeNames) }}
{{- end -}}

{{- define "neon-compute.placement.nodeAffinity" -}}
{{- if or .Values.placement.allowedNodeNames .Values.placement.matchExpressions -}}
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
    - matchExpressions:
      {{- if .Values.placement.allowedNodeNames }}
      {{- include "neon-compute.placement.hostMatch" . | nindent 6 }}
      {{- end }}
      {{- with .Values.placement.matchExpressions }}
      {{- toYaml . | nindent 6 }}
      {{- end }}
{{- end -}}
{{- end -}}

{{- define "neon-compute.placement.pod" -}}
{{ include "neon-compute.placement.selector" . }}
affinity:
  {{- include "neon-compute.placement.nodeAffinity" . | nindent 2 }}
{{- end -}}
