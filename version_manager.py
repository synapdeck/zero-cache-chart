#!/usr/bin/env python3

import sys
from typing import Dict, List, Optional, Union, Tuple, Any
import yaml
import requests
from semver.version import Version
import subprocess
import re
from pathlib import Path
import fire


def run_command(cmd: str, check: bool = True) -> str:
    """Run a shell command and return output"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, check=check
        )
        # If command failed but we're not raising an exception, still return stderr for analysis
        if result.returncode != 0 and not check:
            return result.stderr.strip() if result.stderr else result.stdout.strip()
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Return stderr if check=True and command fails
        if not check:
            return e.stderr.strip() if e.stderr else e.stdout.strip()
        raise


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


def fetch_docker_versions(
    docker_image: str,
) -> Tuple[List[Version], Dict[str, Version]]:
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
        if major_minor not in version_map or version_map[major_minor] < version:
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
            b.strip().replace("origin/", "") for b in output.split("\n") if b.strip()
        ]
        return branches
    return []


def update_chart_version(
    chart_path: Path, version: Union[Version, str], commit: bool = True
) -> bool:
    """
    Update Chart.yaml with new version

    Args:
        chart_path: Path to the Chart.yaml file
        version: A Version object or a version string
        commit: Whether to commit the changes

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

    try:
        with open(chart_path, "r") as f:
            chart_data = yaml.safe_load(f)

        current_app_version = chart_data.get("appVersion", "")
        if current_app_version == str(version_obj):
            print(f"appVersion is already set to {version_obj}, no change needed")
        else:
            # Update appVersion
            chart_data["appVersion"] = str(version_obj)

            with open(chart_path, "w") as f:
                yaml.dump(chart_data, f, default_flow_style=False)

            print(f"Updated appVersion from {current_app_version} to {version_obj}")

        if commit:
            # Commit the change
            run_command(f"git add {chart_path}", check=False)
            commit_result = run_command(
                f'git commit -m "chore(chart): update Helm chart appVersion to {version_obj}"',
                check=False,
            )

            if "nothing to commit" in commit_result:
                print("No changes to commit for appVersion")
            elif "error" in commit_result.lower():
                print(f"Warning: Issue committing appVersion change: {commit_result}")

        # Update chart version to match appVersion
        with open(chart_path, "r") as f:
            chart_data = yaml.safe_load(f)

        current_chart_version = chart_data.get("version", "")
        if current_chart_version == str(version_obj):
            print(f"Chart version is already set to {version_obj}, no change needed")
        else:
            # Update version
            chart_data["version"] = str(version_obj)

            with open(chart_path, "w") as f:
                yaml.dump(chart_data, f, default_flow_style=False)

            print(
                f"Updated chart version from {current_chart_version} to {version_obj}"
            )

        if commit:
            # Commit the change
            run_command(f"git add {chart_path}", check=False)
            commit_result = run_command(
                f'git commit -m "chore(chart): update chart version to {version_obj}"',
                check=False,
            )

            if "nothing to commit" in commit_result:
                print("No changes to commit for chart version")
            elif "error" in commit_result.lower():
                print(
                    f"Warning: Issue committing chart version change: {commit_result}"
                )

        return True

    except Exception as e:
        print(f"Error updating chart version: {e}")
        return False


def create_tag(
    version: Union[Version, str],
    is_branch_tag: bool = False,
    branch_mm: Optional[str] = None,
) -> str:
    """
    Create a git tag for the given version

    Args:
        version: Version to create tag for
        is_branch_tag: Whether this is a tag for a version branch
        branch_mm: Major.minor string for branch tags

    Returns:
        str: Tag name that was created
    """
    if isinstance(version, str):
        version_str = version
    else:
        version_str = str(version)

    if is_branch_tag and branch_mm:
        tag_name = f"v{branch_mm}/{version_str}"
    else:
        tag_name = f"v{version_str}"

    # Check if tag already exists
    existing_tags = run_command("git tag -l", check=False)
    if tag_name in existing_tags.split("\n"):
        print(f"Tag {tag_name} already exists, skipping tag creation")
        return tag_name

    print(f"Creating tag {tag_name}")
    tag_result = run_command(f"git tag {tag_name}", check=False)
    if "already exists" in tag_result:
        print(f"Tag {tag_name} already exists, skipping tag creation")
        return tag_name

    push_result = run_command(f"git push origin {tag_name}", check=False)
    if "rejected" in push_result:
        print(f"Tag {tag_name} already exists on remote, skipping push")
    elif "error" in push_result.lower():
        print(f"Warning: Issue pushing tag {tag_name}: {push_result}")
    else:
        print(f"Successfully pushed tag {tag_name}")

    return tag_name


