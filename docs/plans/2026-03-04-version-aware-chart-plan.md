# Version-Aware Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace per-version git branches with version-aware Helm templates that emit correct env vars for zero-cache 0.22+, simplify the CLI to a linear update flow, and clean up broken OCI artifacts.

**Architecture:** A `zero-cache.zeroVersion` helper extracts major.minor from `image.tag`. Named env block templates in `_helpers.tpl` use `semverCompare` to emit the right env var names per version. The CLI drops all branch management, only updating main and pushing release tags. Chart version becomes independent (1.x.x) from appVersion.

**Tech Stack:** Helm templates (Go templates, semverCompare), Python/click CLI, GitHub Actions, GitHub Packages API

**Design doc:** `docs/plans/2026-03-04-version-aware-chart-design.md`

---

### Task 1: Update values.yaml

Replace `customMutators` with `api`, remove deprecated `targetClientRowCount`, add all new env var sections.

**Files:**
- Modify: `values.yaml`

**Step 1: Replace customMutators with api section**

In `values.yaml`, replace:

```yaml
  # Custom mutator settings
  customMutators:
    # URL for pushing custom mutations to your server
    # Required if you use custom mutators: https://zero.rocicorp.dev/docs/custom-mutators
    pushUrl: ""
```

With:

```yaml
  # API server endpoints (custom queries and mutators)
  # See: https://zero.rocicorp.dev/docs/custom-mutators
  api:
    # URL for mutation handler (ZERO_MUTATE_URL >=0.24, ZERO_PUSH_URL <0.24)
    mutateUrl: ""
    # URL for query handler (>=0.24 only)
    queryUrl: ""
    # API key for authorizing zero-cache to call mutation handler
    mutateApiKey: {}
      # value: "your-api-key"
      # valueFrom:
      #   secretKeyRef:
      #     name: my-api-key
      #     key: mutate-key
    # API key for authorizing zero-cache to call query handler
    queryApiKey: {}
      # value: "your-api-key"
      # valueFrom:
      #   secretKeyRef:
      #     name: my-api-key
      #     key: query-key
    # Forward cookies from client requests to mutation handler
    mutateForwardCookies: false
    # Forward cookies from client requests to query handler
    queryForwardCookies: false
```

**Step 2: Remove deprecated performance setting**

Remove `targetClientRowCount: 20000` from `common.performance`.

**Step 3: Add advanced section**

After `customMutators` replacement (which is now `api`), add:

```yaml
  # Advanced configuration
  advanced:
    # Delay startup until first request (single-node only)
    lazyStartup: false
    # Anonymous telemetry (set false or DO_NOT_TRACK=1 to disable)
    enableTelemetry: true
    # Enable query planner for ZQL optimization
    enableQueryPlanner: true
    # Max ms a sync worker spends in IVM before yielding
    yieldThresholdMs: 10
    # SQLite page cache size in KiB (null = SQLite default ~2MB)
    replicaPageCacheSizeKib: null
    # Temp directory for IVM operator storage
    storageTmpDir: ""
    # WebSocket per-message deflate compression
    websocketCompression: false
    # WebSocket compression options (JSON string)
    websocketCompressionOptions: ""

```

**Step 4: Add CVR garbage collection**

Under `common.database.cvr`, after `maxConns: 30`, add:

```yaml
      # CVR garbage collection
      garbageCollection:
        # Hours of inactivity before CVR eligible for purging
        inactivityThresholdHours: 48
        # CVRs purged per GC interval (0 = disabled)
        initialBatchSize: 25
        # Initial interval in seconds between GC checks
        initialIntervalSeconds: 60
```

**Step 5: Add litestream multipart settings**

Under `common.litestream`, after `logLevel: warn`, add:

```yaml
    # Parallel parts for snapshot upload/download
    multipartConcurrency: 48
    # Size of each multipart chunk in bytes (default 16 MiB)
    multipartSize: 16777216
```

**Step 6: Set chart version to 1.0.0**

In `Chart.yaml`, change `version: 0.26.1-canary.4` to `version: 1.0.0`. Keep `appVersion: 0.26.1-canary.4`.

**Step 7: Commit**

