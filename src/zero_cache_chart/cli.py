from __future__ import annotations

from pathlib import Path

import click
from semver.version import Version

from zero_cache_chart.chart import read_chart_version, write_chart_version
from zero_cache_chart.docker import fetch_docker_versions
from zero_cache_chart.git import Git, list_version_branches
from zero_cache_chart.oci import push_if_not_exists, tag_version, prune_untagged
from zero_cache_chart.types import VersionManagementResult
from zero_cache_chart.versions import (
    build_version_map,
    get_latest_version,
    classify_version_tag,
    branch_pointer_tags,
    select_retained_branches,
)


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
    chart = Path(chart_path)
    git = Git()
    result = VersionManagementResult()

    # 1. Read current chart version
    current_version = read_chart_version(chart)
    result.current_version = str(current_version) if current_version else None
    click.echo(f"Current version: {current_version or 'unknown'}")

    # 2. Fetch Docker Hub versions
    all_versions = fetch_docker_versions(docker_image)
    if not all_versions:
        click.echo("No versions found on Docker Hub")
        return

    latest = get_latest_version(all_versions)
    version_map = build_version_map(all_versions)
    click.echo(f"Latest upstream: {latest}")
    click.echo(f"Major.minor versions: {list(version_map.keys())}")

    if dry_run:
        click.echo("\n[DRY RUN] Would perform the following:")
        if current_version and latest and latest > current_version:
            click.echo(f"  Update main branch: {current_version} -> {latest}")
        _print_dry_run_summary(version_map, git, branch_retention, latest, oci_registry, oci_repo)
        return

    original_branch = git.current_branch()

    try:
        # 3. Update main branch if newer
        if current_version and latest and latest > current_version:
            click.echo(f"\nUpdating main: {current_version} -> {latest}")
            write_chart_version(chart, latest)
            git.add(chart_path)
            git.commit(f"chore(chart): update chart to {latest}")
            git.push("main")
            result.main_updated = True

        # 4. Check if new major.minor needs a branch
        if latest:
            latest_mm = f"v{latest.major}.{latest.minor}"
            git.fetch()
            existing_branches = list_version_branches(git)

            if latest_mm not in existing_branches:
                click.echo(f"\nCreating branch {latest_mm}")
                git.checkout("main")
                git.checkout_new(latest_mm)
                git.push(latest_mm)
                result.new_branch_created = latest_mm

        # 5. Update retained version branches
        git.fetch()
        all_branches = list_version_branches(git)
        retained = select_retained_branches(all_branches, retain=branch_retention)
        click.echo(f"\nRetained branches: {retained}")

        for branch in retained:
            _update_branch(git, branch, version_map, chart, chart_path, result)

        # 6. Create per-release git tag
        if latest:
            tag_name, kind = classify_version_tag(latest)
            if not git.tag_exists(tag_name):
                git.checkout("main")
                git.create_tag(tag_name)
                git.push_tag(tag_name)
                result.created_tags.append(tag_name)
                click.echo(f"Created tag {tag_name} ({kind})")

        # 7. Update branch pointer tags
        if latest:
            for pointer_tag in branch_pointer_tags(latest):
                git.checkout("main")
                git.create_tag(pointer_tag, force=True)
                git.push_tag(pointer_tag, force=True)
                click.echo(f"Updated pointer tag {pointer_tag}")

        # 8. Push to OCI registry
        if latest:
            git.checkout("main")
            version_str = str(latest)
            pushed = push_if_not_exists(oci_registry, oci_repo, version_str)
            if pushed:
                result.pushed_oci_packages.append(version_str)
                click.echo(f"Pushed {version_str} to OCI")

                # 9. Apply OCI pointer tags
                for pointer_tag in branch_pointer_tags(latest):
                    tag_version(oci_registry, oci_repo, version_str, pointer_tag.removeprefix("v"))
                    click.echo(f"Applied OCI tag {pointer_tag}")
            else:
                click.echo(f"OCI package {version_str} already exists")

    finally:
        # Restore original branch
        current = git.current_branch()
        if current != original_branch:
            git.checkout(original_branch)

    # 10. Print summary
    _print_summary(result)


def _update_branch(
    git: Git,
    branch: str,
    version_map: dict[str, Version],
    chart: Path,
    chart_path: str,
    result: VersionManagementResult,
) -> None:
    """Update a single version branch to its latest patch."""
    import re

    match = re.search(r"v(\d+\.\d+)", branch)
    if not match:
        return

    mm = match.group(1)
    branch_latest = version_map.get(mm)
    if not branch_latest:
        return

    git.checkout(branch)
    git.pull(branch)

    current = read_chart_version(chart)
    if current and branch_latest > current:
        current_mm = f"{current.major}.{current.minor}"
        if mm != current_mm:
            click.echo(f"  Skipping {branch}: cross-major.minor update {current_mm} -> {mm}")
            return

        click.echo(f"  Updating {branch}: {current} -> {branch_latest}")
        write_chart_version(chart, branch_latest)
        git.add(chart_path)
        git.commit(f"chore(chart): update chart to {branch_latest}")
        git.push(branch)
        result.updated_branches.append(branch)
    else:
        click.echo(f"  {branch} already at {branch_latest}")


def _print_dry_run_summary(
    version_map: dict[str, Version],
    git: Git,
    branch_retention: int,
    latest: Version | None,
    oci_registry: str,
    oci_repo: str,
) -> None:
    try:
        git.fetch()
        branches = list_version_branches(git)
    except Exception:
        branches = []

    retained = select_retained_branches(branches, retain=branch_retention)
    click.echo(f"  Retained branches: {retained}")
    if latest:
        tag_name, _ = classify_version_tag(latest)
        click.echo(f"  Create tag: {tag_name}")
        click.echo(f"  Pointer tags: {branch_pointer_tags(latest)}")
        click.echo(f"  Push to OCI: {oci_registry}/{oci_repo}")


def _print_summary(result: VersionManagementResult) -> None:
    click.echo("\n=== Summary ===")
    if result.current_version:
        click.echo(f"Current version: {result.current_version}")
    click.echo(f"Main updated: {result.main_updated}")
    if result.new_branch_created:
        click.echo(f"New branch: {result.new_branch_created}")
    if result.updated_branches:
        click.echo(f"Updated branches: {', '.join(result.updated_branches)}")
    if result.created_tags:
        click.echo(f"Created tags: {', '.join(result.created_tags)}")
    if result.pushed_oci_packages:
        click.echo(f"Pushed OCI: {', '.join(result.pushed_oci_packages)}")


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
    # Parse org/package from oci_repo (e.g. "synapdeck/zero-cache-chart")
    parts = oci_repo.split("/", 1)
    if len(parts) != 2:
        raise click.BadParameter(f"Expected org/package format, got: {oci_repo}", param_hint="--oci-repo")

    org, package_name = parts
    click.echo(f"Pruning untagged versions from {org}/{package_name}")

    if dry_run:
        click.echo("[DRY RUN]")

    count = prune_untagged(
        org,
        package_name,
        max_age_days=max_age_days,
        prune_all=prune_all,
        dry_run=dry_run,
    )

    action = "Would delete" if dry_run else "Deleted"
    click.echo(f"{action} {count} untagged version(s)")
