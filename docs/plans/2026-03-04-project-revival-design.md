# zero-cache-chart Revival Design

## Context

This project maintains a Helm chart for [zero-cache](https://zero.rocicorp.dev/)
and automates version tracking against the upstream `rocicorp/zero` Docker image.
It has been dormant and accumulated significant technical debt:

- A 1034-line monolithic Python script (`version_manager.py`)
- 37,731 untagged OCI artifacts in GHCR
- 271 git tags with redundant branch-scoped duplicates
- Tooling split across mise (Helm), uv (Python), and raw subprocess calls
- No chart validation or linting in CI

## Design

### 1. Full Nix Flake (replacing mise + standalone uv)

Replace `mise.toml` and `.python-version` with a single `flake.nix` using uv2nix
to build the Python environment from the existing `pyproject.toml` + `uv.lock`.

**Dev shell provides:**
- Python 3.12 + all project dependencies (via uv2nix)
- Helm
- kubeconform (template validation)
- helm-docs (documentation generation)
- oras (OCI tag manipulation)

**Nix packages exposed:**
- `packages.default` — the version manager CLI as a runnable Nix package

**Files removed:** `mise.toml`, `.python-version`

**CI setup:** `DeterminateSystems/nix-installer-action` + `DeterminateSystems/magic-nix-cache-action`
for fast cached Nix in GitHub Actions.

### 2. Python Package Restructure

Replace the `version_manager.py` monolith with a proper package:

```
src/zero_cache_chart/
  __init__.py
  cli.py          # click entrypoint, argument parsing
  docker.py       # Docker Hub API querying, version fetching
  git.py          # Git operations (branches, tags, checkout, push)
  chart.py        # Chart.yaml reading/writing, helm packaging
  oci.py          # OCI registry push, tagging (via oras), pruning
  versions.py     # Version comparison, branch retention policy
```

**Key changes:**
- Replace `fire` with `click` for explicit CLI with proper `--help`
- Replace `subprocess.run(cmd, shell=True)` with `subprocess.run([...], shell=False)` —
  no shell injection risk
- Replace the `Dict[str, Any]` results bag with a dataclass
- Replace the `run_command` helper (which silently returns stderr on failure) with a
  typed wrapper that raises on failure
- Branch retention: only update last 3 major.minor branches, skip older ones

### 3. OCI Registry Cleanup

**Root cause fix:** Check if a version exists in the registry *before* pushing.
Skip entirely if it already exists. The current approach pushes first and checks
for "already exists" in the output string, which creates untagged manifests on
partial failures.

**Ongoing pruning:** A `prune` CLI command that uses the GitHub Packages API to:
1. List all versions of the package
2. Delete any untagged version older than a configurable threshold (default: 7 days)

Runs as a CI step after version management.

**One-time cleanup:** Same `prune` command with `--all` flag to delete all untagged
versions regardless of age (for the initial 37K cleanup).

### 4. Tagging Strategy

**Git tags — per-release (immutable):**
- `v0.26.1-canary.4` — created once per version, never moved
- Only for the latest version detected on each run (not retroactive)

**Git tags — branch pointers (force-updated):**
- `v0.26` — latest stable release in 0.26.x
- `v0.26-canary` — latest canary/prerelease in 0.26.x

**OCI tags — per-version:**
- `0.26.1-canary.4` — created by `helm push` from Chart.yaml version

**OCI tags — pointers (via `oras tag`):**
- `0.26` — latest stable 0.26.x chart
- `0.26-canary` — latest canary in 0.26.x

**Existing 271 git tags:** Left in place. Stop creating `v0.26/0.26.1-canary.4`
style duplicates going forward.

### 5. CI Workflow

Single workflow file, three jobs:

**`update-versions`** (hourly + push to main + manual):
- `nix run .#version-manager` to poll Docker Hub, update main + last 3 branches,
  create tags, push OCI packages, apply `oras tag` pointers
- Permissions: `contents: write`, `packages: write`

**`prune-oci`** (after `update-versions`):
- Runs `prune` command to delete untagged versions older than 7 days
- Permissions: `packages: write`

**`validate-chart`** (on PRs):
- `helm lint .`
- `kubeconform` against rendered templates
- Lightweight sanity check for manual chart changes

### 6. Helm Chart Template Audit

Full red-ink review of all templates covering:
- Deployment logic and failure modes
- StatefulSet topology and coordination between replication manager / view syncers
- Litestream backup strategy correctness
- Probe configuration and startup behavior
- Security contexts and pod security standards
- Service configuration and session affinity
- Standard Kubernetes labels (`app.kubernetes.io/*`)
- Deprecated API versions or Helm idioms
- Hardcoded values that should be configurable
- Resource defaults

Findings will be presented for review before changes are made. Behavioral changes
require explicit approval.
