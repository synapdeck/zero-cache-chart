from __future__ import annotations

import re
import subprocess
from pathlib import Path

from zero_cache_chart.types import CommandResult, CommandError


def parse_major_minor(branch: str) -> tuple[int, int] | None:
    match = re.search(r"v(\d+)\.(\d+)", branch)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)))


class Git:
    def __init__(self, cwd: Path | None = None):
        self.cwd = cwd

    def _run(self, *args: str, check: bool = True) -> CommandResult:
        cmd = ["git", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=self.cwd)
        result = CommandResult(
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
            returncode=proc.returncode,
        )
        if check and result.returncode != 0:
            raise CommandError(cmd, result)
        return result

    def current_branch(self) -> str:
        return self._run("branch", "--show-current").stdout

    def checkout(self, branch: str) -> None:
        self._run("checkout", branch)

    def checkout_new(self, branch: str) -> None:
        self._run("checkout", "-b", branch)

    def fetch(self) -> None:
        self._run("fetch", "origin")

    def pull(self, branch: str) -> None:
        self._run("pull", "origin", branch)

    def push(self, branch: str) -> None:
        self._run("push", "origin", branch)

    def add(self, *paths: str) -> None:
        self._run("add", *paths)

    def commit(self, message: str) -> None:
        self._run("commit", "-m", message)

    def create_tag(self, name: str, *, force: bool = False) -> None:
        args = ["tag"]
        if force:
            args.append("-f")
        args.append(name)
        self._run(*args)

    def push_tag(self, name: str, *, force: bool = False) -> None:
        args = ["push"]
        if force:
            args.append("-f")
        args.extend(["origin", name])
        self._run(*args)

    def tag_exists(self, name: str) -> bool:
        result = self._run("tag", "-l", name)
        return name in result.stdout.split("\n")

    def list_remote_branches(self) -> list[str]:
        result = self._run("branch", "-r")
        return [
            b.strip().removeprefix("origin/")
            for b in result.stdout.split("\n")
            if b.strip() and "HEAD" not in b
        ]


