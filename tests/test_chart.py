from pathlib import Path

import yaml
from semver.version import Version
from zero_cache_chart.chart import read_chart_version, read_chart_oci_version, write_chart_version, _is_breaking_upgrade


def test_read_chart_version(tmp_path: Path):
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.26.1-canary.4\nversion: 0.26.1-canary.4\n")
    ver = read_chart_version(chart)
    assert ver == Version.parse("0.26.1-canary.4")


def test_read_chart_version_invalid(tmp_path: Path):
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: latest\nversion: latest\n")
    ver = read_chart_version(chart)
    assert ver is None


def test_write_chart_version(tmp_path: Path):
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.26.0\nversion: 2.0.0\nname: zero-cache\n")
    write_chart_version(chart, Version.parse("0.26.1"))
    ver = read_chart_version(chart)
    assert ver == Version.parse("0.26.1")


def test_write_chart_version_patch_bump(tmp_path: Path):
    """Patch appVersion bump produces chart patch bump."""
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.26.0\nversion: 2.0.0\nname: zero-cache\n")
    new_ver = write_chart_version(chart, Version.parse("0.26.1"))
    data = yaml.safe_load(chart.read_text())
    assert data["appVersion"] == "0.26.1"
    assert data["version"] == "2.0.1"
    assert new_ver == "2.0.1"


def test_write_chart_version_pre1_minor_bump(tmp_path: Path):
    """Pre-1.0 minor appVersion bump produces chart major bump."""
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.25.0\nversion: 1.0.5\nname: zero-cache\n")
    new_ver = write_chart_version(chart, Version.parse("0.26.0"))
    data = yaml.safe_load(chart.read_text())
    assert data["appVersion"] == "0.26.0"
    assert data["version"] == "2.0.0"
    assert new_ver == "2.0.0"


def test_write_chart_version_major_bump(tmp_path: Path):
    """Major appVersion bump produces chart major bump."""
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.27.0\nversion: 3.0.2\nname: zero-cache\n")
    new_ver = write_chart_version(chart, Version.parse("1.0.0"))
    data = yaml.safe_load(chart.read_text())
    assert data["appVersion"] == "1.0.0"
    assert data["version"] == "4.0.0"
    assert new_ver == "4.0.0"


def test_is_breaking_upgrade():
    v = Version.parse
    # Pre-1.0 minor bump is breaking
    assert _is_breaking_upgrade(v("0.25.0"), v("0.26.0")) is True
    # Major bump is breaking
    assert _is_breaking_upgrade(v("0.27.0"), v("1.0.0")) is True
    assert _is_breaking_upgrade(v("1.0.0"), v("2.0.0")) is True
    # Patch bump is not breaking
    assert _is_breaking_upgrade(v("0.26.0"), v("0.26.1")) is False
    assert _is_breaking_upgrade(v("1.0.0"), v("1.0.1")) is False
    # Post-1.0 minor bump is not breaking
    assert _is_breaking_upgrade(v("1.0.0"), v("1.1.0")) is False


def test_write_chart_version_no_change(tmp_path: Path):
    """Chart version unchanged when appVersion is the same."""
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.26.0\nversion: 1.0.5\nname: zero-cache\n")
    result = write_chart_version(chart, Version.parse("0.26.0"))
    data = yaml.safe_load(chart.read_text())
    assert data["appVersion"] == "0.26.0"
    assert data["version"] == "1.0.5"
    assert result is None


def test_read_chart_oci_version(tmp_path: Path):
    chart = tmp_path / "Chart.yaml"
    chart.write_text("apiVersion: v2\nappVersion: 0.26.0\nversion: 1.0.5\nname: zero-cache\n")
    assert read_chart_oci_version(chart) == "1.0.5"
