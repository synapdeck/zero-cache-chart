from zero_cache_chart.oci import _parse_package_versions


def test_parse_package_versions():
    data = [
        {"id": 1, "metadata": {"container": {"tags": ["0.26.0"]}}, "created_at": "2026-01-01T00:00:00Z"},
        {"id": 2, "metadata": {"container": {"tags": []}}, "created_at": "2026-01-01T00:00:00Z"},
        {"id": 3, "metadata": {"container": {"tags": []}}, "created_at": "2025-01-01T00:00:00Z"},
    ]
    tagged, untagged = _parse_package_versions(data)
    assert len(tagged) == 1
    assert len(untagged) == 2


def test_parse_package_versions_empty():
    tagged, untagged = _parse_package_versions([])
    assert tagged == []
    assert untagged == []


def test_parse_package_versions_all_tagged():
    data = [
        {"id": 1, "metadata": {"container": {"tags": ["0.26.0"]}}, "created_at": "2026-01-01T00:00:00Z"},
        {"id": 2, "metadata": {"container": {"tags": ["0.25.0"]}}, "created_at": "2026-01-01T00:00:00Z"},
    ]
    tagged, untagged = _parse_package_versions(data)
    assert len(tagged) == 2
    assert len(untagged) == 0
