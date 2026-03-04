# zero-cache-chart Revival Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Revive the zero-cache Helm chart project: replace mise with a full Nix flake (uv2nix), restructure the monolithic version manager into a proper Python package with click, fix OCI artifact pollution, rationalize tagging, update CI, and do a deep audit of the Helm templates.

**Architecture:** Full Nix flake using uv2nix for Python dependency management. Python package at `src/zero_cache_chart/` with click CLI. CI runs via `nix run`. OCI tagging via oras. Branch retention limited to last 3 major.minor versions.

**Tech Stack:** Nix (uv2nix), Python 3.12, click, semver, requests, pyyaml, Helm, kubeconform, oras, GitHub Actions

---

### Task 1: Nix Flake Foundation

**Files:**
- Create: `flake.nix`
- Create: `flake.lock` (generated)
- Create: `.envrc`
- Delete: `mise.toml`
- Delete: `.python-version`
- Modify: `.helmignore` — add Nix artifacts, remove mise references
- Modify: `.gitignore` — add `.direnv/`

**Step 1: Create flake.nix with uv2nix**

The flake should:
- Use uv2nix to build the Python environment from `pyproject.toml` + `uv.lock`
- Provide a devShell with: Python + deps, helm, kubeconform, helm-docs, oras
- Expose `packages.default` as the version-manager CLI (the `zero-cache-chart` console script)
- Pin nixpkgs to a recent stable release

Reference for uv2nix setup: https://github.com/pyproject-nix/uv2nix

```nix
{
  description = "zero-cache Helm chart version manager";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/pyproject-build-systems";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, pyproject-nix, uv2nix, pyproject-build-systems, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        workspace = uv2nix.lib.workspace.loadWorkspace {
          workspaceRoot = ./.;
        };

        overlay = workspace.mkPyprojectOverlay {
          sourcePreference = "wheel";
        };

        pythonSet =
          (pkgs.callPackage pyproject-nix.build.packages {
            python = pkgs.python312;
          }).overrideScope (
            nixpkgs.lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              overlay
            ]
          );

        venv = pythonSet.mkVirtualEnv "zero-cache-chart-env" workspace.deps.default;
      in
      {
        packages.default = venv;

        devShells.default = pkgs.mkShell {
          packages = [
            venv
            pkgs.kubernetes-helm
            pkgs.kubeconform
            pkgs.helm-docs
            pkgs.oras
            pkgs.uv
          ];
        };
      }
    );
}
```

This is a starting point — will need adjustment based on actual uv2nix API at build time.

**Step 2: Create .envrc for direnv**

```bash
use flake
```

**Step 3: Remove mise.toml and .python-version**

These are replaced by the Nix flake.

**Step 4: Update .helmignore**

Add:
```
flake.nix
flake.lock
.envrc
.direnv/
result
```

Remove references to `mise.toml`.

**Step 5: Test**

```bash
nix develop --command bash -c "helm version && python --version && kubeconform -v && oras version"
```

Expected: all four commands succeed with version output.

**Step 6: Commit**

```bash
git add flake.nix .envrc .helmignore
git rm mise.toml .python-version
git commit -m "build: replace mise with Nix flake using uv2nix"
```

---

### Task 2: Python Package Scaffold

**Files:**
- Create: `src/zero_cache_chart/__init__.py`
- Create: `src/zero_cache_chart/cli.py`
- Create: `src/zero_cache_chart/types.py`
- Modify: `pyproject.toml` — add `[project.scripts]`, replace fire with click
- Modify: `uv.lock` — regenerate

**Step 1: Update pyproject.toml**

Replace `fire` with `click` in dependencies. Add console script entrypoint.
Add `[build-system]` and `[project.scripts]` sections:

```toml
[project]
name = "zero-cache-chart"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
    "click>=8.1.0",
    "pyyaml>=6.0.2",
    "requests>=2.32.3",
    "semver>=3.0.4",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-mock>=3.14.0",
    "responses>=0.25.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/zero_cache_chart"]

[project.scripts]
zero-cache-chart = "zero_cache_chart.cli:main"
```

