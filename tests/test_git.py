import subprocess
from pathlib import Path
from zero_cache_chart.git import (
    Git,
    parse_major_minor,
)


def test_parse_major_minor():
    assert parse_major_minor("v0.26") == (0, 26)
    assert parse_major_minor("v1.3") == (1, 3)
    assert parse_major_minor("not-a-branch") is None


def init_repo(path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("test")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    return path


def test_git_current_branch(tmp_path: Path):
    repo = init_repo(tmp_path)
    git = Git(cwd=repo)
    branch = git.current_branch()
    assert branch in ("main", "master")


def test_git_create_tag(tmp_path: Path):
    repo = init_repo(tmp_path)
    git = Git(cwd=repo)
    git.create_tag("v0.1.0")
    result = subprocess.run(["git", "tag", "-l"], cwd=repo, capture_output=True, text=True)
    assert "v0.1.0" in result.stdout


def test_git_force_tag(tmp_path: Path):
    repo = init_repo(tmp_path)
    git = Git(cwd=repo)
    git.create_tag("v0.1.0")
    git.create_tag("v0.1.0", force=True)


def test_git_tag_exists(tmp_path: Path):
    repo = init_repo(tmp_path)
    git = Git(cwd=repo)
    assert git.tag_exists("v0.1.0") is False
    git.create_tag("v0.1.0")
    assert git.tag_exists("v0.1.0") is True
