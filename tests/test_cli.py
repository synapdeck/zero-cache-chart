from pathlib import Path

from click.testing import CliRunner
from zero_cache_chart.cli import main, _reconcile_chart_nix


def test_main_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "zero-cache Helm chart version manager" in result.output


def test_update_help():
    runner = CliRunner()
    result = runner.invoke(main, ["update", "--help"])
    assert result.exit_code == 0
    assert "--docker-image" in result.output
    assert "--oci-repo" in result.output
    assert "--dry-run" in result.output
    assert "--branch-retention" not in result.output


def test_prune_help():
    runner = CliRunner()
    result = runner.invoke(main, ["prune", "--help"])
    assert result.exit_code == 0
    assert "--oci-repo" in result.output
    assert "--max-age-days" in result.output
    assert "--all" in result.output


def test_cleanup_all_help():
    runner = CliRunner()
    result = runner.invoke(main, ["cleanup-all", "--help"])
    assert result.exit_code == 0
    assert "--oci-repo" in result.output
    assert "--dry-run" in result.output


def test_update_requires_docker_image():
    runner = CliRunner()
    result = runner.invoke(main, ["update", "--oci-repo=foo/bar"])
    assert result.exit_code != 0
    assert "Missing option" in result.output or "required" in result.output.lower()


def test_prune_requires_oci_repo():
    runner = CliRunner()
    result = runner.invoke(main, ["prune"])
    assert result.exit_code != 0
    assert "Missing option" in result.output or "required" in result.output.lower()


def _write_nix(tmp_path: Path, version: str) -> Path:
    nix = tmp_path / "chart.nix"
    nix.write_text(f'{{\n  version = "{version}";\n  chartHash = "sha256-old";\n}}\n')
    return nix


def test_reconcile_chart_nix_hashes_fresh_package(tmp_path: Path, mocker):
    nix = _write_nix(tmp_path, "2.1.1")
    package = tmp_path / "zero-cache-2.1.2.tgz"
    mocker.patch("zero_cache_chart.cli.sri_hash", return_value="sha256-new")
    pull = mocker.patch("zero_cache_chart.cli.pull_chart")

    assert _reconcile_chart_nix(nix, "ghcr.io", "org/repo", "2.1.2", package) is True
    assert 'version = "2.1.2"' in nix.read_text()
    assert 'chartHash = "sha256-new"' in nix.read_text()
    pull.assert_not_called()


def test_reconcile_chart_nix_stale_pulls_from_registry(tmp_path: Path, mocker):
    """When the package already exists in the registry, a stale chart.nix is
    reconciled by pulling the published chart and hashing it."""
    nix = _write_nix(tmp_path, "2.1.1")
    pull = mocker.patch("zero_cache_chart.cli.pull_chart", return_value=tmp_path / "pulled.tgz")
    mocker.patch("zero_cache_chart.cli.sri_hash", return_value="sha256-new")

    assert _reconcile_chart_nix(nix, "ghcr.io", "org/repo", "2.1.2", None) is True
    assert 'version = "2.1.2"' in nix.read_text()
    assert 'chartHash = "sha256-new"' in nix.read_text()
    assert pull.call_args.args[:3] == ("ghcr.io", "org/repo", "2.1.2")


def test_reconcile_chart_nix_up_to_date_is_noop(tmp_path: Path, mocker):
    nix = _write_nix(tmp_path, "2.1.2")
    pull = mocker.patch("zero_cache_chart.cli.pull_chart")

    assert _reconcile_chart_nix(nix, "ghcr.io", "org/repo", "2.1.2", None) is False
    assert 'chartHash = "sha256-old"' in nix.read_text()
    pull.assert_not_called()


def test_reconcile_chart_nix_missing_file(tmp_path: Path):
    nix = tmp_path / "chart.nix"
    assert _reconcile_chart_nix(nix, "ghcr.io", "org/repo", "2.1.2", None) is False
