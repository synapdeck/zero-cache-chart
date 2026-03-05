from __future__ import annotations

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


def classify_version_tag(version: Version) -> tuple[str, str]:
    tag_name = f"v{version}"
    kind = "prerelease" if version.prerelease else "stable"
    return tag_name, kind
