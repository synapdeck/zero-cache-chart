import pytest
from semver.version import Version
from zero_cache_chart.versions import (
    build_version_map,
    get_latest_version,
    is_stable,
    select_retained_branches,
    classify_version_tag,
    branch_pointer_tags,
)


def v(s: str) -> Version:
    return Version.parse(s)


class TestIsStable:
    def test_stable(self):
        assert is_stable(v("0.26.0")) is True

    def test_canary(self):
        assert is_stable(v("0.26.0-canary.4")) is False

    def test_prerelease(self):
        assert is_stable(v("1.0.0-rc.1")) is False


class TestBuildVersionMap:
    def test_groups_by_major_minor(self):
        versions = [v("0.25.0"), v("0.25.1"), v("0.26.0")]
        vmap = build_version_map(versions)
        assert str(vmap["0.25"]) == "0.25.1"
        assert str(vmap["0.26"]) == "0.26.0"

    def test_empty(self):
        assert build_version_map([]) == {}


class TestGetLatestVersion:
    def test_returns_highest(self):
        versions = [v("0.25.0"), v("0.26.0"), v("0.26.1-canary.4")]
        assert get_latest_version(versions) == v("0.26.1-canary.4")

    def test_empty_returns_none(self):
        assert get_latest_version([]) is None


class TestSelectRetainedBranches:
    def test_retains_last_n(self):
        branches = ["v0.19", "v0.20", "v0.21", "v0.22", "v0.23", "v0.24", "v0.25", "v0.26"]
        retained = select_retained_branches(branches, retain=3)
        assert retained == ["v0.24", "v0.25", "v0.26"]

    def test_fewer_than_n(self):
        branches = ["v0.25", "v0.26"]
        retained = select_retained_branches(branches, retain=3)
        assert retained == ["v0.25", "v0.26"]

    def test_sorts_numerically(self):
        branches = ["v0.9", "v0.20", "v0.10"]
        retained = select_retained_branches(branches, retain=2)
        assert retained == ["v0.10", "v0.20"]


class TestClassifyVersionTag:
    def test_stable(self):
        name, kind = classify_version_tag(v("0.26.0"))
        assert name == "v0.26.0"
        assert kind == "stable"

    def test_canary(self):
        name, kind = classify_version_tag(v("0.26.0-canary.4"))
        assert name == "v0.26.0-canary.4"
        assert kind == "prerelease"


class TestBranchPointerTags:
    def test_stable(self):
        assert branch_pointer_tags(v("0.26.0")) == ["v0.26"]

    def test_canary(self):
        assert branch_pointer_tags(v("0.26.0-canary.4")) == ["v0.26-canary"]
