#!/usr/bin/env python3

import sys
from typing import Dict, List, Optional, Union, Tuple
import yaml
import requests
from semver.version import Version
import subprocess
import re
from pathlib import Path
import fire


def run_command(cmd: str, check: bool = True) -> str:
    """Run a shell command and return output"""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=check
    )
    return result.stdout.strip()


def get_current_version(chart_path: Path) -> Tuple[Optional[Version], Optional[str]]:
    """
    Get current version from Chart.yaml and return as a Version object along with major.minor string

    Args:
        chart_path: Path to the Chart.yaml file

    Returns:
        Tuple containing:
        - Version object (or None if not valid semver)
        - Major.minor string (or None if not valid)
    """
    # Get current version
    with open(chart_path, "r") as f:
        chart_data = yaml.safe_load(f)
        version_str = chart_data.get("appVersion", "").replace('"', "")

    current_version = None
    current_major_minor = None

    if Version.is_valid(version_str):
        current_version = Version.parse(version_str)
        current_major_minor = f"{current_version.major}.{current_version.minor}"
        print(f"Current version: {current_version} (valid semver)")
    else:
        parts = version_str.split(".")
        if len(parts) >= 2:
            current_major_minor = f"{parts[0]}.{parts[1]}"
            print(f"Current version: {version_str} (not standard semver)")
        else:
            print(
                f"Warning: Current version {version_str} does not appear to be a valid version"
            )

    print(f"Current major.minor: {current_major_minor}")
    return current_version, current_major_minor


def fetch_docker_versions(docker_image: str) -> Tuple[List[Version], Dict[str, Version]]:
    """
    Fetch all versions of the Docker image

    Args:
        docker_image: Docker image name to fetch versions for

    Returns:
        Tuple containing:
        - List of Version objects sorted by version
        - Dictionary mapping major.minor to latest Version object
    """
    if not docker_image:
        raise ValueError("Docker image name is required")

    url = f"https://hub.docker.com/v2/repositories/{docker_image}/tags/?page_size=100"
    response = requests.get(url)
    data = response.json()

    # Extract version tags and filter valid semver
    versions: List[Version] = []
    for tag in data.get("results", []):
        tag_name = tag.get("name", "")
        if Version.is_valid(tag_name):
            version_obj = Version.parse(tag_name)
            versions.append(version_obj)

    # Sort versions using semver functionality (Version objects implement comparison)
    versions.sort()

    # Create map of major.minor string to latest Version object
    version_map: Dict[str, Version] = {}
    for version in versions:
        major_minor = f"{version.major}.{version.minor}"
        # Only store the highest version for each major.minor
        if (
            major_minor not in version_map
            or version_map[major_minor] < version
        ):
            version_map[major_minor] = version

    latest_version = versions[-1] if versions else None
    print(f"Latest version: {latest_version or 'None'}")
    print(f"All major.minor versions: {list(version_map.keys())}")
    return versions, version_map


def get_version_branches() -> List[str]:
    """
    Get all version branches

    Returns:
        List of branch names
    """
    run_command("git fetch origin")
    output = run_command(
        "git branch -r | grep 'origin/v[0-9]\\+\\.[0-9]\\+' || echo ''"
    )
    if output:
        branches = [
            b.strip().replace("origin/", "")
            for b in output.split("\n")
            if b.strip()
        ]
        return branches
    return []


def update_chart_version(chart_path: Path, version: Union[Version, str]) -> bool:
    """
    Update Chart.yaml with new version

    Args:
        chart_path: Path to the Chart.yaml file
        version: A Version object or a version string

    Returns:
        bool: True if the update was successful, False otherwise
    """
    # Ensure we're working with a valid Version object
    if isinstance(version, str):
        if Version.is_valid(version):
            version_obj = Version.parse(version)
        else:
            print(f"Warning: {version} is not a valid semver version")
            return False
    else:
        # Already a Version object
        version_obj = version

    with open(chart_path, "r") as f:
        chart_data = yaml.safe_load(f)

    # Update appVersion
    chart_data["appVersion"] = str(version_obj)

    with open(chart_path, "w") as f:
        yaml.dump(chart_data, f, default_flow_style=False)

    # Commit the change
    run_command(f"git add {chart_path}")
    run_command(
        f'git commit -m "chore(chart): update Helm chart appVersion to {version_obj}"'
    )

    # Update chart version to match appVersion
    with open(chart_path, "r") as f:
        chart_data = yaml.safe_load(f)

    # Update version
    chart_data["version"] = str(version_obj)

    with open(chart_path, "w") as f:
        yaml.dump(chart_data, f, default_flow_style=False)

    # Commit the change
    run_command(f"git add {chart_path}")
    run_command(
        f'git commit -m "chore(chart): update chart version to {version_obj}"'
    )

    return True


