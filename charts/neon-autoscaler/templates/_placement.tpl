{{- define "neon-autoscaler.placement.guard" -}}
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

{{/* Scheduler可单独收紧到允许节点之一；原pool/os/arch与节点亲和性始终保留，Agent不受影响。 */}}
{{- define "neon-autoscaler.placement.schedulerPod" -}}
{{- if not (kindIs "map" .Values.scheduler.nodeSelector) -}}
{{- fail "scheduler.nodeSelector must be a hostname-only map" -}}
{{- end -}}
{{- range $key, $value := .Values.scheduler.nodeSelector -}}
{{- if ne $key "kubernetes.io/hostname" -}}
{{- fail "scheduler.nodeSelector may only add kubernetes.io/hostname; pool/os/arch cannot be overridden" -}}
{{- end -}}
{{- if not (has $value $.Values.placement.allowedNodeNames) -}}
{{- fail "scheduler.nodeSelector hostname must belong to placement.allowedNodeNames" -}}
{{- end -}}
{{- end -}}
{{ include "neon-autoscaler.placement.selector" . }}
{{- with index .Values.scheduler.nodeSelector "kubernetes.io/hostname" }}
  kubernetes.io/hostname: {{ . | quote }}
{{- end }}
affinity:
  {{- include "neon-autoscaler.placement.nodeAffinity" . | nindent 2 }}
{{- end -}}
