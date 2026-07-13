"""Tests for the Docker plugin (Dockerfile FROM parsing)."""

import pytest

from backend.data_sources.docker_plugin import DockerPlugin


@pytest.fixture
def plugin():
    return DockerPlugin()


class TestDockerPlugin:
    """Test suite for DockerPlugin."""

    def test_plugin_ecosystem(self, plugin):
        assert plugin.ecosystem == "docker"

    def test_manifest_patterns(self, plugin):
        globs = [m.glob for m in plugin.manifests]
        assert "Dockerfile" in globs
        assert "Dockerfile.*" in globs

    def test_parse_simple_from(self):
        content = "FROM python:3.11-slim"
        result = DockerPlugin.parse_dockerfile(content)
        assert result == [{"name": "python", "version": "3.11-slim", "_ecosystem": "docker"}]

    def test_parse_from_with_as(self):
        content = "FROM node:18-alpine AS builder"
        result = DockerPlugin.parse_dockerfile(content)
        assert result == [{"name": "node", "version": "18-alpine", "_ecosystem": "docker"}]

    def test_parse_from_scratch(self):
        content = "FROM scratch"
        result = DockerPlugin.parse_dockerfile(content)
        assert result == []

    def test_parse_multi_stage(self):
        content = "FROM python:3.11-slim AS base\nFROM node:18-alpine AS builder\nCOPY --from=builder /app ."
        result = DockerPlugin.parse_dockerfile(content)
        assert len(result) == 2
        assert result[0] == {"name": "python", "version": "3.11-slim", "_ecosystem": "docker"}
        assert result[1] == {"name": "node", "version": "18-alpine", "_ecosystem": "docker"}

    def test_parse_with_platform(self):
        content = "FROM --platform=linux/amd64 python:3.11"
        result = DockerPlugin.parse_dockerfile(content)
        assert result == [{"name": "python", "version": "3.11", "_ecosystem": "docker"}]

    def test_parse_registry_url(self):
        content = "FROM registry.example.com/myimage:1.0"
        result = DockerPlugin.parse_dockerfile(content)
        assert result == [
            {"name": "registry.example.com/myimage", "version": "1.0", "_ecosystem": "docker"}
        ]

    def test_parse_no_tag(self):
        content = "FROM ubuntu"
        result = DockerPlugin.parse_dockerfile(content)
        assert result == [{"name": "ubuntu", "version": "latest", "_ecosystem": "docker"}]

    def test_parse_digest(self):
        content = "FROM python@sha256:abc123"
        result = DockerPlugin.parse_dockerfile(content)
        assert result == [{"name": "python", "version": "sha256:abc123", "_ecosystem": "docker"}]

    def test_parse_no_from(self):
        content = "RUN apt-get update\nCOPY . /app\nCMD python app.py"
        result = DockerPlugin.parse_dockerfile(content)
        assert result == []

    def test_parse_empty(self):
        result = DockerPlugin.parse_dockerfile("")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_package_info_stub(self, plugin):
        info = await plugin.get_package_info("python")
        assert info == {
            "name": "python",
            "ecosystem": "docker",
            "version": "latest",
            "versions": [{"version": "latest"}],
            "dependencies": {},
            "description": "Docker image (no remote metadata available)",
        }