```bash
git add values.yaml Chart.yaml
git commit -m "feat(values): add all documented env vars, independent chart version

- Replace customMutators.pushUrl with api section (mutateUrl, queryUrl, API keys, cookies)
- Remove deprecated targetClientRowCount (gone since 0.22)
- Add advanced section (lazyStartup, queryPlanner, websocket, telemetry)
- Add CVR garbage collection settings
- Add litestream multipart settings
- Set chart version to 1.0.0 (independent of appVersion)"
```

---

### Task 2: Version Detection Helper and Core Env Block

Add `zero-cache.zeroVersion` helper and the first named env template `zero-cache.env.core`.

**Files:**
- Modify: `templates/_helpers.tpl`

**Step 1: Add version helper**

At end of `_helpers.tpl`, add:

```yaml
{{/*
Extract major.minor.0 from image.tag (or appVersion) for semverCompare.
Examples: "0.26.1-canary.4" -> "0.26.0", "0.20.2025051800" -> "0.20.0"
*/}}
{{- define "zero-cache.zeroVersion" -}}
{{- $raw := .Values.image.tag | default .Chart.AppVersion | toString -}}
{{- $parts := splitList "." $raw -}}
{{- printf "%s.%s.0" (index $parts 0) (index $parts 1) -}}
{{- end -}}
```

**Step 2: Add env.core template**

This block is emitted by all three workloads. The PORT value is passed as a template parameter since it differs per workload.

```yaml
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
```

**Step 3: Validate the helper renders correctly**

Run: `helm template test . --set common.database.upstream.url.value="postgres://u:p@h:5432/d" --set image.tag=0.24.2025010100 --show-only templates/single-node-deployment.yaml 2>&1 | head -5`

At this stage the templates still use inline env vars, so this just verifies the helper doesn't break rendering. We'll wire them up in later tasks.

**Step 4: Commit**

```bash
git add templates/_helpers.tpl
git commit -m "feat(helpers): add zeroVersion helper and env.core template"
```

---

### Task 3: Database, Auth, Admin, and Rate Limit Env Blocks

**Files:**
- Modify: `templates/_helpers.tpl`

**Step 1: Add env.database template**

```yaml
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
```

**Step 2: Add env.auth template**

```yaml
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
```

**Step 3: Add env.admin template**

```yaml
{{/*
Admin password environment variable.
*/}}
{{- define "zero-cache.env.admin" -}}
{{- if .Values.common.adminPassword }}
- name: ZERO_ADMIN_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "zero-cache.fullname" . }}-admin
      key: admin-password
{{- end }}
{{- end -}}
```

**Step 4: Add env.ratelimit template**

```yaml
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
```

**Step 5: Commit**

```bash
git add templates/_helpers.tpl
git commit -m "feat(helpers): add database, auth, admin, and ratelimit env templates"
```

---

### Task 4: Mutators Env Block (Version-Conditional)

**Files:**
- Modify: `templates/_helpers.tpl`

**Step 1: Add env.mutators template**

This is the key version-conditional block: `ZERO_PUSH_URL` for <0.24, `ZERO_MUTATE_URL` for >=0.24. Query URL, API keys, and forward cookies are >=0.24 only.

```yaml
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
```

**Step 2: Commit**

```bash
git add templates/_helpers.tpl
git commit -m "feat(helpers): add version-conditional mutators env template

ZERO_PUSH_URL for <0.24, ZERO_MUTATE_URL for >=0.24.
Query URL, API keys, and cookie forwarding only emitted for >=0.24."
```

---

### Task 5: Litestream, S3, Performance, Logging, and Advanced Env Blocks

**Files:**
- Modify: `templates/_helpers.tpl`

**Step 1: Add env.litestream template**

Note: `ZERO_LITESTREAM_BACKUP_URL` is NOT included here — it's workload-specific (only repl-mgr and single-node). This block is the shared config vars.

```yaml
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
```

**Step 2: Add env.s3 template**

```yaml
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
```

**Step 3: Add env.performance template**

```yaml
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
```

**Step 4: Add env.logging template**

```yaml
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
```

**Step 5: Add env.advanced template**

```yaml
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
```

**Step 6: Commit**

