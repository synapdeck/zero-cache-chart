from pathlib import Path
from semver.version import Version
from zero_cache_chart.chart import read_chart_version, write_chart_version


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
    chart.write_text("apiVersion: v2\nappVersion: 0.25.0\nversion: 0.25.0\nname: zero-cache\n")
    write_chart_version(chart, Version.parse("0.26.0"))
    ver = read_chart_version(chart)
    assert ver == Version.parse("0.26.0")
