"""Contract tests for the EcosystemPlugin system.

Every plugin registered via ``@register_ecosystem`` must pass these tests,
ensuring a consistent data-source interface across all ecosystems.
"""

import inspect
import sys

import pytest

from backend.core.plugin import (
    EcosystemPlugin,
    PluginManifest,
    PluginLockFile,
    get_all_plugins,
    get_plugin,
    import_builtin_plugins,
    list_plugin_manifests,
    register_ecosystem,
)

# Ensure all built-in plugins are loaded
import_builtin_plugins()


def _all_plugin_classes() -> list[type[EcosystemPlugin]]:
    return list(get_all_plugins().values())


# ── Registry tests ────────────────────────────────────────────────────────


class TestPluginRegistry:
    def test_plugins_loaded(self):
        plugins = _all_plugin_classes()
        assert len(plugins) >= 1, "At least one plugin should be registered"

    def test_get_plugin_returns_class(self):
        plugins = _all_plugin_classes()
        for cls in plugins:
            found = get_plugin(cls.ecosystem)
            assert found is cls, f"get_plugin({cls.ecosystem!r}) should return {cls}"

    def test_get_plugin_unknown(self):
        assert get_plugin("nonexistent_ecosystem_xyz") is None

    def test_list_plugin_manifests_returns_triples(self):
        triples = list_plugin_manifests()
        for g, e, p in triples:
            assert isinstance(g, str) and g
            assert isinstance(e, str) and e
            assert isinstance(p, str) and p

    def test_plugin_has_ecosystem(self):
        for cls in _all_plugin_classes():
            assert hasattr(cls, "ecosystem")
            assert isinstance(cls.ecosystem, str) and cls.ecosystem

    def test_plugin_has_display_name(self):
        for cls in _all_plugin_classes():
            assert isinstance(cls.display_name, str)


# ── Plugin contract tests ─────────────────────────────────────────────────


class TestPluginContract:
    """Every plugin passes these tests."""

    @pytest.fixture(params=_all_plugin_classes(), ids=lambda cls: cls.ecosystem)
    def plugin_cls(self, request) -> type[EcosystemPlugin]:
        return request.param

    def test_inherits_ecosystem_plugin(self, plugin_cls):
        assert issubclass(plugin_cls, EcosystemPlugin)

    def test_has_abstract_methods_implemented(self, plugin_cls):
        # get_package_info is the only abstract method
        assert not inspect.isabstract(plugin_cls), (
            f"{plugin_cls.__name__} must implement get_package_info"
        )

    def test_manifests_are_plugin_manifest_instances(self, plugin_cls):
        for mf in plugin_cls.manifests:
            assert isinstance(mf, PluginManifest)
            assert isinstance(mf.glob, str) and mf.glob
            assert isinstance(mf.parser, str) and mf.parser

    def test_lock_files_are_plugin_lock_file_instances(self, plugin_cls):
        for lf in plugin_cls.lock_files:
            assert isinstance(lf, PluginLockFile)
            assert isinstance(lf.glob, str) and lf.glob
            assert isinstance(lf.parser, str) and lf.parser

    def test_parser_methods_exist(self, plugin_cls):
        for mf in plugin_cls.manifests:
            method = getattr(plugin_cls, mf.parser, None)
            assert method is not None, f"{plugin_cls.__name__} missing parser method {mf.parser!r}"
            assert callable(method)

    def test_lock_parser_methods_exist(self, plugin_cls):
        for lf in plugin_cls.lock_files:
            method = getattr(plugin_cls, lf.parser, None)
            assert method is not None, (
                f"{plugin_cls.__name__} missing lock parser method {lf.parser!r}"
            )
            assert callable(method)

    def test_can_instantiate(self, plugin_cls):
        inst = plugin_cls()
        assert isinstance(inst, plugin_cls)
        assert inst.ecosystem == plugin_cls.ecosystem

    def test_get_artifact_hash_returns_none_or_dict(self, plugin_cls):
        inst = plugin_cls()
        import asyncio

        result = asyncio.run(inst.get_artifact_hash("test-pkg", "1.0.0"))
        assert result is None or isinstance(result, dict), (
            f"get_artifact_hash should return None or dict, got {type(result)}"
        )

    def test_update_manifest_present(self, plugin_cls):
        inst = plugin_cls()
        # update_manifest returns None when not overridden (fallback)
        for mf in plugin_cls.manifests:
            update_method = getattr(plugin_cls, f"update_{mf.parser}", None)
            if update_method:
                assert callable(update_method)


# ── Ecosystem-Specific Tests ──────────────────────────────────────────────


