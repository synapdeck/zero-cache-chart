from click.testing import CliRunner
from zero_cache_chart.cli import main


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
