# Zero-Cache

A Helm chart for deploying zero-cache, a horizontally scalable service that maintains a SQLite replica of your Postgres database for Zero.

## Version Management

This repository uses an automated GitHub Actions workflow to manage Docker image versions. Here's how it works:

### Automated Version Management

The system monitors the `rocicorp/zero` Docker image for new versions and updates the Helm chart accordingly:

1. **Main Branch Updates**:

   - When a new version of the Docker image is released, changes are committed directly to the main branch
   - This ensures the main branch always points to the latest version
   - A version tag (e.g., `v0.20.2025051800`) is created for each update

2. **Version Branch Management**:
   - For each major.minor version (e.g., `v0.20`), a dedicated branch is maintained
   - When a new version is released with a new major.minor (e.g., `0.21.yyyymmddxx`), a new branch `v0.21` is automatically created
   - Each version branch only receives updates to its specific major.minor version
   - Branch-specific version tags (e.g., `v0.20/0.20.2025051800`) are created for each update

### How It Works

The system runs on a schedule (every hour) and:

1. Fetches all available Docker image versions
2. Updates the main branch with the latest version via direct commit
3. Updates both the `appVersion` and chart `version` in Chart.yaml
4. Creates a version tag for each update
5. Packages and pushes the Helm chart to the GitHub Container Registry (ghcr.io)
6. Creates new version branches for new major.minor versions
7. Updates existing version branches with the latest build for their specific major.minor version

This approach ensures that:

- The main branch always gets the latest version
- Version tags provide an easy way to reference specific versions
- Helm charts are published to the OCI registry (ghcr.io) for easy consumption
- Chart version always matches the Docker image version for consistency
- A new version branch is created for each new major.minor version
- Existing version branches only receive build/date updates to their specific major.minor version
- Consumers can easily select specific versions from the OCI registry

## Manual Triggering

You can manually trigger the version check by going to the Actions tab and running the "Docker Image Version Management" workflow.

## Configuration

The workflow is defined in `.github/workflows/version-management.yml` and monitors the Docker image specified in the workflow configuration.

## Using the Helm Chart from OCI Registry

The Helm chart is published to the GitHub Container Registry (ghcr.io) as an OCI artifact and can be used directly with Helm:

```bash
# Pull a specific chart version
helm pull oci://ghcr.io/synapdeck/zero-cache-chart/zero-cache --version VERSION

# Install the chart
helm install zero-cache oci://ghcr.io/synapdeck/zero-cache-chart/zero-cache --version VERSION

# Upgrade an existing installation
helm upgrade zero-cache oci://ghcr.io/synapdeck/zero-cache-chart/zero-cache --version VERSION
```

Replace:

- `VERSION` with the desired chart version

### Available Versions

The OCI registry maintains multiple versions of the chart:

- Latest version from the `main` branch
- Specific versions tagged with the appVersion (e.g., `0.20.2025051800`)
- Branch-specific versions for each major.minor version (e.g., `v0.20/0.20.2025051800`)

### Viewing Available Charts

To view available chart versions:

```bash
# List all versions of the chart
helm search repo oci://ghcr.io/synapdeck/zero-cache-chart/zero-cache --versions
```