def update_main_branch(
    chart_path: Path,
    all_versions: List[Version],
    current_version: Optional[Version],
    oci_registry: str,
    oci_repo: str
) -> None:
    """
    Update main branch with the latest version from Docker Hub

    Args:
        chart_path: Path to Chart.yaml
        all_versions: List of all version objects
        current_version: Current version object or None
        oci_registry: OCI registry URL
        oci_repo: OCI repository name
    """
    if not all_versions:
        print("No versions found")
        return

    latest_version = all_versions[-1]  # This is a Version object

    # Validate versions
    if not current_version:
        print("Warning: Current version is not a valid semver version")
        return

    # Compare using Version objects directly
    if latest_version == current_version:
        print(f"Main branch already at latest version {latest_version}")
        return

    # Check compatibility between versions (using Version objects directly)
    if latest_version.is_compatible(current_version):
        print(
            f"Versions are compatible according to semver rules: {latest_version} is compatible with {current_version}"
        )
    else:
        print(
            f"Versions are NOT compatible according to semver rules: {latest_version} is not compatible with {current_version}"
        )

    if latest_version.major > current_version.major:
        print(
            f"Major version bump detected: {current_version} → {latest_version}"
        )
    elif latest_version.minor > current_version.minor:
        print(
            f"Minor version bump detected: {current_version} → {latest_version}"
        )
    else:
        print(f"Patch update detected: {current_version} → {latest_version}")

    print(f"Updating main branch from {current_version} to {latest_version}")

    # Checkout main branch
    run_command("git checkout main")

    # Update Chart.yaml
    update_chart_version(chart_path, latest_version)

    # Push to main
    run_command("git push origin main")

    # Create version tag
    tag_name = f"v{latest_version}"
    run_command(f"git tag {tag_name}")
    run_command(f"git push origin {tag_name}")

    # Package and push chart to OCI registry
    run_command("helm package ./zero-cache")
    chart_package = run_command("ls zero-cache-*.tgz")
    run_command(f"helm push {chart_package} oci://{oci_registry}/{oci_repo}")

    print(f"Updated main branch to {latest_version}")


def create_new_version_branch(
    chart_path: Path,
    all_versions: List[Version],
    current_major_minor: Optional[str],
    oci_registry: str,
    oci_repo: str
) -> None:
    """
    Create a new branch for latest major.minor version if it doesn't exist

    Args:
        chart_path: Path to Chart.yaml
        all_versions: List of all version objects
        current_major_minor: Current major.minor string
        oci_registry: OCI registry URL
        oci_repo: OCI repository name
    """
    if not all_versions:
        return

    latest_version = all_versions[-1]  # This is a Version object
    latest_major_minor = f"{latest_version.major}.{latest_version.minor}"

    # Only create if it's a new major.minor
    if latest_major_minor != current_major_minor:
        # Check if branch already exists
        branch_name = f"v{latest_major_minor}"
        existing_branches = run_command("git branch -r").split("\n")

        if not any(branch_name in b for b in existing_branches):
            print(f"Creating new version branch {branch_name}")

            # Create new branch from main
            run_command("git checkout main")
            run_command(f"git checkout -b {branch_name}")

            # Update Chart.yaml
            update_chart_version(chart_path, latest_version)

            # Push branch
            run_command(f"git push origin {branch_name}")

            # Create version tag
            tag_name = f"v{latest_major_minor}/{latest_version}"
            run_command(f"git tag {tag_name}")
            run_command(f"git push origin {tag_name}")

            # Package and push chart to OCI registry
            run_command("helm package ./zero-cache")
            chart_package = run_command("ls zero-cache-*.tgz")
            run_command(
                f"helm push {chart_package} oci://{oci_registry}/{oci_repo}"
            )

            print(f"Created version branch {branch_name}")