```bash
git add templates/_helpers.tpl
git commit -m "feat(helpers): add litestream, s3, performance, logging, advanced env templates"
```

---

### Task 6: Rewire Workload Templates

Replace inline env vars in all three workload templates with named includes. Keep workload-specific vars (CHANGE_STREAMER_MODE, NUM_SYNC_WORKERS, LITESTREAM_BACKUP_URL) inline.

**Files:**
- Modify: `templates/single-node-deployment.yaml`
- Modify: `templates/view-syncer-statefulset.yaml`
- Modify: `templates/replication-manager-statefulset.yaml`

**Step 1: Rewrite single-node env section**

Replace the entire `env:` block (lines 70-250) with:

```yaml
          env:
            {{- include "zero-cache.env.core" (dict "port" .Values.singleNode.service.port "root" .) | nindent 12 }}
            - name: ZERO_CHANGE_STREAMER_MODE
              value: "dedicated"
            {{- include "zero-cache.env.auth" . | nindent 12 }}
            {{- include "zero-cache.env.admin" . | nindent 12 }}
            {{- include "zero-cache.env.database" . | nindent 12 }}
            {{- if .Values.common.litestream.backupUrl }}
            - name: ZERO_LITESTREAM_BACKUP_URL
              value: "{{ .Values.common.litestream.backupUrl }}"
            {{- end }}
            {{- include "zero-cache.env.litestream" . | nindent 12 }}
            {{- include "zero-cache.env.s3" . | nindent 12 }}
            {{- include "zero-cache.env.performance" . | nindent 12 }}
            {{- include "zero-cache.env.logging" . | nindent 12 }}
            {{- include "zero-cache.env.ratelimit" . | nindent 12 }}
            {{- include "zero-cache.env.mutators" . | nindent 12 }}
            {{- include "zero-cache.env.advanced" . | nindent 12 }}
```

**Step 2: Rewrite view-syncer env section**

Replace the entire `env:` block with:

```yaml
          env:
            {{- include "zero-cache.env.core" (dict "port" .Values.viewSyncer.service.port "root" .) | nindent 12 }}
            - name: ZERO_CHANGE_STREAMER_MODE
              value: "discover"
            {{- include "zero-cache.env.auth" . | nindent 12 }}
            {{- include "zero-cache.env.admin" . | nindent 12 }}
            {{- include "zero-cache.env.database" . | nindent 12 }}
            {{- include "zero-cache.env.litestream" . | nindent 12 }}
            {{- include "zero-cache.env.s3" . | nindent 12 }}
            {{- include "zero-cache.env.performance" . | nindent 12 }}
            {{- include "zero-cache.env.logging" . | nindent 12 }}
            {{- include "zero-cache.env.ratelimit" . | nindent 12 }}
            {{- include "zero-cache.env.mutators" . | nindent 12 }}
            {{- include "zero-cache.env.advanced" . | nindent 12 }}
```

**Step 3: Rewrite replication-manager env section**

Replace the entire `env:` block with:

```yaml
          env:
            {{- include "zero-cache.env.core" (dict "port" .Values.replicationManager.service.port "root" .) | nindent 12 }}
            - name: ZERO_NUM_SYNC_WORKERS
              value: "0"
            {{- include "zero-cache.env.auth" . | nindent 12 }}
            {{- include "zero-cache.env.admin" . | nindent 12 }}
            {{- include "zero-cache.env.database" . | nindent 12 }}
            {{- if .Values.common.litestream.backupUrl }}
            - name: ZERO_LITESTREAM_BACKUP_URL
              value: "{{ .Values.common.litestream.backupUrl }}"
            {{- end }}
            {{- include "zero-cache.env.litestream" . | nindent 12 }}
            {{- include "zero-cache.env.s3" . | nindent 12 }}
            {{- include "zero-cache.env.performance" . | nindent 12 }}
            {{- include "zero-cache.env.logging" . | nindent 12 }}
            {{- include "zero-cache.env.ratelimit" . | nindent 12 }}
            {{- include "zero-cache.env.mutators" . | nindent 12 }}
            {{- include "zero-cache.env.advanced" . | nindent 12 }}
```

**Step 4: Validate all three modes render without errors**

