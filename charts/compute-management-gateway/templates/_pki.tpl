{{- define "compute-management-gateway.dsga.pkiNames" -}}
{{- $p := .Values.dsga.pki -}}
{{- dict
  "selfSignedIssuer" (default (printf "%s-dsga-selfsigned" .Release.Name | trunc 63 | trimSuffix "-") $p.selfSignedIssuerName)
  "rootCertificate" (default (printf "%s-dsga-root-ca" .Release.Name | trunc 63 | trimSuffix "-") $p.rootCertificateName)
  "rootSecret" (default (printf "%s-dsga-root-ca" .Release.Name | trunc 63 | trimSuffix "-") $p.rootSecretName)
  "caIssuer" (default (printf "%s-dsga-ca" .Release.Name | trunc 63 | trimSuffix "-") $p.caIssuerName)
  "certificate" (default .Values.dsga.tlsSecret $p.certificateName)
  | toJson -}}
{{- end -}}
