{{- define "neon-autoscaler.placement.guard" -}}
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

{{- define "neon-autoscaler.placement.pool" -}}
{{- join "-" (sortAlpha .Values.placement.allowedNodeNames) -}}
{{- end -}}

{{- define "neon-autoscaler.placement.selector" -}}
nodeSelector:
  kubernetes.io/os: linux
  kubernetes.io/arch: amd64
  neon.tech/pg17-memory-pool: {{ include "neon-autoscaler.placement.pool" . | quote }}
{{- end -}}

{{- define "neon-autoscaler.placement.hostMatch" -}}
- key: kubernetes.io/hostname
  operator: In
  values: {{ toJson (sortAlpha .Values.placement.allowedNodeNames) }}
{{- end -}}

{{- define "neon-autoscaler.placement.nodeAffinity" -}}
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
    - matchExpressions:
      {{- include "neon-autoscaler.placement.hostMatch" . | nindent 6 }}
{{- end -}}

{{- define "neon-autoscaler.placement.pod" -}}
{{ include "neon-autoscaler.placement.selector" . }}
affinity:
  {{- include "neon-autoscaler.placement.nodeAffinity" . | nindent 2 }}
{{- end -}}