**Step 2: Create types.py**

Shared types and the subprocess wrapper:

```python
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


class CommandError(Exception):
    def __init__(self, cmd: list[str], result: CommandResult):
        self.cmd = cmd
        self.result = result
        super().__init__(
            f"Command {' '.join(cmd)} failed with exit code {result.returncode}: {result.stderr}"
        )


def run(cmd: list[str], *, check: bool = True) -> CommandResult:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    result = CommandResult(
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        returncode=proc.returncode,
    )
    if check and result.returncode != 0:
        raise CommandError(cmd, result)
    return result


@dataclass
class VersionManagementResult:
    main_updated: bool = False
    new_branch_created: str | None = None
    updated_branches: list[str] = field(default_factory=list)
    created_tags: list[str] = field(default_factory=list)
    pushed_oci_packages: list[str] = field(default_factory=list)
    pruned_oci_versions: int = 0
    current_version: str | None = None
```

**Step 3: Create cli.py skeleton**

```python
import click


@click.group()
def main() -> None:
    """zero-cache Helm chart version manager."""


@main.command()
@click.option("--docker-image", required=True, help="Docker image to track (e.g. rocicorp/zero)")
@click.option("--chart-path", default="Chart.yaml", help="Path to Chart.yaml")
@click.option("--oci-registry", default="ghcr.io", help="OCI registry URL")
@click.option("--oci-repo", required=True, help="OCI repository path")
@click.option("--branch-retention", default=3, help="Number of major.minor branches to maintain")
@click.option("--dry-run", is_flag=True, help="Simulate without making changes")
def update(
    docker_image: str,
    chart_path: str,
    oci_registry: str,
    oci_repo: str,
    branch_retention: int,
    dry_run: bool,
) -> None:
    """Poll Docker Hub and update chart versions."""
    click.echo("Not yet implemented")


@main.command()
@click.option("--oci-registry", default="ghcr.io")
@click.option("--oci-repo", required=True)
@click.option("--max-age-days", default=7, help="Delete untagged versions older than N days")
@click.option("--all", "prune_all", is_flag=True, help="Delete ALL untagged versions regardless of age")
@click.option("--dry-run", is_flag=True)
def prune(
    oci_registry: str,
    oci_repo: str,
    max_age_days: int,
    prune_all: bool,
    dry_run: bool,
) -> None:
    """Prune untagged OCI versions from the registry."""
    click.echo("Not yet implemented")
```

**Step 4: Create __init__.py**

Empty file.

**Step 5: Regenerate uv.lock**

```bash
uv lock
```

**Step 6: Test the scaffold**

```bash
uv run zero-cache-chart --help
uv run zero-cache-chart update --help
uv run zero-cache-chart prune --help
```

Expected: help text renders for all three commands.

**Step 7: Commit**

```bash
git add src/ pyproject.toml uv.lock
git commit -m "refactor: scaffold Python package with click CLI"
```

---

### Task 3: Implement versions.py (Pure Logic)

This is the most testable module — pure functions, no side effects.

**Files:**
- Create: `src/zero_cache_chart/versions.py`
- Create: `tests/test_versions.py`

**Step 1: Write tests for version logic**

