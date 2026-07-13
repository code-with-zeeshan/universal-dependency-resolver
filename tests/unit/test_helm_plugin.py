"""Unit tests for the Helm ecosystem plugin."""

import json
import pytest

from backend.data_sources.helm_plugin import HelmPlugin


class TestParseChartYaml:
    """Tests for HelmPlugin.parse_chart_yaml()."""

    def test_with_dependencies(self):
        content = """\
apiVersion: v2
name: my-chart
dependencies:
  - name: redis
    version: 16.0.0
    repository: https://charts.bitnami.com/bitnami
  - name: postgresql
    version: 12.0.0
    repository: https://charts.bitnami.com/bitnami
"""
        result = HelmPlugin.parse_chart_yaml(content)
        assert len(result) == 2
        assert result[0]["name"] == "redis"
        assert result[0]["version"] == "16.0.0"
        assert result[0]["_ecosystem"] == "helm"
        assert result[1]["name"] == "postgresql"
        assert result[1]["version"] == "12.0.0"

    def test_without_dependencies(self):
        content = """\
apiVersion: v2
name: my-chart
description: A simple chart
"""
        result = HelmPlugin.parse_chart_yaml(content)
        assert result == []

    def test_empty_content(self):
        result = HelmPlugin.parse_chart_yaml("")
        assert result == []

    def test_dependency_without_version(self):
        content = """\
dependencies:
  - name: redis
    version:
  - name: nginx
"""
        result = HelmPlugin.parse_chart_yaml(content)
        assert len(result) == 2
        assert result[0]["version"] == "*"
        assert result[1]["version"] == "*"


class TestParseChartLock:
    """Tests for HelmPlugin.parse_chart_lock()."""

    def test_basic_lock(self):
        data = {
            "dependencies": [
                {"name": "redis", "version": "16.0.0"},
                {"name": "postgresql", "version": "12.0.0"},
            ]
        }
        result = HelmPlugin.parse_chart_lock(json.dumps(data))
        assert len(result) == 2
        assert result["redis"]["version"] == "16.0.0"
        assert result["postgresql"]["version"] == "12.0.0"

    def test_empty_lock(self):
        result = HelmPlugin.parse_chart_lock(json.dumps({"dependencies": []}))
        assert result == {}

    def test_invalid_json(self):
        result = HelmPlugin.parse_chart_lock("not json")
        assert result == {}


class TestHelmPlugin:
    """Tests for HelmPlugin class metadata and stubs."""

    def test_ecosystem_name(self):
        assert HelmPlugin.ecosystem == "helm"

    def test_manifest_patterns(self):
        assert len(HelmPlugin.manifests) == 1
        assert HelmPlugin.manifests[0].glob == "Chart.yaml"
        assert HelmPlugin.manifests[0].parser == "parse_chart_yaml"

    def test_lock_file_pattern(self):
        assert len(HelmPlugin.lock_files) == 1
        assert HelmPlugin.lock_files[0].glob == "Chart.lock"
        assert HelmPlugin.lock_files[0].parser == "parse_chart_lock"

    @pytest.mark.asyncio
    async def test_get_package_info_stub(self):
        plugin = HelmPlugin(cache_ttl=0)
        result = await plugin.get_package_info("redis")
        assert result is not None
        assert result["name"] == "redis"
        assert result["ecosystem"] == "helm"
        assert result["version"] == "latest"
