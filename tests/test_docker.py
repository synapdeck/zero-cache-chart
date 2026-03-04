import responses
from semver.version import Version
from zero_cache_chart.docker import fetch_docker_versions


@responses.activate
def test_fetch_docker_versions_basic():
    responses.add(
        responses.GET,
        "https://hub.docker.com/v2/repositories/rocicorp/zero/tags/",
        json={
            "count": 3,
            "next": None,
            "results": [
                {"name": "0.25.0"},
                {"name": "0.26.0"},
                {"name": "latest"},
                {"name": "0.26.1-canary.4"},
            ],
        },
    )

    versions = fetch_docker_versions("rocicorp/zero")
    assert versions == [
        Version.parse("0.25.0"),
        Version.parse("0.26.0"),
        Version.parse("0.26.1-canary.4"),
    ]


@responses.activate
def test_fetch_docker_versions_pagination():
    responses.add(
        responses.GET,
        "https://hub.docker.com/v2/repositories/rocicorp/zero/tags/",
        json={
            "count": 2,
            "next": "https://hub.docker.com/v2/repositories/rocicorp/zero/tags/?page=2",
            "results": [{"name": "0.25.0"}],
        },
    )
    responses.add(
        responses.GET,
        "https://hub.docker.com/v2/repositories/rocicorp/zero/tags/?page=2",
        json={
            "count": 2,
            "next": None,
            "results": [{"name": "0.26.0"}],
        },
    )

    versions = fetch_docker_versions("rocicorp/zero")
    assert versions == [Version.parse("0.25.0"), Version.parse("0.26.0")]