def create_version_tags(
    all_versions: List[Version],
    version_map: Dict[str, Version],
) -> List[str]:
    """
    Create tags for all versions independent of branch or OCI operations

    Args:
        all_versions: List of all version objects
        version_map: Dictionary mapping major.minor to latest Version object

    Returns:
        List[str]: List of created tag names
    """
    if not all_versions:
        return []

    created_tags = []
    latest_version = all_versions[-1]

    # Create main tag for latest version
    print(f"Creating tag for latest version: {latest_version}")
    main_tag = create_tag(latest_version)
    created_tags.append(main_tag)

    # Get all version branches
    git_branches = get_version_branches()
    for branch in git_branches:
        # Extract major.minor from branch name
        match = re.search(r"v(\d+\.\d+)", branch)
        if not match:
            continue

        branch_mm = match.group(1)
        branch_version = version_map.get(branch_mm)

        if not branch_version:
            print(f"No version found for branch {branch}, skipping tag creation")
            continue

        # Create tag for this branch version
        print(f"Creating tag for branch {branch} with version: {branch_version}")
        branch_tag = create_tag(branch_version, is_branch_tag=True, branch_mm=branch_mm)
        created_tags.append(branch_tag)

    return created_tags


def package_and_push_to_oci(oci_registry: str, oci_repo: str) -> bool:
    """
    Package the Helm chart and push to OCI registry

    Args:
        oci_registry: OCI registry URL
        oci_repo: OCI repository name

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"Packaging and pushing chart to OCI registry {oci_registry}/{oci_repo}")

        # Remove any existing packages before creating a new one
        run_command("rm -f zero-cache-*.tgz", check=False)

        # Package the chart
        package_result = run_command("helm package .", check=False)
        if "Error" in package_result:
            print(f"Error packaging Helm chart: {package_result}")
            return False

        chart_package = run_command("ls zero-cache-*.tgz")
        if not chart_package:
            print("Failed to create chart package")
            return False

        # Try to push the chart
        push_result = run_command(
            f"helm push {chart_package} oci://{oci_registry}/{oci_repo}", check=False
        )

        # Check for common errors
        if "already exists" in push_result:
            print(
                f"Chart version already exists in registry {oci_registry}/{oci_repo}, skipping push"
            )
            run_command(f"rm -f {chart_package}", check=False)  # Clean up
            return True
        elif "Error" in push_result or "error" in push_result.lower():
            print(f"Error pushing to OCI registry: {push_result}")
            run_command(f"rm -f {chart_package}", check=False)  # Clean up
            return False
        else:
            print(f"Successfully pushed chart to {oci_registry}/{oci_repo}")
            run_command(f"rm -f {chart_package}", check=False)  # Clean up
            return True

    except Exception as e:
        print(f"Error pushing to OCI registry: {e}")
        # Clean up any generated packages
        run_command("rm -f zero-cache-*.tgz", check=False)
        return False


def update_main_branch(
    chart_path: Path,
    all_versions: List[Version],
    current_version: Optional[Version],
) -> Optional[Version]:
    """
    Update main branch with the latest version from Docker Hub

    Args:
        chart_path: Path to Chart.yaml
        all_versions: List of all version objects
        current_version: Current version object or None

    Returns:
        Optional[Version]: Updated version if successful, None otherwise
    """
    if not all_versions:
        print("No versions found")
        return None

    latest_version = all_versions[-1]  # This is a Version object

    # Validate versions
    if not current_version:
        print("Warning: Current version is not a valid semver version")
        return None

    # Compare using Version objects directly
    if latest_version == current_version:
        print(f"Main branch already at latest version {latest_version}")
        return None

    # Main branch accepts all updates regardless of compatibility
    # Just inform about major/minor version changes for awareness
    latest_mm = f"{latest_version.major}.{latest_version.minor}"
    current_mm = f"{current_version.major}.{current_version.minor}"
    
    if latest_mm != current_mm:
        print(f"Note: Updating across different major.minor versions: {current_mm} → {latest_mm}")
    else:
        print(f"Updating within same major.minor version: {current_mm}")

    if latest_version.major > current_version.major:
        print(f"Major version bump detected: {current_version} → {latest_version}")
    elif latest_version.minor > current_version.minor:
        print(f"Minor version bump detected: {current_version} → {latest_version}")
    else:
        print(f"Patch update detected: {current_version} → {latest_version}")

    print(f"Updating main branch from {current_version} to {latest_version}")

    # Checkout main branch
    checkout_result = run_command("git checkout main", check=False)
    if "error" in checkout_result.lower():
        print(f"Error checking out main branch: {checkout_result}")
        return None

    # Update Chart.yaml
    if not update_chart_version(chart_path, latest_version):
        print("Failed to update chart version")
        return None

    # Push to main
    push_result = run_command("git push origin main", check=False)
    if "error" in push_result.lower() or "rejected" in push_result.lower():
        print(f"Error pushing to main branch: {push_result}")
        print("You may need to pull changes first or resolve conflicts")
        return None

    print(f"Updated main branch to {latest_version}")

    return latest_version


def create_new_version_branch(
    chart_path: Path,
    all_versions: List[Version],
    current_major_minor: Optional[str],
) -> Optional[str]:
    """
    Create a new branch for latest major.minor version if it doesn't exist

    Args:
        chart_path: Path to Chart.yaml
        all_versions: List of all version objects
        current_major_minor: Current major.minor string

    Returns:
        Optional[str]: Branch name if created, None otherwise
    """
    if not all_versions:
        return None

    latest_version = all_versions[-1]  # This is a Version object
    latest_major_minor = f"{latest_version.major}.{latest_version.minor}"

    # Only create if it's a new major.minor
    if latest_major_minor != current_major_minor:
        # Check if branch already exists
        branch_name = f"v{latest_major_minor}"
        existing_branches = run_command("git branch -r").split("\n")

        if not any(branch_name in b for b in existing_branches):
            print(f"Creating new version branch {branch_name}")

            # Check if branch exists remotely (even if not locally)
            remote_branches = run_command("git ls-remote --heads origin", check=False)
            if f"refs/heads/{branch_name}" in remote_branches:
                print(
                    f"Branch {branch_name} already exists on remote, skipping creation"
                )
                return None

            # Create new branch from main
            checkout_main = run_command("git checkout main", check=False)
            if "error" in checkout_main.lower():
                print(f"Error checking out main branch: {checkout_main}")
                return None

            create_branch = run_command(f"git checkout -b {branch_name}", check=False)
            if "error" in create_branch.lower():
                if "already exists" in create_branch.lower():
                    print(f"Branch {branch_name} already exists locally")
                    checkout_result = run_command(
                        f"git checkout {branch_name}", check=False
                    )
                    if "error" in checkout_result.lower():
                        print(
                            f"Error checking out existing branch {branch_name}: {checkout_result}"
                        )
                        return None
                else:
                    print(f"Error creating branch {branch_name}: {create_branch}")
                    return None

            # Update Chart.yaml
            if not update_chart_version(chart_path, latest_version):
                print(f"Failed to update chart version on branch {branch_name}")
                return None

            # Push branch
            push_result = run_command(f"git push origin {branch_name}", check=False)
            if "error" in push_result.lower() or "rejected" in push_result.lower():
                print(f"Error pushing branch {branch_name}: {push_result}")
                return None

            print(f"Created version branch {branch_name}")
            return branch_name

    return None


def update_version_branches(
    chart_path: Path,
    git_branches: List[str],
    version_map: Dict[str, Version],
) -> List[str]:
    """
    Update all version branches with their latest corresponding Version objects

    Args:
        chart_path: Path to Chart.yaml
        git_branches: List of git branch names
        version_map: Dictionary mapping major.minor to latest Version object

    Returns:
        List[str]: List of branches that were updated
    """
    if not git_branches:
        return []

    updated_branches = []

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
        checkout_result = run_command(f"git checkout {branch}", check=False)
        if "error" in checkout_result.lower():
            print(f"Error checking out branch {branch}: {checkout_result}")
            continue

        # Make sure we have the latest from remote
        pull_result = run_command(f"git pull origin {branch}", check=False)
        if "error" in pull_result.lower() or "conflict" in pull_result.lower():
            print(
                f"Warning: Issue pulling latest changes for branch {branch}: {pull_result}"
            )
            print(
                "Will continue with local version, but you may need to resolve conflicts"
            )

        # Get current version
        try:
            with open(chart_path, "r") as f:
                chart_data = yaml.safe_load(f)
                version_str = chart_data.get("appVersion", "").replace('"', "")

                if not Version.is_valid(version_str):
                    print(
                        f"Warning: Current version {version_str} on branch {branch} is not a valid semver version"
                    )
                    continue

                current_version = Version.parse(version_str)
        except Exception as e:
            print(f"Error reading chart file on branch {branch}: {e}")
            continue

        if latest_version > current_version:
            print(f"Updating {branch} from {current_version} to {latest_version}")

            # For version branches, ensure we only update within the same major.minor
            # This is what ^${currentVersion} would mean in semver
            latest_mm = f"{latest_version.major}.{latest_version.minor}"
            current_mm = f"{current_version.major}.{current_version.minor}"
            
            if latest_mm != current_mm:
                print(f"  Cannot update across different major.minor versions: {current_mm} → {latest_mm}")
                continue
                
            print(f"  Updating within same major.minor version: {current_mm}")

            # Update Chart.yaml
            if not update_chart_version(chart_path, latest_version):
                print(f"  Failed to update chart version, skipping branch {branch}")
                continue

            # Push branch
            push_result = run_command(f"git push origin {branch}", check=False)
            if "error" in push_result.lower() or "rejected" in push_result.lower():
                print(f"Error pushing branch {branch}: {push_result}")
                print("Skipping further operations for this branch")
                continue

            print(f"Updated branch {branch} to {latest_version}")
            updated_branches.append(branch)
        else:
            print(f"Branch {branch} already at latest version {latest_version}")

    return updated_branches


def push_oci_packages(
    all_versions: List[Version],
    version_map: Dict[str, Version],
    oci_registry: str,
    oci_repo: str,
) -> List[str]:
    """
    Push all version charts to OCI registry, independent of branch or tag operations

    Args:
        all_versions: List of all version objects
        version_map: Dictionary mapping major.minor to latest Version object
        oci_registry: OCI registry URL
        oci_repo: OCI repository name

    Returns:
        List[str]: List of versions that were pushed to OCI
    """
    if not all_versions or not oci_registry or not oci_repo:
        return []

    pushed_versions = []
    latest_version = all_versions[-1]

    print(f"Pushing OCI packages for latest version: {latest_version}")

    # Push main version to OCI
    run_command("git checkout main", check=False)
    if package_and_push_to_oci(oci_registry, oci_repo):
        pushed_versions.append(str(latest_version))

    # Handle version branch packages
    git_branches = get_version_branches()
    for branch in git_branches:
        # Extract major.minor from branch name
        match = re.search(r"v(\d+\.\d+)", branch)
        if not match:
            continue

        branch_mm = match.group(1)
        branch_version = version_map.get(branch_mm)

        if not branch_version:
            continue

        print(f"Pushing OCI package for branch {branch} with version: {branch_version}")

        # Need to checkout the branch first
        checkout_result = run_command(f"git checkout {branch}", check=False)
        if "error" in checkout_result.lower():
            print(
                f"Error checking out branch {branch}, skipping OCI push: {checkout_result}"
            )
            continue

        if package_and_push_to_oci(oci_registry, oci_repo):
            pushed_versions.append(str(branch_version))

    return pushed_versions


def run_version_management(
    docker_image: str,
    chart_path: Path,
    values_path: Path,
    manage_branches: bool = True,
    manage_tags: bool = True,
    manage_oci: bool = True,
    oci_registry: Optional[str] = None,
    oci_repo: Optional[str] = None,
    dry_run: bool = False,
) -> int:
    """
    Run the complete version management process

    Args:
        docker_image: Docker image name
        chart_path: Path to Chart.yaml
        values_path: Path to values.yaml
        manage_branches: Whether to update branches
        manage_tags: Whether to create tags
        manage_oci: Whether to push to OCI registry
        oci_registry: OCI registry URL
        oci_repo: OCI repository name
        dry_run: Whether to just simulate operations without making changes

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    current_branch = None

    # Validate required parameters
    if not docker_image:
        print("Error: Required parameter 'docker_image' is missing.")
        return 1

    # Check OCI parameters if OCI management is enabled
    if manage_oci and (not oci_registry or not oci_repo):
        print(
            "Error: OCI registry parameters required when manage_oci is enabled. Please provide oci_registry and oci_repo."
        )
        return 1

    try:
        # Set up dry run mode if requested
        if dry_run:
            print("DRY RUN MODE - No changes will be committed")

        # Verify git repository
        git_check = run_command("git rev-parse --is-inside-work-tree", check=False)
        if "true" not in git_check.lower():
            print("Error: Not in a git repository")
            return 1

        # Save current git state
        current_branch = run_command("git branch --show-current", check=False)
        print(f"Current git branch: {current_branch}")

        # Get version information
        current_version, current_major_minor = get_current_version(chart_path)
        all_versions, version_map = fetch_docker_versions(docker_image)

        # Initialize results tracking
        results = {
            "main_updated": False,
            "new_branch_created": None,
            "updated_branches": [],
            "created_tags": [],
            "pushed_oci_packages": [],
            "current_version": str(current_version) if current_version else None,
        }

        # Process branch management if enabled
        if manage_branches:
            results = _handle_branch_management(
                dry_run,
                chart_path,
                all_versions,
                current_version,
                current_major_minor,
                version_map,
                results,
            )

            # Get updated current version after branch management
            updated_current_version, _ = get_current_version(chart_path)
        else:
            # If not managing branches, use the initially detected version
            updated_current_version = current_version

        # Process tag management if enabled
        if manage_tags:
            results = _handle_tag_management(
                dry_run, all_versions, version_map, results, updated_current_version
            )

        # Process OCI package management if enabled
        if manage_oci and oci_registry and oci_repo:
            results = _handle_oci_management(
                dry_run, all_versions, version_map, oci_registry, oci_repo, results, updated_current_version
            )

        # Print summary of operations
        _print_summary(manage_branches, manage_tags, manage_oci, results)

        # Restore original branch if changed and not in dry run mode
        if (
            not dry_run
            and current_branch
            and current_branch != run_command("git branch --show-current", check=False)
        ):
            print(f"Restoring original branch: {current_branch}")
            restore_result = run_command(f"git checkout {current_branch}", check=False)
            if "error" in restore_result.lower():
                print(
                    f"Warning: Could not restore to original branch {current_branch}: {restore_result}"
                )

        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()

        # Try to restore original branch in case of error
        if not dry_run and current_branch:
            print(f"Attempting to restore original branch: {current_branch}")
            try:
                run_command(f"git checkout {current_branch}", check=False)
            except Exception:
                print(f"Failed to restore to original branch {current_branch}")

        return 1


