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
    current_app = str(data.get("appVersion", ""))
    new_app = str(version)

    if current_app == new_app:
        return  # Nothing to update

    data["appVersion"] = new_app

    # Bump chart patch version independently
    chart_ver = data.get("version", "0.0.0")
    if Version.is_valid(str(chart_ver)):
        cv = Version.parse(str(chart_ver))
        data["version"] = str(cv.bump_patch())
    else:
        data["version"] = new_app

    chart_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
