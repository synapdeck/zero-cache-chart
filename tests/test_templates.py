"""Render the chart with helm and assert on the resulting manifests."""

import subprocess
from pathlib import Path

import pytest
import yaml

CHART = Path(__file__).resolve().parent.parent
UPSTREAM_URL = "common.database.upstream.url.value=postgres://t:t@h/d"

# Each component's workload kind, name suffix, and the values key holding its
# own extraEnv/extraEnvFrom.
COMPONENTS = [
    ("Deployment", "zero-cache", "singleNode", ["--set", "singleNode.enabled=true"]),
    ("StatefulSet", "zero-cache-replication-manager", "replicationManager", []),
    ("StatefulSet", "zero-cache-view-syncer", "viewSyncer", []),
]


def render(*args: str) -> str:
    result = subprocess.run(
        ["helm", "template", "z", str(CHART), "--set", UPSTREAM_URL, *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def workload(rendered: str, kind: str, name: str) -> dict:
    for doc in yaml.safe_load_all(rendered):
        if doc and doc.get("kind") == kind and doc["metadata"]["name"].endswith(name):
            return doc
    raise AssertionError(f"no {kind} ending in {name!r} in rendered output")


def main_container(rendered: str, kind: str, name: str) -> dict:
    return workload(rendered, kind, name)["spec"]["template"]["spec"]["containers"][0]


@pytest.mark.parametrize("kind,name,component,extra_args", COMPONENTS)
def test_extra_env_empty_is_a_no_op(kind, name, component, extra_args):
    """Omitted and explicitly-empty extraEnv render byte-identical output."""
    baseline = render(*extra_args)
    explicit = render(
        *extra_args,
        "--set-json", f'{{"{component}":{{"extraEnv":[],"extraEnvFrom":[]}}}}',
        "--set-json", '{"common":{"extraEnv":[],"extraEnvFrom":[]}}',
    )
    assert baseline == explicit
    assert "envFrom" not in main_container(baseline, kind, name)


@pytest.mark.parametrize("kind,name,component,extra_args", COMPONENTS)
def test_extra_env_appends_in_order(kind, name, component, extra_args):
    """Entries land after the chart's own env, common first, in listed order."""
    baseline_env = main_container(render(*extra_args), kind, name)["env"]
    env = main_container(
        render(
            *extra_args,
            "--set", "common.extraEnv[0].name=COMMON_ONE",
            "--set", "common.extraEnv[0].value=c1",
            "--set", f"{component}.extraEnv[0].name=OWN_ONE",
            "--set", f"{component}.extraEnv[0].value=o1",
            "--set", f"{component}.extraEnv[1].name=OWN_TWO",
            "--set", f"{component}.extraEnv[1].value=o2",
        ),
        kind,
        name,
    )["env"]

    assert env[: len(baseline_env)] == baseline_env, "chart env must be untouched"
    assert env[len(baseline_env):] == [
        {"name": "COMMON_ONE", "value": "c1"},
        {"name": "OWN_ONE", "value": "o1"},
        {"name": "OWN_TWO", "value": "o2"},
    ]


@pytest.mark.parametrize("kind,name,component,extra_args", COMPONENTS)
def test_extra_env_overrides_chart_value_last(kind, name, component, extra_args):
    """A duplicate name is appended last, so Kubernetes' last-wins rule applies."""
    env = main_container(
        render(
            *extra_args,
            "--set", f"{component}.extraEnv[0].name=ZERO_LOG_LEVEL",
            "--set", f"{component}.extraEnv[0].value=debug",
        ),
        kind,
        name,
    )
    entries = [e for e in env["env"] if e["name"] == "ZERO_LOG_LEVEL"]
    assert len(entries) == 2
    assert entries[-1]["value"] == "debug"


@pytest.mark.parametrize("kind,name,component,extra_args", COMPONENTS)
def test_extra_env_from_sources(kind, name, component, extra_args):
    container = main_container(
        render(
            *extra_args,
            "--set", "common.extraEnvFrom[0].configMapRef.name=common-cm",
            "--set", f"{component}.extraEnvFrom[0].secretRef.name=own-secret",
        ),
        kind,
        name,
    )
    assert container["envFrom"] == [
        {"configMapRef": {"name": "common-cm"}},
        {"secretRef": {"name": "own-secret"}},
    ]


def test_extra_env_is_scoped_to_its_own_component():
    """A component's extraEnv does not leak into the other component."""
    rendered = render(
        "--set", "viewSyncer.extraEnv[0].name=VS_ONLY",
        "--set", "viewSyncer.extraEnv[0].value=v1",
    )
    vs = main_container(rendered, "StatefulSet", "zero-cache-view-syncer")
    rm = main_container(rendered, "StatefulSet", "zero-cache-replication-manager")
    assert "VS_ONLY" in [e["name"] for e in vs["env"]]
    assert "VS_ONLY" not in [e["name"] for e in rm["env"]]


def test_extra_env_skips_init_containers():
    """extraEnv targets the zero-cache container only, not init containers."""
    rendered = render(
        "--set", "common.extraEnv[0].name=COMMON_ONE",
        "--set", "common.extraEnv[0].value=c1",
    )
    pod = workload(rendered, "StatefulSet", "zero-cache-view-syncer")["spec"]["template"]["spec"]
    for init in pod.get("initContainers", []):
        assert "COMMON_ONE" not in [e["name"] for e in init.get("env", [])]
