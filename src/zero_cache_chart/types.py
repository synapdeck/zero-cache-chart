from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


class CommandError(Exception):
    def __init__(self, cmd: list[str], result: CommandResult):
        self.cmd = cmd
        self.result = result
        super().__init__(
            f"Command {' '.join(cmd)} failed with exit code {result.returncode}: {result.stderr}"
        )


def run(cmd: list[str], *, check: bool = True) -> CommandResult:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    result = CommandResult(
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        returncode=proc.returncode,
    )
    if check and result.returncode != 0:
        raise CommandError(cmd, result)
    return result


@dataclass
class VersionManagementResult:
    main_updated: bool = False
    created_tags: list[str] = field(default_factory=list)
    pushed_oci_packages: list[str] = field(default_factory=list)
    current_version: str | None = None
