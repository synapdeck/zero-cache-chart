# Version-Aware Helm Chart Design

## Context

The zero-cache Helm chart currently maintains per-major.minor git branches (v0.20, v0.21, etc.) with floating pointer tags, publishing separate chart versions for each branch. This is complex, fragile, and the published charts for older versions are broken. Meanwhile, zero-cache has had breaking env var changes across versions (PUSH_URL renamed to MUTATE_URL in 0.24, AUTH_* deprecated in 0.25, TARGET_CLIENT_ROW_COUNT deprecated in 0.22, plus many new vars we don't template at all).

This redesign replaces the branching system with version-aware Helm templates. A single chart supports zero-cache 0.22+ by emitting the correct env vars based on the detected version. The CLI simplifies to a linear "watch Docker Hub, update main, push OCI" flow.

## Minimum Supported Version

**0.22+** (Node 22 era). This covers the PUSH_URL->MUTATE_URL rename at 0.24 and auth deprecation at 0.25.

## Version Detection

A `zero-cache.zeroVersion` helper extracts major.minor from `image.tag` (falling back to `appVersion`) and returns `X.Y.0`:

```yaml
{{- define "zero-cache.zeroVersion" -}}
{{- $raw := .Values.image.tag | default .Chart.AppVersion | toString -}}
{{- $parts := splitList "." $raw -}}
{{- printf "%s.%s.0" (index $parts 0) (index $parts 1) -}}
{{- end -}}
```

Templates use `semverCompare` against this value to gate version-specific behavior.

## Named Env Block Templates

Environment variables move from inline duplication across 3 workload templates into logical named templates in `_helpers.tpl`:

| Template | Vars | Version-conditional? |
|----------|------|---------------------|
| `zero-cache.env.core` | PORT, APP_ID, APP_PUBLICATIONS, REPLICA_FILE, AUTO_RESET, TASK_ID, SERVER_VERSION | No |
| `zero-cache.env.database` | UPSTREAM_DB, CVR_DB, CHANGE_DB, all MAX_CONNS, CVR GC vars | No |
| `zero-cache.env.auth` | AUTH_SECRET, AUTH_JWK, AUTH_JWKS_URL | Yes (deprecated >=0.25, still rendered) |
| `zero-cache.env.admin` | ADMIN_PASSWORD | No |
| `zero-cache.env.mutators` | MUTATE_URL/PUSH_URL, QUERY_URL, API keys, FORWARD_COOKIES | Yes (PUSH_URL <0.24, MUTATE_URL >=0.24; QUERY_URL/keys >=0.24 only) |
| `zero-cache.env.litestream` | BACKUP_URL, CONFIG_PATH, checkpoint/interval/restore/multipart vars | No |
| `zero-cache.env.s3` | AWS_ACCESS_KEY_ID, SECRET_ACCESS_KEY, REGION, ENDPOINT_URL | No |
| `zero-cache.env.performance` | INITIAL_SYNC_TABLE_COPY_WORKERS, YIELD_THRESHOLD_MS, REPLICA_VACUUM_INTERVAL_HOURS, REPLICA_PAGE_CACHE_SIZE_KIB, NUM_SYNC_WORKERS, ENABLE_QUERY_PLANNER | No |
| `zero-cache.env.logging` | LOG_FORMAT, LOG_LEVEL, slow thresholds, IVM_SAMPLING, OTEL_* | No |
| `zero-cache.env.ratelimit` | PER_USER_MUTATION_LIMIT_MAX, WINDOW_MS | No |
| `zero-cache.env.advanced` | LAZY_STARTUP, WEBSOCKET_COMPRESSION, WEBSOCKET_COMPRESSION_OPTIONS, ENABLE_TELEMETRY, STORAGE_DB_TMP_DIR | No |

Workload templates include these blocks and add only their unique vars inline (CHANGE_STREAMER_MODE, LITESTREAM_BACKUP_URL on repl-mgr only, etc.).

## values.yaml Changes

### Renamed/restructured

`common.customMutators.pushUrl` replaced by:

```yaml
common:
  api:
    mutateUrl: ""
    queryUrl: ""
    mutateApiKey: {}      # value/valueFrom pattern
    queryApiKey: {}        # value/valueFrom pattern
    mutateForwardCookies: false
    queryForwardCookies: false
```

`common.api.mutateUrl` emits `ZERO_PUSH_URL` for <0.24 and `ZERO_MUTATE_URL` for >=0.24.

### Removed

- `common.performance.targetClientRowCount` (deprecated since 0.22, our minimum)

### New sections

```yaml
common:
  advanced:
    lazyStartup: false
    enableTelemetry: true
    enableQueryPlanner: true
    yieldThresholdMs: 10
    replicaPageCacheSizeKib: null
    storageTmpDir: ""
    websocketCompression: false
    websocketCompressionOptions: ""

  database:
    cvr:
      garbageCollection:
        inactivityThresholdHours: 48
        initialBatchSize: 25
        initialIntervalSeconds: 60

  litestream:
    # existing vars plus:
    multipartConcurrency: 48
    multipartSize: 16777216
```

## Chart Versioning

Chart version becomes independent of appVersion. Starting at `1.0.0`. When the CLI detects a new upstream appVersion, it updates `appVersion` in Chart.yaml and bumps the chart patch version (e.g., 1.0.0 -> 1.0.1). Major/minor chart bumps are manual for chart-breaking changes.

## CLI Simplification

### `update` command (simplified)

Linear flow:
1. Fetch Docker Hub versions
2. Find latest version
3. If newer than Chart.yaml: update `appVersion`, bump chart patch version
4. Commit, create git tag (`v{appVersion}`), push to main
5. Package chart, push to OCI registry

### Removed from CLI

- `select_retained_branches()` from versions.py
- `branch_pointer_tags()` from versions.py
- `list_version_branches()` from git.py
- `_update_branch()` from cli.py
- Branch creation/update loop
- Floating pointer tags
- `--branch-retention` option

### New: `cleanup-all` command

One-time operation to delete all existing OCI chart versions from ghcr.io (they're broken and abandoned). Lists all package versions via GitHub API and deletes them. After this, the new `update` flow pushes fresh 1.x versions.

## CI Workflow

### `update-versions` job (hourly + manual)

Simplified to: check Docker Hub -> update main -> tag -> push OCI. No branch management.

### `validate-chart` job (on PRs)

- `helm template` with various value combinations
- `kubeconform` validation
- `pytest` for CLI

### `cleanup-oci` job (one-time manual dispatch)

Wipes all old OCI versions. After that, the existing `prune` handles untagged artifacts on schedule.

## Version-Conditional Behavior Summary

| Feature | <0.24 | >=0.24 |
|---------|-------|--------|
| Custom mutator env var name | ZERO_PUSH_URL | ZERO_MUTATE_URL |
| ZERO_QUERY_URL | not emitted | emitted if set |
| ZERO_*_API_KEY | not emitted | emitted if set |
| ZERO_*_FORWARD_COOKIES | not emitted | emitted if set |

Auth vars (ZERO_AUTH_SECRET, JWK, JWKS_URL) are deprecated >=0.25 but still functional. They are always rendered when configured regardless of version.