@pytest.fixture(params=["hex", "haskell", "pub", "gradle", "swift"])
def any_plugin_cls(request):
    cls = get_plugin(request.param)
    assert cls is not None, f"Plugin {request.param!r} not found"
    return cls


class TestEcosystemParsers:
    """Generic parser tests run against every plugin."""

    def test_has_manifest_parser(self, any_plugin_cls):
        for mf in any_plugin_cls.manifests:
            method = getattr(any_plugin_cls, mf.parser, None)
            assert method is not None, f"Missing parser {mf.parser}"
            assert callable(method)

    def test_has_lock_parser(self, any_plugin_cls):
        for lf in any_plugin_cls.lock_files:
            method = getattr(any_plugin_cls, lf.parser, None)
            assert method is not None, f"Missing lock parser {lf.parser}"
            assert callable(method)

    def test_has_update_method(self, any_plugin_cls):
        for mf in any_plugin_cls.manifests:
            update_method = getattr(any_plugin_cls, f"update_{mf.parser}", None)
            if update_method is not None:
                assert callable(update_method)

    @pytest.mark.asyncio
    async def test_get_package_info_no_crash(self, any_plugin_cls):
        inst = any_plugin_cls()
        result = await inst.get_package_info(
            "this_package_definitely_does_not_exist_xyz", include_versions=True
        )
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_package_versions_no_crash(self, any_plugin_cls):
        inst = any_plugin_cls()
        result = await inst.get_package_versions("this_package_definitely_does_not_exist_xyz")
        assert isinstance(result, list)


# ── HexPlugin-specific tests ──────────────────────────────────────────────