def _handle_branch_management(
    dry_run: bool,
    chart_path: Path,
    all_versions: List[Version],
    current_version: Optional[Version],
    current_major_minor: Optional[str],
    version_map: Dict[str, Version],
    results: Dict[str, Any],
) -> Dict[str, Any]:
    """Helper function to manage branches"""
    if dry_run:
        print("DRY RUN: Would update main branch")
    else:
        print("\n=== BRANCH MANAGEMENT ===")
        # Update main branch
        updated_version = update_main_branch(chart_path, all_versions, current_version)
        results["main_updated"] = updated_version is not None

        # Create new version branch if needed
        new_branch = create_new_version_branch(
            chart_path, all_versions, current_major_minor
        )
        results["new_branch_created"] = new_branch

        # Get all version branches
        git_branches = get_version_branches()

        # Update all version branches
        updated_branches = update_version_branches(
            chart_path, git_branches, version_map
        )
        results["updated_branches"] = updated_branches

    return results


def _handle_tag_management(
    dry_run: bool,
    all_versions: List[Version],
    version_map: Dict[str, Version],
    results: Dict[str, Any],
    current_version: Optional[Version] = None,
) -> Dict[str, Any]:
    """Helper function to manage tags"""
    if dry_run:
        print("DRY RUN: Would create version tags")
    else:
        print("\n=== TAG MANAGEMENT ===")
        # Create tags for all versions
        created_tags = create_version_tags(all_versions, version_map)
        results["created_tags"] = created_tags

        # Check if current version has a tag
        if current_version:
            version_str = str(current_version)
            if version_str not in results["created_tags"]:
                print(f"Checking if tag exists for current version: {version_str}")
                tag_check = run_command(f"git tag -l v{version_str}", check=False).strip()
                if not tag_check:
                    print(f"Creating tag for current version: {version_str}")
                    create_tag(version_str)
                    results["created_tags"].append(version_str)

    return results


