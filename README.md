# Zero-Cache Helm Chart

A Helm chart for deploying [zero-cache](https://zero.rocicorp.dev/), a horizontally scalable service that maintains a SQLite replica of your Postgres database for [Zero](https://zero.rocicorp.dev/).

## Installing the Chart

The chart is published to the GitHub Container Registry as an OCI artifact:

```bash
# Install
helm install zero-cache oci://ghcr.io/synapdeck/zero-cache-chart/zero-cache --version VERSION

# Upgrade
helm upgrade zero-cache oci://ghcr.io/synapdeck/zero-cache-chart/zero-cache --version VERSION

# Pull without installing
helm pull oci://ghcr.io/synapdeck/zero-cache-chart/zero-cache --version VERSION
```

## Architecture

The chart supports two deployment modes:

### Single-Node Mode (`singleNode.enabled: true`)

A single Deployment running both the change streamer and view syncer. Suitable for development or small workloads. Uses a standalone PVC for data persistence.

### Multi-Node Mode (default)

- **Replication Manager** — a single-replica StatefulSet that streams changes from Postgres
- **View Syncers** — a horizontally scalable StatefulSet that serves client queries (supports HPA)

View syncers wait for the replication manager to be healthy before starting.

## Version-Aware Templates

The chart uses `semverCompare` to emit the correct environment variable names based on the zero-cache version (`image.tag` or `appVersion`):

- `ZERO_MUTATE_URL` for >=0.24, `ZERO_PUSH_URL` for <0.24
- Query URL, API keys, and cookie forwarding only emitted for >=0.24

This means a single chart version works across multiple zero-cache releases.

## Configuration

See [`values.yaml`](values.yaml) for all configurable values with documentation. Key settings:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `singleNode.enabled` | Use single-node deployment mode | `false` |
| `common.database.upstream.url` | Postgres connection string (required) | `{}` |
| `common.auth.secret` / `jwk` / `jwksUrl` | JWT authentication config | `{}` |
| `common.api.mutateUrl` | Mutation handler URL | `""` |
| `common.api.queryUrl` | Query handler URL (>=0.24 only) | `""` |
| `common.advanced.lazyStartup` | Delay startup until first request | `false` |
| `common.advanced.enableQueryPlanner` | Enable ZQL query planner | `true` |
| `s3.enabled` | Enable S3-backed Litestream replication | `false` |
| `viewSyncer.replicas` | Number of view syncer replicas | `2` |
| `viewSyncer.autoscaling.enabled` | Enable HPA for view syncers | `false` |

## Automated Version Management

A GitHub Actions workflow (`version-management.yml`) monitors the `rocicorp/zero` Docker image and updates the chart automatically:

1. Fetches the latest Docker image version from Docker Hub
2. Updates `appVersion` in Chart.yaml and bumps the chart `version` patch
3. Creates release tags (e.g., `v0.26.1-canary.4`)
4. Packages and pushes the Helm chart to `ghcr.io`
5. Prunes untagged OCI artifacts to keep the registry clean

The chart version (`1.x.x`) is independent of the zero-cache appVersion — it auto-increments on each update.

The workflow runs hourly and can be manually triggered from the Actions tab. A `cleanup-all` dispatch option is available for one-time OCI registry cleanup.

## Development

### Prerequisites

- [Nix](https://nixos.org/) with flakes enabled

### Setup

```bash
# Enter the development shell (provides Python 3.13, helm, kubeconform, helm-docs, oras, uv)
nix develop

# Or with direnv
direnv allow
```

### CLI Tool

The `zero-cache-chart` CLI manages version tracking and OCI publishing:

```bash
# Update chart versions from Docker Hub
zero-cache-chart update \
  --docker-image rocicorp/zero \
  --oci-repo synapdeck/zero-cache-chart

# Prune untagged OCI artifacts
zero-cache-chart prune \
  --oci-repo synapdeck/zero-cache-chart \
  --max-age-days 7

# Delete ALL OCI versions (one-time cleanup)
zero-cache-chart cleanup-all \
  --oci-repo synapdeck/zero-cache-chart

# Dry run (no changes)
zero-cache-chart update --dry-run ...
```

### Project Structure

```
src/zero_cache_chart/
├── cli.py        # Click CLI commands (update, prune, cleanup-all)
├── chart.py      # Chart.yaml read/write
├── docker.py     # Docker Hub API client
├── git.py        # Git operations
├── oci.py        # OCI registry operations
├── types.py      # Shared types and subprocess helpers
└── versions.py   # Version parsing and classification
tests/            # pytest test suite
templates/        # Helm chart templates
```

### Running Tests

```bash
pytest
```