class TestHexPlugin:
    """Validates the Hex-built-in plugin works correctly."""

    @pytest.fixture
    def hex_plugin(self):
        cls = get_plugin("hex")
        assert cls is not None
        return cls

    def test_hex_ecosystem(self, hex_plugin):
        assert hex_plugin.ecosystem == "hex"

    def test_hex_manifests(self, hex_plugin):
        assert any(mf.glob == "mix.exs" for mf in hex_plugin.manifests)

    def test_hex_lock_files(self, hex_plugin):
        assert any(lf.glob == "mix.lock" for lf in hex_plugin.lock_files)

    def test_parse_mix_exs(self, hex_plugin):
        content = """defmodule MyApp.MixProject do
  def project do
    [
      app: :my_app,
      version: "0.1.0",
      deps: deps()
    ]
  end

  defp deps do
    [
      {:phoenix, "~> 1.7"},
      {:ecto_sql, "~> 3.10"},
      {:jason, ">= 1.0"},
    ]
  end
end
"""
        result = hex_plugin.parse_mix_exs(content)
        names = {d["name"] for d in result}
        assert "phoenix" in names
        assert "ecto_sql" in names
        assert "jason" in names

    def test_parse_mix_lock(self, hex_plugin):
        content = """%{
  "phoenix": {:hex, :phoenix, "1.7.12", [...], ["castore", "jason"], "hex"},
  "jason": {:hex, :jason, "1.4.1", [...], [], "hex"},
}
"""
        result = hex_plugin.parse_mix_lock(content)
        assert "phoenix" in result
        assert result["phoenix"]["version"] == "1.7.12"
        assert "jason" in result

    def test_update_mix_exs(self, hex_plugin):
        content = """{:phoenix, "~> 1.7"},
{:ecto_sql, "~> 3.10"},
"""
        result = hex_plugin.update_mix_exs(content, "phoenix", "1.7.12")
        assert result is not None
        assert "'1.7.12'" in result or '"1.7.12"' in result

    def test_update_mix_exs_not_found(self, hex_plugin):
        content = """{:phoenix, "~> 1.7"},
"""
        result = hex_plugin.update_mix_exs(content, "nonexistent_pkg", "1.0.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_package_info(self, hex_plugin):
        inst = hex_plugin()
        result = await inst.get_package_info(
            "this_package_definitely_does_not_exist_xyz", include_versions=True
        )
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_package_versions(self, hex_plugin):
        inst = hex_plugin()
        result = await inst.get_package_versions("this_package_definitely_does_not_exist_xyz")
        assert isinstance(result, list)


# ── HaskellPlugin-specific tests ──────────────────────────────────────────


class TestHaskellPlugin:
    """Validates the Haskell-built-in plugin works correctly."""

    @pytest.fixture
    def hp(self):
        cls = get_plugin("haskell")
        assert cls is not None
        return cls

    def test_ecosystem(self, hp):
        assert hp.ecosystem == "haskell"

    def test_manifests(self, hp):
        assert any(mf.glob == "*.cabal" for mf in hp.manifests)

    def test_parse_cabal(self, hp):
        content = """name: my-package
build-depends: base >=4.12 && <5,
               text >=1.2,
               containers
"""
        result = hp.parse_cabal(content)
        names = {d["name"] for d in result}
        assert "base" in names
        assert "text" in names
        assert "containers" in names

    def test_update_cabal(self, hp):
        content = "  build-depends: base >=4.12, text >=1.2\n"
        result = hp.update_cabal(content, "base", "4.18.0")
        assert result is not None
        assert "base 4.18.0" in result

    def test_update_cabal_not_found(self, hp):
        result = hp.update_cabal("nothing here", "nonexistent", "1.0")
        assert result is None


# ── PubPlugin-specific tests ──────────────────────────────────────────────


class TestPubPlugin:
    """Validates the Pub.dev plugin works correctly."""

    @pytest.fixture
    def pp(self):
        cls = get_plugin("pub")
        assert cls is not None
        return cls

    def test_ecosystem(self, pp):
        assert pp.ecosystem == "pub"

    def test_manifests(self, pp):
        assert any(mf.glob == "pubspec.yaml" for mf in pp.manifests)

    def test_parse_pubspec(self, pp):
        content = """name: my_package
dependencies:
  http: ^0.13.0
  riverpod: ^2.0.0
dev_dependencies:
  test: ^1.16.0
"""
        result = pp.parse_pubspec(content)
        names = {d["name"] for d in result}
        assert "http" in names
        assert "riverpod" in names
        assert "test" in names

    def test_parse_pubspec_skips_flutter(self, pp):
        content = """dependencies:
  flutter:
    sdk: flutter
  http: ^0.13.0
"""
        result = pp.parse_pubspec(content)
        names = {d["name"] for d in result}
        assert "http" in names
        assert "flutter" not in names

    def test_update_pubspec(self, pp):
        content = "  http: ^0.13.0\n  riverpod: ^2.0.0\n"
        result = pp.update_pubspec(content, "http", "1.0.0")
        assert result is not None
        assert "http: 1.0.0" in result

    def test_update_pubspec_not_found(self, pp):
        result = pp.update_pubspec("nothing here", "nonexistent", "1.0")
        assert result is None


# ── GradlePlugin-specific tests ───────────────────────────────────────────


class TestGradlePlugin:
    """Validates the Gradle plugin works correctly."""

    @pytest.fixture
    def gp(self):
        cls = get_plugin("gradle")
        assert cls is not None
        return cls

    def test_ecosystem(self, gp):
        assert gp.ecosystem == "gradle"

    def test_manifests(self, gp):
        assert any(mf.glob == "build.gradle" for mf in gp.manifests)
        assert any(mf.glob == "build.gradle.kts" for mf in gp.manifests)

    def test_parse_gradle_map(self, gp):
        content = """dependencies {
    implementation 'com.google.guava:guava:31.1-jre'
    api 'org.slf4j:slf4j-api:2.0.0'
    testImplementation 'junit:junit:4.13.2'
}
"""
        result = gp.parse_gradle(content)
        names = {d["name"] for d in result}
        assert "com.google.guava:guava" in names
        assert "org.slf4j:slf4j-api" in names
        assert "junit:junit" in names

    def test_parse_gradle_func(self, gp):
        content = """dependencies {
    implementation("com.google.guava:guava:31.1-jre")
    api("org.slf4j:slf4j-api:2.0.0")
}
"""
        result = gp.parse_gradle(content)
        assert len(result) >= 2

    def test_update_gradle(self, gp):
        content = "    implementation 'com.google.guava:guava:31.1-jre'\n"
        result = gp.update_gradle(content, "com.google.guava:guava", "32.0.0")
        assert result is not None
        assert "guava:32.0.0" in result

    def test_update_gradle_not_found(self, gp):
        result = gp.update_gradle("no match", "nonexistent:foo", "1.0")
        assert result is None


# ── SwiftPlugin-specific tests ────────────────────────────────────────────


class TestSwiftPlugin:
    """Validates the Swift plugin works correctly."""

    @pytest.fixture
    def sp(self):
        cls = get_plugin("swift")
        assert cls is not None
        return cls

    def test_ecosystem(self, sp):
        assert sp.ecosystem == "swift"

    def test_manifests(self, sp):
        assert any(mf.glob == "Package.swift" for mf in sp.manifests)

    def test_lock_files(self, sp):
        assert any(lf.glob == "Package.resolved" for lf in sp.lock_files)

    def test_parse_package_resolved(self, sp):
        content = """{
  "pins": [
    {
      "identity": "swift-nio",
      "version": "2.62.0",
      "state": {"version": "2.62.0"}
    }
  ]
}
"""
        result = sp.parse_package_resolved(content)
        assert "swift-nio" in result
        assert result["swift-nio"]["version"] == "2.62.0"