def _handle_oci_management(
    dry_run: bool,
    all_versions: List[Version],
    version_map: Dict[str, Version],
    oci_registry: str,
    oci_repo: str,
    results: Dict[str, Any],
    current_version: Optional[Version] = None,
) -> Dict[str, Any]:
    """Helper function to manage OCI packages"""
    if dry_run:
        print("DRY RUN: Would push packages to OCI registry")
    else:
        print("\n=== OCI PACKAGE MANAGEMENT ===")
        # Push packages to OCI registry
        pushed_packages = push_oci_packages(
            all_versions, version_map, oci_registry, oci_repo
        )
        results["pushed_oci_packages"] = pushed_packages

        # Check if current version has an OCI package
        if current_version:
            version_str = str(current_version)
            if version_str not in results["pushed_oci_packages"]:
                print(f"Checking if OCI package exists for current version: {version_str}")
                # Push package for current version if not already pushed
                if version_str in version_map:
                    print(f"Pushing OCI package for current version: {version_str}")
                    # Need to update Chart.yaml with this version before packaging
                    current_chart_path = Path("./Chart.yaml")
                    if update_chart_version(current_chart_path, version_str, commit=False):
                        success = package_and_push_to_oci(oci_registry, oci_repo)
                    else:
                        success = False
                    if success:
                        results["pushed_oci_packages"].append(version_str)

    return results