Run:
```bash
helm template test . --set common.database.upstream.url.value="postgres://u:p@h:5432/d" --set singleNode.enabled=true > /dev/null && echo "single-node: OK"
helm template test . --set common.database.upstream.url.value="postgres://u:p@h:5432/d" > /dev/null && echo "multi-node: OK"
helm template test . --set common.database.upstream.url.value="postgres://u:p@h:5432/d" --set s3.enabled=true --set s3.accessKey.value=AK --set s3.secretKey.value=SK > /dev/null && echo "multi-node+s3: OK"
```

**Step 5: Validate version-conditional behavior**

Run:
```bash
# Should output ZERO_MUTATE_URL (>=0.24)
helm template test . --set common.database.upstream.url.value="postgres://u:p@h:5432/d" --set singleNode.enabled=true --set image.tag=0.26.0 --set common.api.mutateUrl=http://app/mutate | grep -E "ZERO_(MUTATE|PUSH)_URL"

# Should output ZERO_PUSH_URL (<0.24)
helm template test . --set common.database.upstream.url.value="postgres://u:p@h:5432/d" --set singleNode.enabled=true --set image.tag=0.23.2025010100 --set common.api.mutateUrl=http://app/mutate | grep -E "ZERO_(MUTATE|PUSH)_URL"
```

**Step 6: Commit**

```bash
git add templates/single-node-deployment.yaml templates/view-syncer-statefulset.yaml templates/replication-manager-statefulset.yaml
git commit -m "refactor(templates): replace inline env vars with named includes

All three workloads now use shared env block templates from _helpers.tpl.
Version-conditional mutator env var name verified working."
```

---

### Task 7: Add API Key Secrets

If API keys are provided as direct values, they need a Secret resource (like the existing auth secrets).

**Files:**
- Modify: `templates/secrets.yaml`

**Step 1: Read current secrets.yaml**

Read `templates/secrets.yaml` to understand the existing pattern.

**Step 2: Add API key secret block**

Add a new secret block following the existing pattern for auth/admin/db/s3 secrets:

```yaml
{{- if or .Values.common.api.mutateApiKey.value .Values.common.api.queryApiKey.value }}
---
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "zero-cache.fullname" . }}-api
  labels:
    {{- include "zero-cache.labels" . | nindent 4 }}
type: Opaque
data:
  {{- if .Values.common.api.mutateApiKey.value }}
  mutate-api-key: {{ .Values.common.api.mutateApiKey.value | b64enc | quote }}
  {{- end }}
  {{- if .Values.common.api.queryApiKey.value }}
  query-api-key: {{ .Values.common.api.queryApiKey.value | b64enc | quote }}
  {{- end }}
{{- end }}
```

**Step 3: Commit**

```bash
git add templates/secrets.yaml
git commit -m "feat(secrets): add API key secret for mutate/query API keys"
```

---

### Task 8: Simplify chart.py for Independent Versioning

Update `write_chart_version` to set appVersion and bump chart patch independently.

**Files:**
- Modify: `src/zero_cache_chart/chart.py`
- Modify: `tests/test_chart.py`

**Step 1: Write the failing tests**

Add to `tests/test_chart.py`:

```python
def test_write_chart_version_independent(tmp_path: Path):
    """Chart version bumps patch independently from appVersion."""
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.25.0\nversion: 1.0.0\nname: zero-cache\n")
    write_chart_version(chart, Version.parse("0.26.0"))
    data = yaml.safe_load(chart.read_text())
    assert data["appVersion"] == "0.26.0"
    assert data["version"] == "1.0.1"


def test_write_chart_version_no_change(tmp_path: Path):
    """Chart version unchanged when appVersion is the same."""
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.26.0\nversion: 1.0.5\nname: zero-cache\n")
    write_chart_version(chart, Version.parse("0.26.0"))
    data = yaml.safe_load(chart.read_text())
    assert data["appVersion"] == "0.26.0"
    assert data["version"] == "1.0.5"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chart.py -v`

**Step 3: Update write_chart_version**

Replace `write_chart_version` in `src/zero_cache_chart/chart.py`:

