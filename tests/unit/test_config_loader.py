"""Regression tests for project config loader — workspace, cross-eco deps, profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.core.config_loader import ProjectConfig
from backend.core.utils import make_purl


class TestProjectConfig:
    def test_no_config_file(self, tmp_path: Path):
        cfg = ProjectConfig(tmp_path)
        cfg.load()
        assert cfg.cross_deps == []
        assert cfg.profiles == {}
        assert cfg.workspaces == {}

    def test_load_full_config(self, tmp_path: Path):
        data = {
            "cross_deps": [
                {"from": "lodash@npm", "dep": "click@pypi", "constraint": ">=8.0"},
            ],
            "profiles": {
                "production": ["pypi/flask", "npm/lodash"],
                "dev": ["*/*"],
            },
            "workspaces": {
                "frontend": "./frontend",
                "backend": "./backend",
            },
        }
        (tmp_path / "udr.json").write_text(json.dumps(data))
        cfg = ProjectConfig(tmp_path)
        cfg.load()
        assert len(cfg.cross_deps) == 1
        assert cfg.cross_deps[0]["dep"] == "click@pypi"
        assert "production" in cfg.profiles
        assert "dev" in cfg.profiles
        assert cfg.workspaces["frontend"] == "./frontend"
        assert cfg.workspaces["backend"] == "./backend"

    def test_invalid_json_does_not_crash(self, tmp_path: Path):
        (tmp_path / "udr.json").write_text("not valid json")
        cfg = ProjectConfig(tmp_path)
        cfg.load()  # Should not raise

    def test_profile_includes(self, tmp_path: Path):
        data = {
            "profiles": {
                "production": ["pypi/click", "npm"],
            },
        }
        (tmp_path / "udr.json").write_text(json.dumps(data))
        cfg = ProjectConfig(tmp_path)
        cfg.load()
        assert cfg.profile_includes("pypi", "click", profile="production")
        assert cfg.profile_includes("npm", "express", profile="production")
        assert not cfg.profile_includes("go", "some-pkg", profile="production")

    def test_no_profile_includes_all(self, tmp_path: Path):
        cfg = ProjectConfig(tmp_path)
        assert cfg.profile_includes("pypi", "anything")  # True when no profile set

    def test_ensure_loaded(self, tmp_path: Path):
        cfg = ProjectConfig(tmp_path)
        assert not cfg._loaded
        cfg.ensure_loaded()
        assert cfg._loaded


class TestMakePurl:
    def test_basic_purl(self):
        result = make_purl("requests", "2.25.1", "pypi")
        assert result == "pkg:pypi/requests@2.25.1"

    def test_npm_purl(self):
        result = make_purl("express", "4.18.0", "npm")
        assert result == "pkg:npm/express@4.18.0"

    def test_cargo_purl(self):
        result = make_purl("serde", "1.0.0", "crates")
        assert result == "pkg:cargo/serde@1.0.0"

    def test_scoped_npm_purl(self):
        result = make_purl("@babel/core", "7.0.0", "npm")
        assert "pkg:npm/" in result
        assert "%40" in result  # @ encoded
        assert "%2F" in result  # / encoded

    def test_unknown_ecosystem(self):
        result = make_purl("foo", "1.0", "unknown")
        assert result == "pkg:unknown/foo@1.0"

    def test_no_version(self):
        result = make_purl("requests", "", "pypi")
        assert result == "pkg:pypi/requests"

    def test_go_purl(self):
        result = make_purl("github.com/pkg/errors", "0.9.1", "gomodules")
        assert "golang" in result
        assert "%2F" in result


class TestCrossEcoDeps:
    def test_config_declares_cross_deps(self, tmp_path: Path):
        data = {
            "cross_deps": [
                {"from": "lodash@npm", "dep": "click@pypi", "constraint": ">=8.0"},
                {"from": "click@pypi", "dep": "somedep@cargo", "constraint": "1.0"},
            ],
        }
        (tmp_path / "udr.json").write_text(json.dumps(data))
        cfg = ProjectConfig(tmp_path)
        cfg.load()
        assert len(cfg.cross_deps) == 2

    def test_missing_cross_deps_is_empty(self, tmp_path: Path):
        (tmp_path / "udr.json").write_text("{}")
        cfg = ProjectConfig(tmp_path)
        cfg.load()
        assert cfg.cross_deps == []


class TestWorkspaceConfig:
    def test_workspace_config_loaded(self, tmp_path: Path):
        data = {
            "workspaces": {
                "frontend": "./packages/frontend",
                "backend": "./packages/backend",
                "shared": "./packages/shared",
            },
        }
        (tmp_path / "udr.json").write_text(json.dumps(data))
        cfg = ProjectConfig(tmp_path)
        cfg.load()
        assert len(cfg.workspaces) == 3
        assert cfg.workspaces["frontend"] == "./packages/frontend"

    def test_no_workspaces(self, tmp_path: Path):
        cfg = ProjectConfig(tmp_path)
        cfg.load()
        assert cfg.workspaces == {}
