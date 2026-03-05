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

{{/*
Database environment variables.
Usage: {{- include "zero-cache.env.database" .root | nindent 12 }}
(Expects the root context, i.e. the top-level .)
*/}}
{{- define "zero-cache.env.database" -}}
- name: ZERO_UPSTREAM_DB
  {{- if .Values.common.database.upstream.url.valueFrom }}
  valueFrom:
    {{ toYaml .Values.common.database.upstream.url.valueFrom | nindent 4 }}
  {{- else }}
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-db
      key: upstream-db
  {{- end }}
- name: ZERO_UPSTREAM_MAX_CONNS
  value: "{{ .Values.common.database.upstream.maxConns }}"
{{- if or .Values.common.database.cvr.url.value .Values.common.database.cvr.url.valueFrom }}
- name: ZERO_CVR_DB
  {{- if .Values.common.database.cvr.url.valueFrom }}
  valueFrom:
    {{ toYaml .Values.common.database.cvr.url.valueFrom | nindent 4 }}
  {{- else }}
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-db
      key: cvr-db
  {{- end }}
{{- end }}
- name: ZERO_CVR_MAX_CONNS
  value: "{{ .Values.common.database.cvr.maxConns }}"
{{- if or .Values.common.database.change.url.value .Values.common.database.change.url.valueFrom }}
- name: ZERO_CHANGE_DB
  {{- if .Values.common.database.change.url.valueFrom }}
  valueFrom:
    {{ toYaml .Values.common.database.change.url.valueFrom | nindent 4 }}
  {{- else }}
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-db
      key: change-db
  {{- end }}
{{- end }}
- name: ZERO_CHANGE_MAX_CONNS
  value: "{{ .Values.common.database.change.maxConns }}"
{{- with .Values.common.database.cvr.garbageCollection }}
{{- if .initialBatchSize }}
- name: ZERO_CVR_GARBAGE_COLLECTION_INITIAL_BATCH_SIZE
  value: "{{ .initialBatchSize }}"
- name: ZERO_CVR_GARBAGE_COLLECTION_INITIAL_INTERVAL_SECONDS
  value: "{{ .initialIntervalSeconds }}"
- name: ZERO_CVR_GARBAGE_COLLECTION_INACTIVITY_THRESHOLD_HOURS
  value: "{{ .inactivityThresholdHours }}"
{{- end }}
{{- end }}
{{- end -}}

{{/*
Authentication environment variables (deprecated >=0.25 but still functional).
*/}}
{{- define "zero-cache.env.auth" -}}
{{- if or .Values.common.auth.secret.value .Values.common.auth.secret.valueFrom }}
- name: ZERO_AUTH_SECRET
  {{- if .Values.common.auth.secret.value }}
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-auth
      key: auth-secret
  {{- else }}
  valueFrom:
    {{ toYaml .Values.common.auth.secret.valueFrom | nindent 4 }}
  {{- end }}
{{- end }}
{{- if or .Values.common.auth.jwk.value .Values.common.auth.jwk.valueFrom }}
- name: ZERO_AUTH_JWK
  {{- if .Values.common.auth.jwk.value }}
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-auth
      key: auth-jwk
  {{- else }}
  valueFrom:
    {{ toYaml .Values.common.auth.jwk.valueFrom | nindent 4 }}
  {{- end }}
{{- end }}
{{- if or .Values.common.auth.jwksUrl.value .Values.common.auth.jwksUrl.valueFrom }}
- name: ZERO_AUTH_JWKS_URL
  {{- if .Values.common.auth.jwksUrl.value }}
  value: "{{ .Values.common.auth.jwksUrl.value }}"
  {{- else }}
  valueFrom:
    {{ toYaml .Values.common.auth.jwksUrl.valueFrom | nindent 4 }}
  {{- end }}
{{- end }}
{{- end -}}

{{/*
Admin password environment variable.
*/}}
{{- define "zero-cache.env.admin" -}}
{{- if or .Values.common.adminPassword.value .Values.common.adminPassword.valueFrom }}
- name: ZERO_ADMIN_PASSWORD
  {{- if .Values.common.adminPassword.valueFrom }}
  valueFrom:
    {{ toYaml .Values.common.adminPassword.valueFrom | nindent 4 }}
  {{- else }}
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-admin
      key: admin-password
  {{- end }}
{{- end }}
{{- end -}}

