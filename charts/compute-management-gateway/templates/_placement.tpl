{{- define "compute-management-gateway.placement.guard" -}}
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

{{- define "compute-management-gateway.placement.pool" -}}
{{- join "-" (sortAlpha .Values.placement.allowedNodeNames) -}}
{{- end -}}

{{- define "compute-management-gateway.placement.selector" -}}
nodeSelector:
  kubernetes.io/os: linux
  kubernetes.io/arch: amd64
  neon.tech/pg17-memory-pool: {{ include "compute-management-gateway.placement.pool" . | quote }}
{{- end -}}

{{- define "compute-management-gateway.placement.hostMatch" -}}
- key: kubernetes.io/hostname
  operator: In
  values: {{ toJson (sortAlpha .Values.placement.allowedNodeNames) }}
{{- end -}}

{{- define "compute-management-gateway.placement.nodeAffinity" -}}
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
    - matchExpressions:
      {{- include "compute-management-gateway.placement.hostMatch" . | nindent 6 }}
{{- end -}}

{{- define "compute-management-gateway.placement.pod" -}}
{{ include "compute-management-gateway.placement.selector" . }}
affinity:
  {{- include "compute-management-gateway.placement.nodeAffinity" . | nindent 2 }}
{{- end -}}
