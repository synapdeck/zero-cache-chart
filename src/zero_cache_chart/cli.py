from __future__ import annotations

from pathlib import Path

import click
from semver.version import Version

from zero_cache_chart.chart import read_chart_version, read_chart_oci_version, write_chart_version
from zero_cache_chart.docker import fetch_docker_versions
from zero_cache_chart.git import Git
from zero_cache_chart.oci import push_if_not_exists, prune_untagged, delete_all_versions
from zero_cache_chart.types import VersionManagementResult
from zero_cache_chart.versions import (
    get_latest_stable,
    classify_version_tag,
)


def _split_oci_repo(oci_repo: str) -> tuple[str, str]:
    """Split org/package-path, where package-path may contain slashes."""
    parts = oci_repo.split("/", 1)
    if len(parts) != 2 or not parts[1]:
        raise click.BadParameter(f"Expected org/package format, got: {oci_repo}", param_hint="--oci-repo")
    return parts[0], parts[1]


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

    latest = get_latest_stable(all_versions)
    click.echo(f"Latest stable upstream: {latest}")

    up_to_date = not latest or (current_version and latest <= current_version)
    if up_to_date:
        click.echo("Already up to date")
        # Still ensure OCI package is published (e.g. after cleanup)
        oci_version = read_chart_oci_version(chart)
        if not dry_run and push_if_not_exists(oci_registry, oci_repo, oci_version):
            click.echo(f"Pushed {oci_version} to OCI")
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

    # 5. Push to OCI registry (uses chart version as tag, not appVersion)
    oci_version = read_chart_oci_version(chart)
    pushed = push_if_not_exists(oci_registry, oci_repo, oci_version)
    if pushed:
        result.pushed_oci_packages.append(oci_version)
        click.echo(f"Pushed {oci_version} to OCI")
    else:
        click.echo(f"OCI package {oci_version} already exists")

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
    org, package_name = _split_oci_repo(oci_repo)
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
    org, package_name = _split_oci_repo(oci_repo)
    click.echo(f"Deleting ALL versions from {org}/{package_name}")

    if dry_run:
        click.echo("[DRY RUN]")

    count = delete_all_versions(org, package_name, dry_run=dry_run)
    action = "Would delete" if dry_run else "Deleted"
    click.echo(f"{action} {count} version(s)")
