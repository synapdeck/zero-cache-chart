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
    data["appVersion"] = str(version)
    data["version"] = str(version)
    chart_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
