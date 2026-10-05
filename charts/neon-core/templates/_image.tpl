{{- define "neon-lab.neon-image" -}}
{{- if .Values.global.neonImage.digest -}}
{{ .Values.global.neonImage.repository }}@{{ .Values.global.neonImage.digest }}
{{- else -}}
{{ .Values.global.neonImage.repository }}:{{ .Values.global.neonImage.tag }}
{{- end -}}
{{- end -}}

{{- define "neon-lab.component-image" -}}
{{- $root := index . 0 -}}
{{- $name := index . 1 -}}
{{- $images := $root.Values.global.componentImages | default dict -}}
{{- $image := index $images $name -}}
{{- if $image -}}
{{- $image -}}
{{- else -}}
{{- include "neon-lab.neon-image" $root -}}
{{- end -}}
{{- end -}}
