from __future__ import annotations

import requests
from semver.version import Version


def fetch_docker_versions(docker_image: str) -> list[Version]:
    url: str | None = (
        f"https://hub.docker.com/v2/repositories/{docker_image}/tags/?page_size=100"
    )
    versions: list[Version] = []

    while url:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for tag in data.get("results", []):
            name = tag.get("name", "")
            if Version.is_valid(name):
                versions.append(Version.parse(name))

        url = data.get("next")

    versions.sort()
    return versions
