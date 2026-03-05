from __future__ import annotations

import hashlib
import base64
import re
from pathlib import Path

import yaml
from semver.version import Version


def read_chart_version(chart_path: Path) -> Version | None:
    """Read the appVersion from Chart.yaml."""
    data = yaml.safe_load(chart_path.read_text())
    version_str = str(data.get("appVersion", "")).strip().strip('"')
    if Version.is_valid(version_str):
        return Version.parse(version_str)
    return None


def read_chart_oci_version(chart_path: Path) -> str:
    """Read the chart version (used as OCI tag by helm push)."""
    data = yaml.safe_load(chart_path.read_text())
    return str(data.get("version", "0.0.0"))


def _is_breaking_upgrade(old: Version, new: Version) -> bool:
    """Major bumps, or minor bumps before 1.0, are breaking."""
    if new.major != old.major:
        return True
    return old.major == 0 and new.minor != old.minor


def write_chart_version(chart_path: Path, version: Version) -> str | None:
    """Update appVersion and bump chart version. Returns new chart version, or None if unchanged."""
    text = chart_path.read_text()
    data = yaml.safe_load(text)
    current_app_str = str(data.get("appVersion", ""))
    new_app = str(version)

    if current_app_str == new_app:
        return None

    data["appVersion"] = new_app

    chart_ver = data.get("version", "0.0.0")
    if Version.is_valid(str(chart_ver)):
        cv = Version.parse(str(chart_ver))
        if Version.is_valid(current_app_str) and _is_breaking_upgrade(Version.parse(current_app_str), version):
            data["version"] = str(cv.bump_major())
        else:
            data["version"] = str(cv.bump_patch())
    else:
        data["version"] = new_app

    chart_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    return str(data["version"])


def sri_hash(path: Path) -> str:
    """Compute SRI hash (sha256) of a file."""
    digest = hashlib.sha256(path.read_bytes()).digest()
    return "sha256-" + base64.b64encode(digest).decode()


def write_chart_nix(nix_path: Path, version: str, chart_hash: str) -> None:
    """Update version and chartHash in chart.nix."""
    text = nix_path.read_text()
    text = re.sub(r'(version\s*=\s*)"[^"]*"', rf'\1"{version}"', text)
    text = re.sub(r'(chartHash\s*=\s*)"[^"]*"', rf'\1"{chart_hash}"', text)
    nix_path.write_text(text)
