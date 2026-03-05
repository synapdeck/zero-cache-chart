{{/*
Expand the name of the chart.
*/}}
{{- define "zero-cache.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "zero-cache.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "zero-cache.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "zero-cache.labels" -}}
helm.sh/chart: {{ include "zero-cache.chart" . }}
{{ include "zero-cache.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: zero-cache
{{- end }}

{{/*
Selector labels
*/}}
{{- define "zero-cache.selectorLabels" -}}
app.kubernetes.io/name: {{ include "zero-cache.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "zero-cache.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "zero-cache.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Extract major.minor.0 from image.tag (or appVersion) for semverCompare.
Examples: "0.26.1-canary.4" -> "0.26.0", "0.20.2025051800" -> "0.20.0"
*/}}
{{- define "zero-cache.zeroVersion" -}}
{{- $raw := .Values.image.tag | default .Chart.AppVersion | toString -}}
{{- $parts := splitList "." $raw -}}
{{- printf "%s.%s.0" (index $parts 0) (index $parts 1) -}}
{{- end -}}

{{/*
Core environment variables shared by all workloads.
Usage: {{- include "zero-cache.env.core" (dict "port" .Values.singleNode.service.port "root" .) | nindent 12 }}
*/}}
{{- define "zero-cache.env.core" -}}
- name: ZERO_PORT
  value: "{{ .port }}"
- name: ZERO_APP_ID
  value: "{{ .root.Values.common.appId }}"
{{- if .root.Values.common.appPublications }}
- name: ZERO_APP_PUBLICATIONS
  value: {{ .root.Values.common.appPublications | join "," | quote }}
{{- end }}
- name: ZERO_REPLICA_FILE
  value: "{{ .root.Values.common.replicaFile }}"
- name: ZERO_AUTO_RESET
  value: "{{ .root.Values.common.autoReset }}"
{{- end -}}
