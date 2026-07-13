"""Unit tests for NixPlugin."""

import pytest

from backend.core.plugin import get_plugin, import_builtin_plugins

import_builtin_plugins()


class TestNixPlugin:
    @pytest.fixture
    def plugin_cls(self):
        cls = get_plugin("nix")
        assert cls is not None, "NixPlugin not registered"
        return cls

    def test_ecosystem(self, plugin_cls):
        assert plugin_cls.ecosystem == "nix"

    def test_display_name(self, plugin_cls):
        assert plugin_cls.display_name == "Nix"

    def test_manifests(self, plugin_cls):
        globs = {mf.glob for mf in plugin_cls.manifests}
        assert "default.nix" in globs
        assert "shell.nix" in globs
        assert "flake.nix" in globs

    def test_lock_files(self, plugin_cls):
        globs = {lf.glob for lf in plugin_cls.lock_files}
        assert "flake.lock" in globs

    def test_manifest_parser_names(self, plugin_cls):
        parsers = {mf.parser for mf in plugin_cls.manifests}
        assert "parse_nix" in parsers

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert inst.ecosystem == "nix"
        assert isinstance(inst, plugin_cls)

    def test_parse_nix_build_inputs(self, plugin_cls):
        content = """{ pkgs, ... }:
pkgs.stdenv.mkDerivation {
  name = "hello";
  buildInputs = [ pkgs.python3 pkgs.curl python3Packages.requests ];
  propagatedBuildInputs = [ pkgs.openssl ];
}
"""
        result = plugin_cls.parse_nix(content)
        names = {(d["name"], d.get("_ecosystem", "nix")) for d in result}
        assert ("python3", "nix") in names, f"Expected python3, got {names}"
        assert ("curl", "nix") in names
        assert ("openssl", "nix") in names
        assert ("requests", "pypi") in names

    def test_parse_nix_empty(self, plugin_cls):
        result = plugin_cls.parse_nix("")
        assert result == []

    def test_parse_nix_no_block(self, plugin_cls):
        result = plugin_cls.parse_nix("{ pkgs }:\npkgs.hello\n")
        assert result == []

    def test_parse_nix_lock(self, plugin_cls):
        content = """{
  "nodes": {
    "root": {
      "inputs": {
        "nixpkgs": "nixpkgs_ref",
        "flake-utils": "flake-utils_ref"
      }
    },
    "nixpkgs_ref": {
      "locked": {
        "rev": "abc123def456",
        "narHash": "sha256-xyz"
      },
      "original": {
        "id": "nixpkgs"
      }
    },
    "flake-utils_ref": {
      "locked": {
        "rev": "789012345678",
        "narHash": "sha256-abc"
      },
      "original": {
        "id": "flake-utils"
      }
    }
  }
}
"""
        result = plugin_cls.parse_nix_lock(content)
        assert "nixpkgs" in result
        assert "flake-utils" in result
        assert result["nixpkgs"]["version"] == "abc123def456"

    def test_parse_nix_lock_empty(self, plugin_cls):
        result = plugin_cls.parse_nix_lock("{}")
        assert result == {}

    def test_parse_nix_lock_invalid(self, plugin_cls):
        result = plugin_cls.parse_nix_lock("not-json")
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_package_info(self, plugin_cls):
        inst = plugin_cls()
        result = await inst.get_package_info("hello")
        assert result is not None
        assert result["ecosystem"] == "nix"
        assert result["version"] == "latest"