def update_version_branches(
    chart_path: Path,
    git_branches: List[str],
    version_map: Dict[str, Version],
    oci_registry: str,
    oci_repo: str
) -> None:
    """
    Update all version branches with their latest corresponding Version objects

    Args:
        chart_path: Path to Chart.yaml
        git_branches: List of git branch names
        version_map: Dictionary mapping major.minor to latest Version object
        oci_registry: OCI registry URL
        oci_repo: OCI repository name
    """
    if not git_branches:
        return

    for branch in git_branches:
        # Extract major.minor from branch name
        match = re.search(r"v(\d+\.\d+)", branch)
        if not match:
            continue

        branch_mm = match.group(1)

        # Get latest Version object for this major.minor
        latest_version = version_map.get(branch_mm)
        if not latest_version:
            print(f"No version found for {branch_mm}, skipping")
            continue

        # Checkout branch
        run_command(f"git checkout {branch}")

        # Get current version
        with open(chart_path, "r") as f:
            chart_data = yaml.safe_load(f)
            version_str = chart_data.get("appVersion", "").replace('"', "")

            if not Version.is_valid(version_str):
                print(
                    f"Warning: Current version {version_str} on branch {branch} is not a valid semver version"
                )
                continue

            current_version = Version.parse(version_str)

        if latest_version > current_version:
            print(f"Updating {branch} from {current_version} to {latest_version}")

            # Check if this is a compatible update
            if latest_version.is_compatible(current_version):
                print("  This is a compatible update according to semver rules")
            else:
                print(
                    "  This is NOT a compatible update according to semver rules - potential breaking changes"
                )
                return

            # Update Chart.yaml
            if not update_chart_version(chart_path, latest_version):
                print(f"  Failed to update chart version, skipping branch {branch}")
                continue

            # Push branch
            run_command(f"git push origin {branch}")

            # Create version tag
            tag_name = f"v{branch_mm}/{latest_version}"
            run_command(f"git tag {tag_name}")
            run_command(f"git push origin {tag_name}")

            # Package and push chart to OCI registry
            run_command("helm package ./zero-cache")
            chart_package = run_command("ls zero-cache-*.tgz")
            run_command(
                f"helm push {chart_package} oci://{oci_registry}/{oci_repo}"
            )

            print(f"Updated branch {branch} to {latest_version}")
        else:
            print(f"Branch {branch} already at latest version {latest_version}")


def run_version_management(
    docker_image: str,
    chart_path: Path,
    values_path: Path,
    oci_registry: str,
    oci_repo: str
) -> int:
    """
    Run the complete version management process

    Args:
        docker_image: Docker image name
        chart_path: Path to Chart.yaml
        values_path: Path to values.yaml
        oci_registry: OCI registry URL
        oci_repo: OCI repository name

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    if not docker_image or not oci_registry or not oci_repo:
        print("Error: Required parameters missing. Please provide docker_image, oci_registry, and oci_repo.")
        return 1

    try:
        # Get current version information
        current_version, current_major_minor = get_current_version(chart_path)

        # Fetch all versions from Docker Hub
        all_versions, version_map = fetch_docker_versions(docker_image)

        # Update main branch
        update_main_branch(chart_path, all_versions, current_version, oci_registry, oci_repo)

        # Create new version branch if needed
        create_new_version_branch(chart_path, all_versions, current_major_minor, oci_registry, oci_repo)

        # Get all version branches
        git_branches = get_version_branches()

        # Update all version branches
        update_version_branches(chart_path, git_branches, version_map, oci_registry, oci_repo)

        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main(
    docker_image: str,
    chart_path: str,
    values_path: str,
    oci_registry: str,
    oci_repo: str
) -> int:
    """
    Manage Docker image versions and update Helm charts accordingly.

    Args:
        docker_image: Docker image name (e.g., 'rocicorp/zero')
        chart_path: Path to the Chart.yaml file
        values_path: Path to the values.yaml file
        oci_registry: OCI registry URL (e.g., 'ghcr.io')
        oci_repo: OCI repository name

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    return run_version_management(
        docker_image=docker_image,
        chart_path=Path(chart_path),
        values_path=Path(values_path),
        oci_registry=oci_registry,
        oci_repo=oci_repo
    )


if __name__ == "__main__":
    sys.exit(fire.Fire(main))
