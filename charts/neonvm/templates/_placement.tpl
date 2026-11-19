{{/*
Site-generic node pool. Overlay replaces placement.allowedNodeNames.
Defaults remain worker-117/118/119 for existing laboratory overlays.
*/}}
{{- define "neonvm.placement.guard" -}}
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

{{- define "neonvm.placement.pool" -}}
{{- join "-" (sortAlpha .Values.placement.allowedNodeNames) -}}
{{- end -}}

{{- define "neonvm.placement.selector" -}}
nodeSelector:
  kubernetes.io/os: linux
  kubernetes.io/arch: amd64
  neon.tech/pg17-memory-pool: {{ include "neonvm.placement.pool" . | quote }}
{{- end -}}

{{- define "neonvm.placement.hostMatch" -}}
- key: kubernetes.io/hostname
  operator: In
  values: {{ toJson (sortAlpha .Values.placement.allowedNodeNames) }}
{{- end -}}

{{- define "neonvm.placement.nodeAffinity" -}}
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
    - matchExpressions:
      {{- include "neonvm.placement.hostMatch" . | nindent 6 }}
{{- end -}}

{{- define "neonvm.placement.pod" -}}
{{ include "neonvm.placement.selector" . }}
affinity:
  {{- include "neonvm.placement.nodeAffinity" . | nindent 2 }}
{{- end -}}

{{/* Controller专用收紧条件：只附加白名单hostname，不merge任意nodeSelector，避免覆盖pool/os/arch。 */}}
{{- define "neonvm.placement.controllerSelector" -}}
{{- if not (kindIs "map" .Values.controller.nodeSelector) -}}
{{- fail "controller.nodeSelector must be a hostname-only map" -}}
{{- end -}}
{{- range $key, $value := .Values.controller.nodeSelector -}}
{{- if ne $key "kubernetes.io/hostname" -}}
{{- fail "controller.nodeSelector may only add kubernetes.io/hostname; pool/os/arch cannot be overridden" -}}
{{- end -}}
{{- if not (has $value $.Values.placement.allowedNodeNames) -}}
{{- fail "controller.nodeSelector hostname must belong to placement.allowedNodeNames" -}}
{{- end -}}
{{- end -}}
{{ include "neonvm.placement.selector" . }}
{{- with index .Values.controller.nodeSelector "kubernetes.io/hostname" }}
  kubernetes.io/hostname: {{ . | quote }}
{{- end }}
{{- end -}}