{{/*
Rate limiting environment variables.
*/}}
{{- define "zero-cache.env.ratelimit" -}}
{{- if .Values.common.rateLimiting.perUserMutationLimitMax }}
- name: ZERO_PER_USER_MUTATION_LIMIT_MAX
  value: "{{ .Values.common.rateLimiting.perUserMutationLimitMax }}"
{{- end }}
- name: ZERO_PER_USER_MUTATION_LIMIT_WINDOW_MS
  value: "{{ .Values.common.rateLimiting.perUserMutationLimitWindowMs }}"
{{- end -}}

{{/*
Mutator/query API environment variables.
Version-conditional: ZERO_PUSH_URL <0.24, ZERO_MUTATE_URL >=0.24.
Query URL, API keys, and cookie forwarding only exist >=0.24.
*/}}
{{- define "zero-cache.env.mutators" -}}
{{- $zv := include "zero-cache.zeroVersion" . -}}
{{- if .Values.common.api.mutateUrl }}
{{- if semverCompare ">=0.24.0" $zv }}
- name: ZERO_MUTATE_URL
  value: "{{ .Values.common.api.mutateUrl }}"
{{- else }}
- name: ZERO_PUSH_URL
  value: "{{ .Values.common.api.mutateUrl }}"
{{- end }}
{{- end }}
{{- if and (semverCompare ">=0.24.0" $zv) .Values.common.api.queryUrl }}
- name: ZERO_QUERY_URL
  value: "{{ .Values.common.api.queryUrl }}"
{{- end }}
{{- if semverCompare ">=0.24.0" $zv }}
{{- if or .Values.common.api.mutateApiKey.value .Values.common.api.mutateApiKey.valueFrom }}
- name: ZERO_MUTATE_API_KEY
  {{- if .Values.common.api.mutateApiKey.value }}
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-api
      key: mutate-api-key
  {{- else }}
  valueFrom:
    {{ toYaml .Values.common.api.mutateApiKey.valueFrom | nindent 4 }}
  {{- end }}
{{- end }}
{{- if or .Values.common.api.queryApiKey.value .Values.common.api.queryApiKey.valueFrom }}
- name: ZERO_QUERY_API_KEY
  {{- if .Values.common.api.queryApiKey.value }}
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-api
      key: query-api-key
  {{- else }}
  valueFrom:
    {{ toYaml .Values.common.api.queryApiKey.valueFrom | nindent 4 }}
  {{- end }}
{{- end }}
{{- if .Values.common.api.mutateForwardCookies }}
- name: ZERO_MUTATE_FORWARD_COOKIES
  value: "true"
{{- end }}
{{- if .Values.common.api.queryForwardCookies }}
- name: ZERO_QUERY_FORWARD_COOKIES
  value: "true"
{{- end }}
{{- end }}
{{- end -}}

{{/*
Litestream configuration environment variables (shared).
Does NOT include ZERO_LITESTREAM_BACKUP_URL (workload-specific).
*/}}
{{- define "zero-cache.env.litestream" -}}
{{- if or .Values.s3.enabled .Values.common.litestream.backupUrl }}
- name: ZERO_LITESTREAM_CONFIG_PATH
  value: "/etc/litestream/litestream.yml"
{{- end }}
- name: ZERO_LITESTREAM_CHECKPOINT_THRESHOLD_MB
  value: "{{ .Values.common.litestream.checkpointThresholdMb }}"
- name: ZERO_LITESTREAM_INCREMENTAL_BACKUP_INTERVAL_MINUTES
  value: "{{ .Values.common.litestream.incrementalBackupIntervalMinutes }}"
- name: ZERO_LITESTREAM_SNAPSHOT_BACKUP_INTERVAL_HOURS
  value: "{{ .Values.common.litestream.snapshotBackupIntervalHours }}"
- name: ZERO_LITESTREAM_RESTORE_PARALLELISM
  value: "{{ .Values.common.litestream.restoreParallelism }}"
- name: ZERO_LITESTREAM_LOG_LEVEL
  value: "{{ .Values.common.litestream.logLevel }}"
- name: ZERO_LITESTREAM_MULTIPART_CONCURRENCY
  value: "{{ .Values.common.litestream.multipartConcurrency }}"
- name: ZERO_LITESTREAM_MULTIPART_SIZE
  value: "{{ .Values.common.litestream.multipartSize }}"
{{- end -}}