```python
def write_chart_version(chart_path: Path, version: Version) -> None:
    text = chart_path.read_text()
    data = yaml.safe_load(text)
    current_app = str(data.get("appVersion", ""))
    new_app = str(version)

    if current_app == new_app:
        return  # Nothing to update

    data["appVersion"] = new_app

    # Bump chart patch version independently
    chart_ver = data.get("version", "0.0.0")
    if Version.is_valid(str(chart_ver)):
        cv = Version.parse(str(chart_ver))
        data["version"] = str(cv.bump_patch())
    else:
        data["version"] = new_app

    chart_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
```

**Step 4: Fix the old test**

Update `test_write_chart_version` to expect independent versioning:

```python
def test_write_chart_version(tmp_path: Path):
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.25.0\nversion: 1.0.0\nname: zero-cache\n")
    write_chart_version(chart, Version.parse("0.26.0"))
    ver = read_chart_version(chart)
    assert ver == Version.parse("0.26.0")
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_chart.py -v`

**Step 6: Commit**

```bash
git add src/zero_cache_chart/chart.py tests/test_chart.py
git commit -m "feat(chart): independent chart version with patch auto-bump"
```

---

### Task 9: Simplify versions.py

Remove branch management functions, keep only what the linear flow needs.

**Files:**
- Modify: `src/zero_cache_chart/versions.py`
- Modify: `tests/test_versions.py`

**Step 1: Remove functions**

Remove `select_retained_branches` and `branch_pointer_tags` from `versions.py`.

The file should contain only:

```python
from __future__ import annotations

from semver.version import Version


def is_stable(version: Version) -> bool:
    return version.prerelease is None


def build_version_map(versions: list[Version]) -> dict[str, Version]:
    vmap: dict[str, Version] = {}
    for ver in versions:
        mm = f"{ver.major}.{ver.minor}"
        if mm not in vmap or ver > vmap[mm]:
            vmap[mm] = ver
    return vmap


def get_latest_version(versions: list[Version]) -> Version | None:
    return versions[-1] if versions else None


def classify_version_tag(version: Version) -> tuple[str, str]:
    tag_name = f"v{version}"
    kind = "prerelease" if version.prerelease else "stable"
    return tag_name, kind
```

**Step 2: Remove tests for deleted functions**

Remove `TestSelectRetainedBranches` and `TestBranchPointerTags` from `tests/test_versions.py`. Update the import to remove `select_retained_branches` and `branch_pointer_tags`.

**Step 3: Run tests**

Run: `pytest tests/test_versions.py -v`

**Step 4: Commit**

```bash
git add src/zero_cache_chart/versions.py tests/test_versions.py
git commit -m "refactor(versions): remove branch management functions"
```

---

### Task 10: Simplify git.py

Remove `list_version_branches`. Keep `list_remote_branches` for potential future use but remove the version-branch filter.

**Files:**
- Modify: `src/zero_cache_chart/git.py`
- Modify: `tests/test_git.py`

**Step 1: Remove list_version_branches**

Remove the `list_version_branches` function from `git.py`. Also remove the unused `re` import if no longer needed (check if `parse_major_minor` still uses it — it does, so keep `re`).

**Step 2: Update test imports**

Remove `list_version_branches` from the import in `tests/test_git.py`.

**Step 3: Run tests**

Run: `pytest tests/test_git.py -v`

**Step 4: Commit**

```bash
git add src/zero_cache_chart/git.py tests/test_git.py
git commit -m "refactor(git): remove list_version_branches"
```

---

### Task 11: Simplify types.py

Remove branch-related fields from `VersionManagementResult`.

**Files:**
- Modify: `src/zero_cache_chart/types.py`

**Step 1: Simplify VersionManagementResult**

```python
@dataclass
class VersionManagementResult:
    main_updated: bool = False
    created_tags: list[str] = field(default_factory=list)
    pushed_oci_packages: list[str] = field(default_factory=list)
    current_version: str | None = None
```

**Step 2: Commit**

```bash
git add src/zero_cache_chart/types.py
git commit -m "refactor(types): remove branch-related fields from result"
```

---

### Task 12: Add cleanup-all Command to oci.py

**Files:**
- Modify: `src/zero_cache_chart/oci.py`

**Step 1: Add delete_all_versions function**

After `prune_untagged`, add:

```python
def delete_all_versions(
    org: str,
    package_name: str,
    *,
    dry_run: bool = False,
) -> int:
    """Delete ALL package versions (tagged and untagged). One-time cleanup."""
    versions = list_package_versions(org, package_name)
    count = 0

    for ver in versions:
        tags = ver["metadata"]["container"]["tags"]
        label = ", ".join(tags) if tags else "untagged"
        if dry_run:
            count += 1
        else:
            delete_package_version(org, package_name, ver["id"])
            count += 1

    return count
```

**Step 2: Commit**

```bash
git add src/zero_cache_chart/oci.py
git commit -m "feat(oci): add delete_all_versions for one-time cleanup"
```

---

### Task 13: Rewrite CLI

**Files:**
- Modify: `src/zero_cache_chart/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Rewrite cli.py**

```python
from __future__ import annotations

from pathlib import Path

import click
from semver.version import Version

from zero_cache_chart.chart import read_chart_version, write_chart_version
from zero_cache_chart.docker import fetch_docker_versions
from zero_cache_chart.git import Git
from zero_cache_chart.oci import push_if_not_exists, prune_untagged, delete_all_versions
from zero_cache_chart.types import VersionManagementResult
from zero_cache_chart.versions import (
    get_latest_version,
    classify_version_tag,
)


@click.group()
def main() -> None:
    """zero-cache Helm chart version manager."""


@main.command()
@click.option("--docker-image", required=True, help="Docker image to track (e.g. rocicorp/zero)")
@click.option("--chart-path", default="Chart.yaml", help="Path to Chart.yaml")
@click.option("--oci-registry", default="ghcr.io", help="OCI registry URL")
@click.option("--oci-repo", required=True, help="OCI repository path")
@click.option("--dry-run", is_flag=True, help="Simulate without making changes")
def update(
    docker_image: str,
    chart_path: str,
    oci_registry: str,
    oci_repo: str,
    dry_run: bool,
) -> None:
    """Poll Docker Hub and update chart versions."""
    chart = Path(chart_path)
    git = Git()
    result = VersionManagementResult()

    # 1. Read current chart version
    current_version = read_chart_version(chart)
    result.current_version = str(current_version) if current_version else None
    click.echo(f"Current appVersion: {current_version or 'unknown'}")

    # 2. Fetch Docker Hub versions
    all_versions = fetch_docker_versions(docker_image)
    if not all_versions:
        click.echo("No versions found on Docker Hub")
        return

    latest = get_latest_version(all_versions)
    click.echo(f"Latest upstream: {latest}")

    if not latest or (current_version and latest <= current_version):
        click.echo("Already up to date")
        return

    if dry_run:
        click.echo(f"\n[DRY RUN] Would update: {current_version} -> {latest}")
        tag_name, kind = classify_version_tag(latest)
        click.echo(f"  Create tag: {tag_name} ({kind})")
        click.echo(f"  Push to OCI: {oci_registry}/{oci_repo}")
        return

    # 3. Update Chart.yaml (appVersion + bump chart patch)
    click.echo(f"\nUpdating: {current_version} -> {latest}")
    write_chart_version(chart, latest)
    git.add(chart_path)
    git.commit(f"chore(chart): update appVersion to {latest}")
    git.push("main")
    result.main_updated = True

    # 4. Create release tag
    tag_name, kind = classify_version_tag(latest)
    if not git.tag_exists(tag_name):
        git.create_tag(tag_name)
        git.push_tag(tag_name)
        result.created_tags.append(tag_name)
        click.echo(f"Created tag {tag_name} ({kind})")

    # 5. Push to OCI registry
    version_str = str(latest)
    pushed = push_if_not_exists(oci_registry, oci_repo, version_str)
    if pushed:
        result.pushed_oci_packages.append(version_str)
        click.echo(f"Pushed {version_str} to OCI")
    else:
        click.echo(f"OCI package {version_str} already exists")

    # Summary
    click.echo("\n=== Summary ===")
    click.echo(f"Updated: {result.current_version} -> {latest}")
    if result.created_tags:
        click.echo(f"Tags: {', '.join(result.created_tags)}")
    if result.pushed_oci_packages:
        click.echo(f"OCI: {', '.join(result.pushed_oci_packages)}")


