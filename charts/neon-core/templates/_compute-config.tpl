{{/* Match the public SQL bootstrap to the actual image extension inventory.
     The original full profile is returned unchanged. DSGA core cannot preload
     third-party extensions that the PG18 distribution deliberately omits. */}}
{{- define "neon-lab.compute-public-config" -}}
{{- if eq (.Values.compute.buildProfile | default "full") "dsga-core" -}}
{{- $config := .Files.Get "files/compute-public-config.json" | fromJson -}}
{{- $settings := list -}}
{{- range $setting := $config.spec.cluster.settings -}}
  {{- if eq $setting.name "shared_preload_libraries" -}}
    {{- $_ := set $setting "value" "neon,pg_stat_statements" -}}
  {{- end -}}
  {{- if not (or (hasPrefix "cron." $setting.name) (hasPrefix "timescaledb." $setting.name)) -}}
    {{- $settings = append $settings $setting -}}
  {{- end -}}
{{- end -}}
{{- $_ := set $config.spec.cluster "settings" $settings -}}
{{- $config | toPrettyJson -}}
{{- else -}}
{{- .Files.Get "files/compute-public-config.json" -}}
{{- end -}}
{{- end -}}