{{/*
S3/AWS credential environment variables.
*/}}
{{- define "zero-cache.env.s3" -}}
{{- if .Values.s3.enabled }}
{{- if or .Values.s3.accessKey.value .Values.s3.accessKey.valueFrom }}
- name: AWS_ACCESS_KEY_ID
  {{- if .Values.s3.accessKey.value }}
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-s3
      key: access-key
  {{- else }}
  valueFrom:
    {{ toYaml .Values.s3.accessKey.valueFrom | nindent 4 }}
  {{- end }}
{{- end }}
{{- if or .Values.s3.secretKey.value .Values.s3.secretKey.valueFrom }}
- name: AWS_SECRET_ACCESS_KEY
  {{- if .Values.s3.secretKey.value }}
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-s3
      key: secret-key
  {{- else }}
  valueFrom:
    {{ toYaml .Values.s3.secretKey.valueFrom | nindent 4 }}
  {{- end }}
{{- end }}
- name: AWS_REGION
  value: "{{ .Values.s3.region }}"
{{- if .Values.s3.endpoint }}
- name: AWS_ENDPOINT_URL
  value: "{{ .Values.s3.endpoint }}"
{{- end }}
{{- end }}
{{- end -}}

{{/*
Performance tuning environment variables.
*/}}
{{- define "zero-cache.env.performance" -}}
{{- if .Values.common.performance.replicaVacuumIntervalHours }}
- name: ZERO_REPLICA_VACUUM_INTERVAL_HOURS
  value: "{{ .Values.common.performance.replicaVacuumIntervalHours }}"
{{- end }}
- name: ZERO_INITIAL_SYNC_TABLE_COPY_WORKERS
  value: "{{ .Values.common.performance.initialSyncTableCopyWorkers }}"
{{- end -}}

{{/*
Logging and telemetry environment variables.
*/}}
{{- define "zero-cache.env.logging" -}}
- name: ZERO_LOG_FORMAT
  value: "{{ .Values.common.logging.format }}"
- name: ZERO_LOG_LEVEL
  value: "{{ .Values.common.logging.level }}"
- name: ZERO_LOG_SLOW_HYDRATE_THRESHOLD
  value: "{{ .Values.common.logging.slowHydrateThreshold }}"
- name: ZERO_LOG_SLOW_ROW_THRESHOLD
  value: "{{ .Values.common.logging.slowRowThreshold }}"
- name: ZERO_LOG_IVM_SAMPLING
  value: "{{ .Values.common.logging.ivmSampling }}"
{{- if .Values.common.logging.otel.enable }}
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: "{{ .Values.common.logging.otel.endpoint }}"
- name: OTEL_EXPORTER_OTLP_HEADERS
  value: "{{ .Values.common.logging.otel.headers }}"
- name: OTEL_RESOURCE_ATTRIBUTES
  value: "{{ .Values.common.logging.otel.resourceAttributes }}"
- name: OTEL_NODE_RESOURCE_DETECTORS
  value: "{{ .Values.common.logging.otel.nodeResourceDetectors }}"
{{- end }}
{{- end -}}

{{/*
Advanced/optional environment variables.
*/}}
{{- define "zero-cache.env.advanced" -}}
{{- if .Values.common.advanced.lazyStartup }}
- name: ZERO_LAZY_STARTUP
  value: "true"
{{- end }}
{{- if not .Values.common.advanced.enableTelemetry }}
- name: DO_NOT_TRACK
  value: "1"
{{- end }}
{{- if not .Values.common.advanced.enableQueryPlanner }}
- name: ZERO_ENABLE_QUERY_PLANNER
  value: "false"
{{- end }}
{{- if .Values.common.advanced.yieldThresholdMs }}
- name: ZERO_YIELD_THRESHOLD_MS
  value: "{{ .Values.common.advanced.yieldThresholdMs }}"
{{- end }}
{{- if .Values.common.advanced.replicaPageCacheSizeKib }}
- name: ZERO_REPLICA_PAGE_CACHE_SIZE_KIB
  value: "{{ .Values.common.advanced.replicaPageCacheSizeKib }}"
{{- end }}
{{- if .Values.common.advanced.storageTmpDir }}
- name: ZERO_STORAGE_DB_TMP_DIR
  value: "{{ .Values.common.advanced.storageTmpDir }}"
{{- end }}
{{- if .Values.common.advanced.websocketCompression }}
- name: ZERO_WEBSOCKET_COMPRESSION
  value: "true"
{{- if .Values.common.advanced.websocketCompressionOptions }}
- name: ZERO_WEBSOCKET_COMPRESSION_OPTIONS
  value: {{ .Values.common.advanced.websocketCompressionOptions | quote }}
{{- end }}
{{- end }}
{{- end -}}