@main.command()
@click.option("--oci-repo", required=True, help="org/package format")
@click.option("--max-age-days", default=7, help="Delete untagged versions older than N days")
@click.option("--all", "prune_all", is_flag=True, help="Delete ALL untagged versions regardless of age")
@click.option("--dry-run", is_flag=True)
def prune(
    oci_repo: str,
    max_age_days: int,
    prune_all: bool,
    dry_run: bool,
) -> None:
    """Prune untagged OCI versions from the registry."""
    parts = oci_repo.split("/", 1)
    if len(parts) != 2:
        raise click.BadParameter(f"Expected org/package format, got: {oci_repo}", param_hint="--oci-repo")

    org, package_name = parts
    click.echo(f"Pruning untagged versions from {org}/{package_name}")

    if dry_run:
        click.echo("[DRY RUN]")

    count = prune_untagged(org, package_name, max_age_days=max_age_days, prune_all=prune_all, dry_run=dry_run)
    action = "Would delete" if dry_run else "Deleted"
    click.echo(f"{action} {count} untagged version(s)")


@main.command("cleanup-all")
@click.option("--oci-repo", required=True, help="org/package format")
@click.option("--dry-run", is_flag=True)
@click.confirmation_option(prompt="This will delete ALL chart versions from the registry. Continue?")
def cleanup_all(oci_repo: str, dry_run: bool) -> None:
    """Delete ALL OCI chart versions (one-time cleanup)."""
    parts = oci_repo.split("/", 1)
    if len(parts) != 2:
        raise click.BadParameter(f"Expected org/package format, got: {oci_repo}", param_hint="--oci-repo")

    org, package_name = parts
    click.echo(f"Deleting ALL versions from {org}/{package_name}")

    if dry_run:
        click.echo("[DRY RUN]")

    count = delete_all_versions(org, package_name, dry_run=dry_run)
    action = "Would delete" if dry_run else "Deleted"
    click.echo(f"{action} {count} version(s)")
```

**Step 2: Update tests**

Replace `tests/test_cli.py`:

```python
from click.testing import CliRunner
from zero_cache_chart.cli import main


def test_main_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "zero-cache Helm chart version manager" in result.output


def test_update_help():
    runner = CliRunner()
    result = runner.invoke(main, ["update", "--help"])
    assert result.exit_code == 0
    assert "--docker-image" in result.output
    assert "--oci-repo" in result.output
    assert "--dry-run" in result.output
    assert "--branch-retention" not in result.output


def test_prune_help():
    runner = CliRunner()
    result = runner.invoke(main, ["prune", "--help"])
    assert result.exit_code == 0
    assert "--oci-repo" in result.output
    assert "--max-age-days" in result.output
    assert "--all" in result.output


def test_cleanup_all_help():
    runner = CliRunner()
    result = runner.invoke(main, ["cleanup-all", "--help"])
    assert result.exit_code == 0
    assert "--oci-repo" in result.output
    assert "--dry-run" in result.output


def test_update_requires_docker_image():
    runner = CliRunner()
    result = runner.invoke(main, ["update", "--oci-repo=foo/bar"])
    assert result.exit_code != 0
    assert "Missing option" in result.output or "required" in result.output.lower()


def test_prune_requires_oci_repo():
    runner = CliRunner()
    result = runner.invoke(main, ["prune"])
    assert result.exit_code != 0
    assert "Missing option" in result.output or "required" in result.output.lower()
```

**Step 3: Run all tests**

Run: `pytest -v`

**Step 4: Commit**

```bash
git add src/zero_cache_chart/cli.py tests/test_cli.py
git commit -m "refactor(cli): simplify to linear update flow, add cleanup-all

- Remove branch management, pointer tags, --branch-retention
- Linear flow: fetch -> update -> tag -> push OCI
- Add cleanup-all command for one-time OCI wipe"
```

---

### Task 14: Update CI Workflow

**Files:**
- Modify: `.github/workflows/version-management.yml`

**Step 1: Rewrite workflow**

```yaml
name: Version Management

on:
  push:
    branches: [main]
  schedule:
    - cron: "0 * * * *"
  workflow_dispatch:
    inputs:
      cleanup_all:
        description: "Delete ALL old OCI chart versions (one-time cleanup)"
        type: boolean
        default: false
  pull_request:
    branches: [main]

