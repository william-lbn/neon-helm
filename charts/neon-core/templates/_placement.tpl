{{- define "neon-core.placement.guard" -}}
{{- $expected := list "worker-117" "worker-118" "worker-119" -}}
{{- if not (kindIs "map" .Values.placement) -}}
{{- fail "placement.allowedNodeNames must explicitly name worker-117/118/119; ubuntu/116 is forbidden" -}}
{{- end -}}
{{- if not (kindIs "slice" .Values.placement.allowedNodeNames) -}}
{{- fail "placement.allowedNodeNames must be an explicit list" -}}
{{- end -}}
{{- if ne (toJson (sortAlpha .Values.placement.allowedNodeNames)) (toJson $expected) -}}
{{- fail "placement.allowedNodeNames must contain exactly worker-117, worker-118, worker-119; ubuntu/116 and other nodes are forbidden" -}}
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