```python
import pytest
from semver.version import Version
from zero_cache_chart.versions import (
    build_version_map,
    get_latest_version,
    is_stable,
    select_retained_branches,
    classify_version_tag,
)


def v(s: str) -> Version:
    return Version.parse(s)


class TestIsStable:
    def test_stable(self):
        assert is_stable(v("0.26.0")) is True

    def test_canary(self):
        assert is_stable(v("0.26.0-canary.4")) is False

    def test_prerelease(self):
        assert is_stable(v("1.0.0-rc.1")) is False


class TestBuildVersionMap:
    def test_groups_by_major_minor(self):
        versions = [v("0.25.0"), v("0.25.1"), v("0.26.0")]
        vmap = build_version_map(versions)
        assert str(vmap["0.25"]) == "0.25.1"
        assert str(vmap["0.26"]) == "0.26.0"

    def test_empty(self):
        assert build_version_map([]) == {}


class TestGetLatestVersion:
    def test_returns_highest(self):
        versions = [v("0.25.0"), v("0.26.0"), v("0.26.1-canary.4")]
        assert get_latest_version(versions) == v("0.26.1-canary.4")

    def test_empty_returns_none(self):
        assert get_latest_version([]) is None


class TestSelectRetainedBranches:
    def test_retains_last_n(self):
        branches = ["v0.19", "v0.20", "v0.21", "v0.22", "v0.23", "v0.24", "v0.25", "v0.26"]
        retained = select_retained_branches(branches, retain=3)
        assert retained == ["v0.24", "v0.25", "v0.26"]

    def test_fewer_than_n(self):
        branches = ["v0.25", "v0.26"]
        retained = select_retained_branches(branches, retain=3)
        assert retained == ["v0.25", "v0.26"]

    def test_sorts_numerically(self):
        branches = ["v0.9", "v0.20", "v0.10"]
        retained = select_retained_branches(branches, retain=2)
        assert retained == ["v0.10", "v0.20"]


class TestClassifyVersionTag:
    def test_stable(self):
        name, kind = classify_version_tag(v("0.26.0"))
        assert name == "v0.26.0"
        assert kind == "stable"

    def test_canary(self):
        name, kind = classify_version_tag(v("0.26.0-canary.4"))
        assert name == "v0.26.0-canary.4"
        assert kind == "prerelease"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_versions.py -v
```

Expected: ImportError — module doesn't exist yet.

**Step 3: Implement versions.py**

```python
from __future__ import annotations

import re
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


def select_retained_branches(branches: list[str], *, retain: int) -> list[str]:
    def sort_key(branch: str) -> tuple[int, int]:
        match = re.search(r"v(\d+)\.(\d+)", branch)
        if not match:
            return (0, 0)
        return (int(match.group(1)), int(match.group(2)))

    return sorted(branches, key=sort_key)[-retain:]


def classify_version_tag(version: Version) -> tuple[str, str]:
    tag_name = f"v{version}"
    kind = "prerelease" if version.prerelease else "stable"
    return tag_name, kind


def branch_pointer_tags(version: Version) -> list[str]:
    """Return the branch pointer tag names that should point to this version.

    For stable: ["v{major}.{minor}"]
    For prerelease: ["v{major}.{minor}-canary"] (or whatever the prerelease prefix is)
    """
    mm = f"v{version.major}.{version.minor}"
    if is_stable(version):
        return [mm]
    else:
        return [f"{mm}-canary"]
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_versions.py -v
```

Expected: all pass.

**Step 5: Commit**

```bash
git add src/zero_cache_chart/versions.py tests/test_versions.py
git commit -m "feat: add version logic module with tests"
```

---

### Task 4: Implement docker.py

**Files:**
- Create: `src/zero_cache_chart/docker.py`
- Create: `tests/test_docker.py`

**Step 1: Write tests with mocked HTTP**

Use the `responses` library to mock Docker Hub API calls.

```python
import responses
from semver.version import Version
from zero_cache_chart.docker import fetch_docker_versions


@responses.activate
def test_fetch_docker_versions_basic():
    responses.add(
        responses.GET,
        "https://hub.docker.com/v2/repositories/rocicorp/zero/tags/",
        json={
            "count": 3,
            "next": None,
            "results": [
                {"name": "0.25.0"},
                {"name": "0.26.0"},
                {"name": "latest"},  # should be filtered out
                {"name": "0.26.1-canary.4"},
            ],
        },
    )

    versions = fetch_docker_versions("rocicorp/zero")
    assert versions == [
        Version.parse("0.25.0"),
        Version.parse("0.26.0"),
        Version.parse("0.26.1-canary.4"),
    ]


@responses.activate
def test_fetch_docker_versions_pagination():
    responses.add(
        responses.GET,
        "https://hub.docker.com/v2/repositories/rocicorp/zero/tags/",
        json={
            "count": 2,
            "next": "https://hub.docker.com/v2/repositories/rocicorp/zero/tags/?page=2",
            "results": [{"name": "0.25.0"}],
        },
    )
    responses.add(
        responses.GET,
        "https://hub.docker.com/v2/repositories/rocicorp/zero/tags/?page=2",
        json={
            "count": 2,
            "next": None,
            "results": [{"name": "0.26.0"}],
        },
    )

    versions = fetch_docker_versions("rocicorp/zero")
    assert versions == [Version.parse("0.25.0"), Version.parse("0.26.0")]
```

