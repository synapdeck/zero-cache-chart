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
