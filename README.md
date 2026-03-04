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

## Configuration

See [`values.yaml`](values.yaml) for all configurable values with documentation. Key settings:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `singleNode.enabled` | Use single-node deployment mode | `false` |
| `common.database.upstream.url` | Postgres connection string (required) | `{}` |
| `common.auth.secret` / `jwk` / `jwksUrl` | JWT authentication config | `{}` |
| `s3.enabled` | Enable S3-backed Litestream replication | `false` |
| `viewSyncer.replicas` | Number of view syncer replicas | `2` |
| `viewSyncer.autoscaling.enabled` | Enable HPA for view syncers | `false` |

## Automated Version Management

A GitHub Actions workflow (`version-management.yml`) monitors the `rocicorp/zero` Docker image and updates the chart automatically:

1. Fetches all available Docker image versions from Docker Hub
2. Updates Chart.yaml `appVersion` and `version` on the main branch
3. Creates version tags (e.g., `v0.26.1-canary.4`)
4. Maintains major.minor branches (e.g., `v0.26`) with branch-specific tags
5. Packages and pushes the Helm chart to `ghcr.io`
6. Prunes untagged OCI artifacts to keep the registry clean

The workflow runs hourly and can be manually triggered from the Actions tab.

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
  --oci-registry ghcr.io \
  --oci-repo synapdeck/zero-cache-chart/zero-cache

# Prune untagged OCI artifacts
zero-cache-chart prune \
  --github-repo synapdeck/zero-cache-chart \
  --package-name zero-cache-chart/zero-cache

# Dry run (no changes)
zero-cache-chart update --dry-run ...
```

### Project Structure

```
src/zero_cache_chart/
├── cli.py        # Click CLI commands (update, prune)
├── chart.py      # Chart.yaml read/write
├── docker.py     # Docker Hub API client
├── git.py        # Git operations
├── oci.py        # OCI registry operations
├── types.py      # Shared types and subprocess helpers
└── versions.py   # Version parsing, comparison, branch logic
tests/            # pytest test suite
templates/        # Helm chart templates
```

### Running Tests

```bash
pytest
```