permissions:
  contents: write
  packages: write

jobs:
  validate-chart:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: DeterminateSystems/nix-installer-action@main
      - uses: DeterminateSystems/magic-nix-cache-action@main
      - name: Lint chart
        run: nix develop --command helm lint .
      - name: Validate templates (single-node)
        run: |
          nix develop --command bash -c "
            helm template zero-cache . \
              --set singleNode.enabled=true \
              --set common.database.upstream.url.value=postgres://test:test@localhost/test \
              | kubeconform -strict -summary
          "
      - name: Validate templates (multi-node)
        run: |
          nix develop --command bash -c "
            helm template zero-cache . \
              --set common.database.upstream.url.value=postgres://test:test@localhost/test \
              | kubeconform -strict -summary
          "
      - name: Run tests
        run: nix develop --command uv run pytest -v

  update-versions:
    if: github.event_name != 'pull_request' && !inputs.cleanup_all
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Set git identity
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
      - uses: DeterminateSystems/nix-installer-action@main
      - uses: DeterminateSystems/magic-nix-cache-action@main
      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ github.token }}
      - name: Update versions
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: |
          nix run .#default -- update \
            --docker-image=rocicorp/zero \
            --chart-path=Chart.yaml \
            --oci-registry=ghcr.io \
            --oci-repo=synapdeck/zero-cache-chart

  prune-oci:
    if: github.event_name != 'pull_request' && !inputs.cleanup_all
    needs: update-versions
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: DeterminateSystems/nix-installer-action@main
      - uses: DeterminateSystems/magic-nix-cache-action@main
      - name: Prune untagged OCI versions
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: |
          nix run .#default -- prune \
            --oci-repo=synapdeck/zero-cache-chart \
            --max-age-days=7

  cleanup-all-oci:
    if: github.event_name == 'workflow_dispatch' && inputs.cleanup_all
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: DeterminateSystems/nix-installer-action@main
      - uses: DeterminateSystems/magic-nix-cache-action@main
      - name: Delete all OCI versions
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: |
          nix run .#default -- cleanup-all \
            --oci-repo=synapdeck/zero-cache-chart \
            --yes
```

**Step 2: Commit**

```bash
git add .github/workflows/version-management.yml
git commit -m "ci: simplify workflow, add cleanup-all dispatch option

- Remove branch management from update-versions
- Add cleanup-all-oci job triggered by manual dispatch
- Validate both single-node and multi-node template modes"
```

---

### Task 15: Delete Old Git Branches

One-time cleanup of the abandoned version branches.

**Step 1: List and delete remote version branches**

```bash
git branch -r | grep -E 'origin/v[0-9]+\.[0-9]+$' | sed 's|origin/||' | while read branch; do
  git push origin --delete "$branch"
done
```

**Step 2: Commit is not needed** (branch deletion is a remote operation).

---

### Task 16: Final Validation and README Update

**Files:**
- Modify: `README.md`

**Step 1: Run full test suite**

Run: `pytest -v`

**Step 2: Validate all template modes**

```bash
helm template test . --set common.database.upstream.url.value="postgres://u:p@h:5432/d" --set singleNode.enabled=true > /dev/null && echo "single-node OK"
helm template test . --set common.database.upstream.url.value="postgres://u:p@h:5432/d" > /dev/null && echo "multi-node OK"
helm template test . --set common.database.upstream.url.value="postgres://u:p@h:5432/d" --set s3.enabled=true --set s3.accessKey.value=AK --set s3.secretKey.value=SK > /dev/null && echo "s3 OK"
helm template test . --set common.database.upstream.url.value="postgres://u:p@h:5432/d" --set singleNode.enabled=true --set image.tag=0.23.2025010100 --set common.api.mutateUrl=http://app/mutate | grep ZERO_PUSH_URL && echo "version-compat OK"
```

**Step 3: Update README**

Update the "Automated Version Management" section to reflect the simplified flow (no more branches, independent chart version). Update the "Configuration" table with the new `api` section and `advanced` section.

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for version-aware chart and simplified versioning"
```