**Step 2: Run tests to verify failure**

```bash
uv run pytest tests/test_docker.py -v
```

**Step 3: Implement docker.py**

Key improvement over current code: **paginate through all results** (current code only fetches page_size=100, which may miss versions).

```python
from __future__ import annotations

import requests
from semver.version import Version


def fetch_docker_versions(docker_image: str) -> list[Version]:
    url: str | None = (
        f"https://hub.docker.com/v2/repositories/{docker_image}/tags/?page_size=100"
    )
    versions: list[Version] = []

    while url:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for tag in data.get("results", []):
            name = tag.get("name", "")
            if Version.is_valid(name):
                versions.append(Version.parse(name))

        url = data.get("next")

    versions.sort()
    return versions
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_docker.py -v
```

**Step 5: Commit**

```bash
git add src/zero_cache_chart/docker.py tests/test_docker.py
git commit -m "feat: add Docker Hub version fetching with pagination"
```

---

### Task 5: Implement chart.py

**Files:**
- Create: `src/zero_cache_chart/chart.py`
- Create: `tests/test_chart.py`

**Step 1: Write tests**

```python
from pathlib import Path
from semver.version import Version
from zero_cache_chart.chart import read_chart_version, write_chart_version


def test_read_chart_version(tmp_path: Path):
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.26.1-canary.4\nversion: 0.26.1-canary.4\n")
    ver = read_chart_version(chart)
    assert ver == Version.parse("0.26.1-canary.4")


def test_read_chart_version_invalid(tmp_path: Path):
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: latest\nversion: latest\n")
    ver = read_chart_version(chart)
    assert ver is None


def test_write_chart_version(tmp_path: Path):
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.25.0\nversion: 0.25.0\nname: zero-cache\n")
    write_chart_version(chart, Version.parse("0.26.0"))
    ver = read_chart_version(chart)
    assert ver == Version.parse("0.26.0")
```

**Step 2: Implement chart.py**

Key improvement: preserve YAML formatting. The current code uses `yaml.dump` which
reorders keys and destroys comments. Use simple string replacement or `ruamel.yaml`
if needed, but start simple — read with `yaml.safe_load`, write with `yaml.dump`,
accept that key order may change. If this proves problematic with git diffs, switch
to regex-based replacement of just the version fields.

```python
from __future__ import annotations

from pathlib import Path
import yaml
from semver.version import Version


def read_chart_version(chart_path: Path) -> Version | None:
    data = yaml.safe_load(chart_path.read_text())
    version_str = str(data.get("appVersion", "")).strip().strip('"')
    if Version.is_valid(version_str):
        return Version.parse(version_str)
    return None


def write_chart_version(chart_path: Path, version: Version) -> None:
    text = chart_path.read_text()
    data = yaml.safe_load(text)
    data["appVersion"] = str(version)
    data["version"] = str(version)
    chart_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
```

**Step 3: Run tests, commit**

```bash
uv run pytest tests/test_chart.py -v
git add src/zero_cache_chart/chart.py tests/test_chart.py
git commit -m "feat: add Chart.yaml read/write module"
```

---

### Task 6: Implement git.py

**Files:**
- Create: `src/zero_cache_chart/git.py`
- Create: `tests/test_git.py`

**Step 1: Write tests**

Git operations are side-effectful, so tests use `tmp_path` with real git repos:

```python
import subprocess
from pathlib import Path
from zero_cache_chart.git import (
    Git,
    list_version_branches,
    parse_major_minor,
)


def test_parse_major_minor():
    assert parse_major_minor("v0.26") == (0, 26)
    assert parse_major_minor("v1.3") == (1, 3)
    assert parse_major_minor("not-a-branch") is None


def init_repo(path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("test")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    return path


def test_git_current_branch(tmp_path: Path):
    repo = init_repo(tmp_path)
    git = Git(cwd=repo)
    # Default branch could be main or master depending on git config
    branch = git.current_branch()
    assert branch in ("main", "master")


def test_git_create_tag(tmp_path: Path):
    repo = init_repo(tmp_path)
    git = Git(cwd=repo)
    git.create_tag("v0.1.0")
    result = subprocess.run(["git", "tag", "-l"], cwd=repo, capture_output=True, text=True)
    assert "v0.1.0" in result.stdout


def test_git_force_tag(tmp_path: Path):
    repo = init_repo(tmp_path)
    git = Git(cwd=repo)
    git.create_tag("v0.1.0")
    # Force-update should not raise
    git.create_tag("v0.1.0", force=True)
```

**Step 2: Implement git.py**

```python
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from zero_cache_chart.types import CommandResult, CommandError, run


def parse_major_minor(branch: str) -> tuple[int, int] | None:
    match = re.search(r"v(\d+)\.(\d+)", branch)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)))


class Git:
    def __init__(self, cwd: Path | None = None):
        self.cwd = cwd

    def _run(self, *args: str, check: bool = True) -> CommandResult:
        cmd = ["git", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=self.cwd)
        result = CommandResult(
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
            returncode=proc.returncode,
        )
        if check and result.returncode != 0:
            raise CommandError(cmd, result)
        return result

    def current_branch(self) -> str:
        return self._run("branch", "--show-current").stdout

    def checkout(self, branch: str) -> None:
        self._run("checkout", branch)

    def checkout_new(self, branch: str) -> None:
        self._run("checkout", "-b", branch)

    def fetch(self) -> None:
        self._run("fetch", "origin")

    def pull(self, branch: str) -> None:
        self._run("pull", "origin", branch)

    def push(self, branch: str) -> None:
        self._run("push", "origin", branch)

    def add(self, *paths: str) -> None:
        self._run("add", *paths)

    def commit(self, message: str) -> None:
        self._run("commit", "-m", message)

    def create_tag(self, name: str, *, force: bool = False) -> None:
        args = ["tag"]
        if force:
            args.append("-f")
        args.append(name)
        self._run(*args)

    def push_tag(self, name: str, *, force: bool = False) -> None:
        args = ["push"]
        if force:
            args.append("-f")
        args.extend(["origin", name])
        self._run(*args)

    def tag_exists(self, name: str) -> bool:
        result = self._run("tag", "-l", name)
        return name in result.stdout.split("\n")

    def list_remote_branches(self) -> list[str]:
        result = self._run("branch", "-r")
        return [
            b.strip().removeprefix("origin/")
            for b in result.stdout.split("\n")
            if b.strip() and "HEAD" not in b
        ]


def list_version_branches(git: Git) -> list[str]:
    branches = git.list_remote_branches()
    return [b for b in branches if re.match(r"v\d+\.\d+$", b)]
```

**Step 3: Run tests, commit**

```bash
uv run pytest tests/test_git.py -v
git add src/zero_cache_chart/git.py tests/test_git.py
git commit -m "feat: add typed Git operations wrapper"
```

---

### Task 7: Implement oci.py

**Files:**
- Create: `src/zero_cache_chart/oci.py`
- Create: `tests/test_oci.py`

**Step 1: Write tests**

OCI operations shell out to `helm` and `oras`, so tests focus on the logic
around them (version existence check, pruning API calls) with mocking.

```python
import responses
from zero_cache_chart.oci import _parse_package_versions


@responses.activate
def test_parse_package_versions():
    # Test the parsing logic used by the prune command
    data = [
        {"id": 1, "metadata": {"container": {"tags": ["0.26.0"]}}, "created_at": "2026-01-01T00:00:00Z"},
        {"id": 2, "metadata": {"container": {"tags": []}}, "created_at": "2026-01-01T00:00:00Z"},
        {"id": 3, "metadata": {"container": {"tags": []}}, "created_at": "2025-01-01T00:00:00Z"},
    ]
    tagged, untagged = _parse_package_versions(data)
    assert len(tagged) == 1
    assert len(untagged) == 2
```