def _print_summary(
    manage_branches: bool,
    manage_tags: bool,
    manage_oci: bool,
    results: Dict[str, Any],
) -> None:
    """Print summary of operations performed"""
    print("\n=== SUMMARY ===")
    if results.get("current_version"):
        print(f"Current version: {results['current_version']}")
    if manage_branches:
        print("Branch management:")
        print(f"  - Main branch updated: {results['main_updated']}")
        if results["new_branch_created"]:
            print(f"  - New branch created: {results['new_branch_created']}")
        if results["updated_branches"]:
            print(f"  - Updated branches: {', '.join(results['updated_branches'])}")
        else:
            print("  - No branches needed updating")

    if manage_tags:
        print("Tag management:")
        if results["created_tags"]:
            print(f"  - Created tags: {', '.join(results['created_tags'])}")
            if results.get("current_version") and results["current_version"] in results["created_tags"]:
                print(f"  - Current version {results['current_version']} has tag")
        else:
            print("  - No new tags created, all tags already exist")

        # Check if current version has a tag even if we didn't create one
        if results.get("current_version") and results["current_version"] not in results["created_tags"]:
            tag_exists = run_command(f"git tag -l v{results['current_version']}", check=False).strip()
            if tag_exists:
                print(f"  - Current version {results['current_version']} already has tag")
            else:
                print(f"  - Current version {results['current_version']} does not have tag")

    if manage_oci:
        print("OCI package management:")
        if results["pushed_oci_packages"]:
            print(f"  - Pushed packages: {', '.join(results['pushed_oci_packages'])}")
            if results.get("current_version") and results["current_version"] in results["pushed_oci_packages"]:
                print(f"  - Current version {results['current_version']} has OCI package")
        else:
            print("  - No new packages pushed to OCI registry")

        # Note if current version has an OCI package even if we didn't push one
        if results.get("current_version") and results["current_version"] not in results["pushed_oci_packages"]:
            print(f"  - Current version {results['current_version']} may not have OCI package")


