from __future__ import annotations

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


def write_chart_version(chart_path: Path, version: Version) -> str | None:
    """Update appVersion and bump chart patch. Returns new chart version, or None if unchanged."""
    text = chart_path.read_text()
    data = yaml.safe_load(text)
    current_app = str(data.get("appVersion", ""))
    new_app = str(version)

    if current_app == new_app:
        return None

    data["appVersion"] = new_app

    # Bump chart patch version independently
    chart_ver = data.get("version", "0.0.0")
    if Version.is_valid(str(chart_ver)):
        cv = Version.parse(str(chart_ver))
        data["version"] = str(cv.bump_patch())
    else:
        data["version"] = new_app

    chart_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    return data["version"]