**Step 2: Implement oci.py**

```python
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from semver.version import Version

from zero_cache_chart.types import run


def version_exists_in_registry(registry: str, repo: str, version: str) -> bool:
    """Check if a chart version already exists in the OCI registry."""
    result = run(
        ["oras", "manifest", "fetch", f"{registry}/{repo}/zero-cache:{version}"],
        check=False,
    )
    return result.returncode == 0


def package_chart(chart_dir: Path = Path(".")) -> Path:
    result = run(["helm", "package", str(chart_dir)])
    # helm package outputs "Successfully packaged chart and saved it to: /path/to/chart.tgz"
    for line in result.stdout.split("\n"):
        if line.endswith(".tgz"):
            return Path(line.split(": ")[-1])
    raise RuntimeError(f"Failed to find packaged chart in output: {result.stdout}")


def push_chart(package_path: Path, registry: str, repo: str) -> None:
    run(["helm", "push", str(package_path), f"oci://{registry}/{repo}"])


def tag_version(registry: str, repo: str, source_tag: str, target_tag: str) -> None:
    run([
        "oras", "tag",
        f"{registry}/{repo}/zero-cache:{source_tag}",
        target_tag,
    ])


def push_if_not_exists(
    registry: str,
    repo: str,
    version: str,
    chart_dir: Path = Path("."),
) -> bool:
    if version_exists_in_registry(registry, repo, version):
        return False
    package_path = package_chart(chart_dir)
    try:
        push_chart(package_path, registry, repo)
        return True
    finally:
        package_path.unlink(missing_ok=True)


PackageVersion = dict  # from GitHub API


def _parse_package_versions(
    versions: list[PackageVersion],
) -> tuple[list[PackageVersion], list[PackageVersion]]:
    tagged = [v for v in versions if v["metadata"]["container"]["tags"]]
    untagged = [v for v in versions if not v["metadata"]["container"]["tags"]]
    return tagged, untagged


def list_package_versions(org: str, package_name: str) -> list[PackageVersion]:
    """List all versions of a container package using GitHub API."""
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    url: str | None = (
        f"https://api.github.com/orgs/{org}/packages/container/{package_name}/versions"
        f"?per_page=100"
    )
    all_versions: list[PackageVersion] = []

    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        all_versions.extend(resp.json())

        # Follow Link header for pagination
        link = resp.headers.get("Link", "")
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")

    return all_versions


def delete_package_version(org: str, package_name: str, version_id: int) -> None:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    resp = requests.delete(
        f"https://api.github.com/orgs/{org}/packages/container/{package_name}/versions/{version_id}",
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()


def prune_untagged(
    org: str,
    package_name: str,
    *,
    max_age_days: int = 7,
    prune_all: bool = False,
    dry_run: bool = False,
) -> int:
    versions = list_package_versions(org, package_name)
    _, untagged = _parse_package_versions(versions)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    count = 0

    for ver in untagged:
        created = datetime.fromisoformat(ver["created_at"].replace("Z", "+00:00"))
        if prune_all or created < cutoff:
            if dry_run:
                count += 1
            else:
                delete_package_version(org, package_name, ver["id"])
                count += 1

    return count
```

**Step 3: Run tests, commit**

```bash
uv run pytest tests/test_oci.py -v
git add src/zero_cache_chart/oci.py tests/test_oci.py
git commit -m "feat: add OCI registry operations with push-if-not-exists and pruning"
```

---

### Task 8: Wire Up the CLI

**Files:**
- Modify: `src/zero_cache_chart/cli.py` — implement `update` and `prune` commands
- Create: `tests/test_cli.py`

**Step 1: Implement the update command**

This is the orchestration layer that ties together docker, chart, git, oci, and
versions modules. It replaces the monolithic `run_version_management()` function.

The `update` command should:
1. Read current chart version
2. Fetch Docker Hub versions
3. Compare and update main branch if newer
4. Create new version branch if new major.minor detected
5. Update retained version branches (last N)
6. Create per-release git tag for the new version
7. Update branch pointer git tags (v0.26, v0.26-canary)
8. Push to OCI registry (if not exists)
9. Apply OCI pointer tags via oras
10. Print summary

