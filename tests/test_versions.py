from semver.version import Version
from zero_cache_chart.versions import (
    build_version_map,
    get_latest_stable,
    is_stable,
    classify_version_tag,
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


class TestGetLatestStable:
    def test_returns_highest_stable(self):
        versions = [v("0.25.0"), v("0.26.0"), v("0.26.1-canary.4")]
        assert get_latest_stable(versions) == v("0.26.0")

    def test_skips_all_prerelease(self):
        versions = [v("0.26.0-canary.1"), v("0.26.0-canary.4")]
        assert get_latest_stable(versions) is None

    def test_empty_returns_none(self):
        assert get_latest_stable([]) is None


class TestClassifyVersionTag:
    def test_stable(self):
        name, kind = classify_version_tag(v("0.26.0"))
        assert name == "v0.26.0"
        assert kind == "stable"

    def test_canary(self):
        name, kind = classify_version_tag(v("0.26.0-canary.4"))
        assert name == "v0.26.0-canary.4"
        assert kind == "prerelease"
