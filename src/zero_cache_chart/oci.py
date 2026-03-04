from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

from zero_cache_chart.types import run


PackageVersion = dict[str, Any]


def version_exists_in_registry(registry: str, repo: str, version: str) -> bool:
    """Check if a chart version already exists in the OCI registry."""
    result = run(
        ["oras", "manifest", "fetch", f"{registry}/{repo}/zero-cache:{version}"],
        check=False,
    )
    return result.returncode == 0


def package_chart(chart_dir: Path = Path(".")) -> Path:
    result = run(["helm", "package", str(chart_dir)])
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
