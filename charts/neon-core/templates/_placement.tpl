{{- define "neon-core.placement.guard" -}}
{{- if not (kindIs "map" .Values.placement) -}}
{{- fail "placement.allowedNodeNames must be an explicit list of Kubernetes hostnames" -}}
{{- end -}}
{{- if not (kindIs "slice" .Values.placement.allowedNodeNames) -}}
{{- fail "placement.allowedNodeNames must be an explicit list" -}}
{{- end -}}
{{- if lt (len .Values.placement.allowedNodeNames) 1 -}}
{{- fail "placement.allowedNodeNames must contain at least one hostname" -}}
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

{{- define "neon-core.placement.pool" -}}
{{- join "-" (sortAlpha .Values.placement.allowedNodeNames) -}}
{{- end -}}

{{- define "neon-core.placement.selector" -}}
nodeSelector:
  kubernetes.io/os: linux
  kubernetes.io/arch: amd64
  neon.tech/pg17-memory-pool: {{ include "neon-core.placement.pool" . | quote }}
{{- end -}}

{{- define "neon-core.placement.hostMatch" -}}
- key: kubernetes.io/hostname
  operator: In
  values: {{ toJson (sortAlpha .Values.placement.allowedNodeNames) }}
{{- end -}}

{{- define "neon-core.placement.nodeAffinity" -}}
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
    - matchExpressions:
      {{- include "neon-core.placement.hostMatch" . | nindent 6 }}
{{- end -}}

{{- define "neon-core.placement.pod" -}}
{{ include "neon-core.placement.selector" . }}
affinity:
  {{- include "neon-core.placement.nodeAffinity" . | nindent 2 }}
{{- end -}}