def main(
    docker_image: str,
    chart_path: str,
    values_path: str,
    oci_registry: str = "",
    oci_repo: str = "",
    manage_branches: bool = True,
    manage_tags: bool = True,
    manage_oci: bool = True,
    dry_run: bool = False,
) -> int:
    """
    Manage Docker image versions and update Helm charts accordingly.

    Each management operation (branches, tags, OCI packages) is completely independent
    and can be enabled or disabled as needed.

    Args:
        docker_image: Docker image name (e.g., 'rocicorp/zero')
        chart_path: Path to the Chart.yaml file
        values_path: Path to the values.yaml file
        oci_registry: OCI registry URL (e.g., 'ghcr.io')
        oci_repo: OCI repository name
        manage_branches: Whether to update branches (default: True)
        manage_tags: Whether to create tags (default: True)
        manage_oci: Whether to push to OCI registry (default: True)
        dry_run: Whether to just simulate operations without making changes (default: False)

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    return run_version_management(
        docker_image=docker_image,
        chart_path=Path(chart_path),
        values_path=Path(values_path),
        manage_branches=manage_branches,
        manage_tags=manage_tags,
        manage_oci=manage_oci,
        oci_registry=oci_registry if oci_registry else None,
        oci_repo=oci_repo if oci_repo else None,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    sys.exit(fire.Fire(main))