The `prune` command should:
1. Call `oci.prune_untagged()` with the provided parameters
2. Print count of deleted versions

**Step 2: Implement the prune command**

Wire `prune` to `oci.prune_untagged()`.

**Step 3: Test CLI integration**

```bash
uv run zero-cache-chart update --help
uv run zero-cache-chart prune --help
uv run zero-cache-chart update --docker-image=rocicorp/zero --oci-repo=synapdeck/zero-cache-chart --dry-run
```

**Step 4: Commit**

```bash
git add src/zero_cache_chart/cli.py tests/test_cli.py
git commit -m "feat: wire up update and prune CLI commands"
```

---

### Task 9: Delete Old Code

**Files:**
- Delete: `version_manager.py`

**Step 1: Remove the monolith**

```bash
git rm version_manager.py
git commit -m "chore: remove monolithic version_manager.py"
```

---

### Task 10: Update CI Workflow

**Files:**
- Modify: `.github/workflows/version-management.yml`

**Step 1: Rewrite the workflow**

Three jobs:

```yaml
name: Version Management

on:
  push:
    branches: [main]
  schedule:
    - cron: "0 * * * *"
  workflow_dispatch:
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
      - name: Validate templates
        run: |
          nix develop --command bash -c "
            helm template zero-cache . | kubeconform -strict -summary
          "

  update-versions:
    if: github.event_name != 'pull_request'
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
            --oci-repo=synapdeck/zero-cache-chart \
            --branch-retention=3

  prune-oci:
    if: github.event_name != 'pull_request'
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
            --oci-registry=ghcr.io \
            --oci-repo=synapdeck/zero-cache-chart \
            --max-age-days=7
```

**Step 2: Commit**

```bash
git add .github/workflows/version-management.yml
git commit -m "ci: rewrite workflow with Nix, chart validation, and OCI pruning"
```

---

### Task 11: Helm Chart Template Audit

**Files:**
- Modify: all files in `templates/`
- Modify: `values.yaml`

**Step 1: Read all templates thoroughly**

Read every template file and the upstream zero-cache documentation. Document
findings in a list covering:
- Correctness of the deployment topology
- Probe configuration vs actual zero-cache behavior
- Security context completeness
- Label standards
- Service configuration
- Litestream integration
- Init container logic
- Environment variable handling
- Resource defaults
- Any hardcoded values that should be configurable
- Missing features or misconfigurations

**Step 2: Present findings to user for review**

Do NOT make changes yet. Present the audit results as a list of issues with
proposed fixes. Get approval for each behavioral change.

**Step 3: Implement approved fixes**

Apply changes in logical groups with a commit per group:
- Labels and metadata fixes
- Security context fixes
- Probe configuration fixes
- Service and networking fixes
- Environment variable / configuration fixes
- Any structural changes (new templates, removed templates)

**Step 4: Validate**

```bash
helm lint .
helm template zero-cache . | kubeconform -strict -summary
helm template zero-cache . -f examples/single-node.yaml | kubeconform -strict -summary
```

**Step 5: Commit**

One commit per logical group of template changes.

---

### Task 12: One-Time OCI Cleanup

**After CI is deployed and working.**

**Step 1: Run the prune command with --all**

```bash
GITHUB_TOKEN=<token> zero-cache-chart prune \
  --oci-registry=ghcr.io \
  --oci-repo=synapdeck/zero-cache-chart \
  --all
```

This will delete all 37K+ untagged versions. May take a while due to API rate limits.
Consider adding rate limiting / batching to the prune command if needed.

---

### Task 13: Update README and Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-04-project-revival-design.md` (mark as completed)

**Step 1: Update README**

- Update development setup instructions (Nix instead of mise)
- Document the new CLI (`zero-cache-chart update`, `zero-cache-chart prune`)
- Update version management description (branch retention, tagging strategy)
- Remove references to `version_manager.py`

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README for Nix flake and new CLI"
```
