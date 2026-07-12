"""Unit tests for backend/cli/shared.py — manifest update functions and helpers."""

import json

from backend.cli.shared import (
    _build_target_system_info,
    _get_manifest_updater,
    _select_manifests_interactive,
    _update_brewfile,
    _update_build_gradle,
    _update_cabal,
    _update_cargo_toml,
    _update_composer_json,
    _update_environment_yml,
    _update_gemfile,
    _update_gemspec_dependency,
    _update_go_mod,
    _update_mix_exs,
    _update_package_json,
    _update_package_swift,
    _update_packages_config,
    _update_pipfile,
    _update_podfile,
    _update_pom_xml,
    _update_pubspec_yaml,
    _update_pyproject_toml,
    _update_simple,
)


class TestUpdatePackageJson:
    def test_updates_dependencies(self):
        content = json.dumps({"dependencies": {"express": "^4.18.0"}}, indent=2)
        result = _update_package_json(content, "express", "4.18.0")
        assert result is not None
        data = json.loads(result)
        assert data["dependencies"]["express"] == "4.18.0"

    def test_updates_dev_dependencies(self):
        content = json.dumps({"devDependencies": {"typescript": "^5.0"}}, indent=2)
        result = _update_package_json(content, "typescript", "5.4.0")
        assert result is not None
        data = json.loads(result)
        assert data["devDependencies"]["typescript"] == "5.4.0"

    def test_not_found(self):
        content = json.dumps({"dependencies": {"express": "^4.0"}}, indent=2)
        result = _update_package_json(content, "nonexistent", "1.0")
        assert result is None

    def test_invalid_json(self):
        result = _update_package_json("not json", "pkg", "1.0")
        assert result is None


class TestUpdatePubspecYaml:
    def test_updates_dependencies(self):
        content = "name: test\ndependencies:\n  http: ^1.0.0\n"
        result = _update_pubspec_yaml(content, "http", "1.2.0")
        assert result is not None
        assert "http: 1.2.0" in result

    def test_updates_dev_dependencies(self):
        content = "name: test\ndev_dependencies:\n  lints: ^3.0\n"
        result = _update_pubspec_yaml(content, "lints", "3.1.0")
        assert result is not None
        assert "lints: 3.1.0" in result

    def test_not_found(self):
        content = "name: test\ndependencies:\n  http: ^1.0.0\n"
        result = _update_pubspec_yaml(content, "missing", "1.0")
        assert result is None


class TestUpdateGoMod:
    def test_single_line_require(self):
        content = "require github.com/foo/bar v1.0.0\n"
        result = _update_go_mod(content, "github.com/foo/bar", "v1.2.0")
        assert result is not None
        assert "require github.com/foo/bar v1.2.0" in result

    def test_require_block(self):
        content = "require (\n\tgithub.com/foo/bar v1.0.0\n\tgithub.com/baz/qux v2.0.0\n)\n"
        result = _update_go_mod(content, "github.com/foo/bar", "v1.2.0")
        assert result is not None
        assert "github.com/foo/bar v1.2.0" in result
        assert "github.com/baz/qux v2.0.0" in result

    def test_not_found(self):
        content = "require github.com/foo/bar v1.0.0\n"
        result = _update_go_mod(content, "github.com/missing/pkg", "v1.0.0")
        assert result is None


class TestUpdateCargoToml:
    def test_updates_simple_dep(self):
        content = '[dependencies]\nserde = "1.0"\n'
        result = _update_cargo_toml(content, "serde", "1.5.0")
        assert result is not None
        assert 'serde = "1.5.0"' in result

    def test_updates_inline_table(self):
        content = '[dependencies]\nserde = { version = "1.0", features = ["derive"] }\n'
        result = _update_cargo_toml(content, "serde", "1.5.0")
        assert result is not None
        assert 'version = "1.5.0"' in result

    def test_updates_sub_table(self):
        content = '[dependencies.serde]\nversion = "1.0"\n'
        result = _update_cargo_toml(content, "serde", "1.5.0")
        assert result is not None
        assert 'version = "1.5.0"' in result

    def test_not_found(self):
        content = '[dependencies]\nserde = "1.0"\n'
        result = _update_cargo_toml(content, "missing", "1.0")
        assert result is None


class TestUpdateGemfile:
    def test_updates_gem(self):
        content = 'gem "rails", ">= 7.0"\n'
        result = _update_gemfile(content, "rails", "7.1.0")
        assert result is not None
        assert 'gem "rails", "7.1.0"' in result

    def test_updates_single_quoted(self):
        content = "gem 'rails', '>= 7.0'\n"
        result = _update_gemfile(content, "rails", "7.1.0")
        assert result is not None
        assert "gem 'rails', \"7.1.0\"" in result

    def test_not_found(self):
        content = 'gem "rails", ">= 7.0"\n'
        result = _update_gemfile(content, "missing", "1.0")
        assert result is None


class TestUpdateComposerJson:
    def test_updates_require(self):
        content = json.dumps({"require": {"laravel/framework": ">=10.0"}}, indent=2)
        result = _update_composer_json(content, "laravel/framework", "10.5.0")
        assert result is not None
        data = json.loads(result)
        assert data["require"]["laravel/framework"] == "10.5.0"

    def test_updates_require_dev(self):
        content = json.dumps({"require-dev": {"phpunit/phpunit": ">=10.0"}}, indent=2)
        result = _update_composer_json(content, "phpunit/phpunit", "10.5.0")
        assert result is not None
        data = json.loads(result)
        assert data["require-dev"]["phpunit/phpunit"] == "10.5.0"

    def test_invalid_json(self):
        result = _update_composer_json("not json", "pkg", "1.0")
        assert result is None

    def test_not_found(self):
        content = json.dumps({"require": {"pkg": ">=1.0"}}, indent=2)
        result = _update_composer_json(content, "missing", "1.0")
        assert result is None


class TestUpdatePyprojectToml:
    def test_updates_poetry_dep(self):
        content = '[tool.poetry.dependencies]\nflask = ">=2.0"\n'
        result = _update_pyproject_toml(content, "flask", "2.3.0")
        assert result is not None
        assert 'flask = "2.3.0"' in result

    def test_updates_project_deps(self):
        content = '[project]\ndependencies = [\n    "flask>=2.0",\n]\n'
        result = _update_pyproject_toml(content, "flask", "2.3.0")
        assert result is not None
        assert "flask==2.3.0" in result

    def test_not_found(self):
        content = '[tool.poetry.dependencies]\nflask = ">=2.0"\n'
        result = _update_pyproject_toml(content, "missing", "1.0")
        assert result is None

    def test_invalid_toml(self):
        result = _update_pyproject_toml("not toml {{{", "pkg", "1.0")
        assert result is None


class TestUpdateBuildGradle:
    def test_updates_implementation(self):
        content = "implementation 'com.example:lib:1.0.0'\n"
        result = _update_build_gradle(content, "com.example:lib", "2.0.0")
        assert result is not None
        assert "com.example:lib:2.0.0" in result

    def test_updates_api(self):
        content = "api 'com.example:lib:1.0.0'\n"
        result = _update_build_gradle(content, "com.example:lib", "2.0.0")
        assert result is not None
        assert "com.example:lib:2.0.0" in result

    def test_not_found(self):
        content = "implementation 'com.example:other:1.0.0'\n"
        result = _update_build_gradle(content, "com.example:missing", "1.0")
        assert result is None

    def test_skips_comments(self):
        content = "// implementation 'com.example:lib:1.0.0'\n"
        result = _update_build_gradle(content, "com.example:lib", "2.0.0")
        assert result is None


class TestUpdateMixExs:
    def test_updates_dep(self):
        content = '{:httpoison, ">= 1.0"}\n'
        result = _update_mix_exs(content, "httpoison", "2.0.0")
        assert result is not None
        assert '{:httpoison, "2.0.0"}' in result

    def test_not_found(self):
        content = '{:other, ">= 1.0"}\n'
        result = _update_mix_exs(content, "missing", "1.0")
        assert result is None


class TestUpdatePackageSwift:
    def test_updates_dep(self):
        content = '.package(url: "https://github.com/vapor/vapor.git", from: "4.0.0")\n'
        result = _update_package_swift(content, "vapor", "4.5.0")
        assert result is not None
        assert 'from: "4.5.0"' in result

    def test_not_found(self):
        content = '.package(url: "https://github.com/other/pkg.git", from: "1.0.0")\n'
        result = _update_package_swift(content, "missing", "1.0")
        assert result is None


class TestUpdatePodfile:
    def test_updates_double_quoted(self):
        content = 'pod "Alamofire", "~> 5.0"\n'
        result = _update_podfile(content, "Alamofire", "5.7.0")
        assert result is not None
        assert 'pod "Alamofire", "5.7.0"' in result

    def test_updates_single_quoted(self):
        content = "pod 'Alamofire', '~> 5.0'\n"
        result = _update_podfile(content, "Alamofire", "5.7.0")
        assert result is not None
        assert "pod 'Alamofire', \"5.7.0\"" in result

    def test_not_found(self):
        content = 'pod "Other", "~> 1.0"\n'
        result = _update_podfile(content, "Missing", "1.0")
        assert result is None


class TestUpdatePipfile:
    def test_updates_package(self):
        content = '[packages]\nrequests = ">=2.28"\n'
        result = _update_pipfile(content, "requests", "2.31.0")
        assert result is not None
        assert 'requests = "==2.31.0"' in result

    def test_not_found(self):
        content = '[packages]\nrequests = ">=2.28"\n'
        result = _update_pipfile(content, "missing", "1.0")
        assert result is None


class TestUpdatePackagesConfig:
    def test_updates_package(self):
        content = '<packages><package id="Newtonsoft.Json" version="13.0.0"/></packages>\n'
        result = _update_packages_config(content, "Newtonsoft.Json", "13.0.3")
        assert result is not None
        assert 'version="13.0.3"' in result

    def test_not_found(self):
        content = '<packages><package id="Other" version="1.0.0"/></packages>\n'
        result = _update_packages_config(content, "Missing", "1.0")
        assert result is None


class TestUpdateEnvironmentYml:
    def test_updates_conda_dep(self):
        content = "dependencies:\n  - numpy>=1.20\n"
        result = _update_environment_yml(content, "numpy", "1.24.0")
        assert result is not None
        assert "- numpy=1.24.0" in result

    def test_updates_pip_dep(self):
        content = "dependencies:\n  - pip:\n    - requests>=2.28\n"
        result = _update_environment_yml(content, "requests", "2.31.0")
        assert result is not None
        assert "- requests==2.31.0" in result

    def test_not_found(self):
        content = "dependencies:\n  - numpy>=1.20\n"
        result = _update_environment_yml(content, "missing", "1.0")
        assert result is None


class TestUpdateCabal:
    def test_updates_build_depends(self):
        content = "build-depends: bytestring >=0.10\n"
        result = _update_cabal(content, "bytestring", "0.11.0")
        assert result is not None
        assert "bytestring ==0.11.0" in result

    def test_not_found(self):
        content = "build-depends: base >=4.14\n"
        result = _update_cabal(content, "missing", "1.0")
        assert result is None

    def test_continuation_line(self):
        content = "build-depends: base >=4.14\n             , bytestring >=0.10\n"
        result = _update_cabal(content, "bytestring", "0.11.0")
        assert result is not None
        assert "bytestring ==0.11.0" in result


class TestUpdateBrewfile:
    def test_updates_brew_cask_double_quoted(self):
        content = 'brew "hello", ">= 2.0"\ncask "firefox", ">= 100.0"\ngem "jekyll", ">= 4.0"\n'
        result = _update_brewfile(content, "hello", "2.1.0")
        assert result is not None
        assert 'brew "hello", "2.1.0"' in result
        result2 = _update_brewfile(content, "firefox", "101.0")
        assert result2 is not None
        assert 'cask "firefox", "101.0"' in result2
        result3 = _update_brewfile(content, "jekyll", "4.3.0")
        assert result3 is not None
        assert 'gem "jekyll", "4.3.0"' in result3

    def test_updates_single_quoted(self):
        content = "brew 'hello', '>= 2.0'\n"
        result = _update_brewfile(content, "hello", "2.1.0")
        assert result is not None
        assert "brew 'hello', \"2.1.0\"" in result

    def test_preserves_comment(self):
        content = 'brew "hello", ">= 2.0"  # core utility\n'
        result = _update_brewfile(content, "hello", "2.1.0")
        assert result is not None
        assert "# core utility" in result

    def test_not_found(self):
        content = 'brew "other", ">= 1.0"\n'
        result = _update_brewfile(content, "missing", "1.0")
        assert result is None


class TestUpdateGemspecDependency:
    def test_updates_add_dependency(self):
        content = 's.add_dependency "rails", ">= 7.0"\n'
        result = _update_gemspec_dependency(content, "rails", "7.1.0")
        assert result is not None
        assert '"7.1.0"' in result

    def test_updates_add_dependency_parens(self):
        content = 's.add_dependency("rails", ">= 7.0")\n'
        result = _update_gemspec_dependency(content, "rails", "7.1.0")
        assert result is not None
        assert '"7.1.0"' in result

    def test_updates_runtime_dependency(self):
        content = 's.add_runtime_dependency "rack", ">= 2.0"\n'
        result = _update_gemspec_dependency(content, "rack", "3.0.0")
        assert result is not None
        assert '"3.0.0"' in result

    def test_updates_development_dependency(self):
        content = 's.add_development_dependency "rspec", ">= 3.0"\n'
        result = _update_gemspec_dependency(content, "rspec", "3.12.0")
        assert result is not None
        assert '"3.12.0"' in result

    def test_not_found(self):
        content = 's.add_dependency "other", ">= 1.0"\n'
        result = _update_gemspec_dependency(content, "missing", "1.0")
        assert result is None


class TestUpdateSimple:
    def test_updates_eq_dep(self):
        content = "nginx==1.24.0\nredis==7.0.0\n"
        result = _update_simple(content, "nginx", "1.25.0")
        assert result is not None
        assert "nginx==1.25.0" in result
        assert "redis==7.0.0" in result

    def test_updates_bare_dep(self):
        content = "curl\nwget\n"
        result = _update_simple(content, "curl", "8.0.0")
        assert result is not None
        assert "curl==8.0.0" in result
        assert "wget" in result

    def test_updates_ge_dep(self):
        content = "python>=3.10\n"
        result = _update_simple(content, "python", "3.12.0")
        assert result is not None
        assert "python==3.12.0" in result

    def test_preserves_comment(self):
        content = "nginx==1.24.0  # web server\n"
        result = _update_simple(content, "nginx", "1.25.0")
        assert result is not None
        assert "# web server" in result

    def test_preserves_blank_and_comment_lines(self):
        content = "# System packages\n\ngit==2.40.0\n"
        result = _update_simple(content, "git", "2.41.0")
        assert result is not None
        assert "# System packages" in result
        assert "" in result.split("\n")  # blank line preserved

    def test_not_found(self):
        content = "nginx==1.24.0\n"
        result = _update_simple(content, "missing", "1.0")
        assert result is None


class TestUpdatePomXml:
    def test_updates_dependency_version(self):
        content = """<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>my-lib</artifactId>
      <version>1.0.0</version>
    </dependency>
  </dependencies>
</project>
"""
        result = _update_pom_xml(content, "com.example:my-lib", "2.0.0")
        assert result is not None
        assert "<version>2.0.0</version>" in result

    def test_updates_second_dep(self):
        content = """<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <dependencies>
    <dependency>
      <groupId>com.alpha</groupId>
      <artifactId>first</artifactId>
      <version>1.0.0</version>
    </dependency>
    <dependency>
      <groupId>com.beta</groupId>
      <artifactId>second</artifactId>
      <version>2.0.0</version>
    </dependency>
  </dependencies>
</project>
"""
        result = _update_pom_xml(content, "com.beta:second", "3.0.0")
        assert result is not None
        assert "<version>3.0.0</version>" in result
        assert "<version>1.0.0</version>" in result

    def test_not_found(self):
        content = """<?xml version="1.0"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>my-lib</artifactId>
      <version>1.0.0</version>
    </dependency>
  </dependencies>
</project>
"""
        result = _update_pom_xml(content, "com.missing:lib", "1.0")
        assert result is None

    def test_invalid_xml_returns_none(self):
        result = _update_pom_xml("not xml", "pkg", "1.0")
        assert result is None


class TestGetManifestUpdater:
    def test_known_filenames(self):
        assert _get_manifest_updater("package.json") is _update_package_json
        assert _get_manifest_updater("pubspec.yaml") is _update_pubspec_yaml
        assert _get_manifest_updater("go.mod") is _update_go_mod
        assert _get_manifest_updater("Cargo.toml") is _update_cargo_toml
        assert _get_manifest_updater("Gemfile") is _update_gemfile
        assert _get_manifest_updater("composer.json") is _update_composer_json
        assert _get_manifest_updater("pyproject.toml") is _update_pyproject_toml
        assert _get_manifest_updater("build.gradle") is _update_build_gradle
        assert _get_manifest_updater("build.gradle.kts") is _update_build_gradle
        assert _get_manifest_updater("Package.swift") is _update_package_swift
        assert _get_manifest_updater("mix.exs") is _update_mix_exs
        assert _get_manifest_updater("Podfile") is _update_podfile
        assert _get_manifest_updater("Brewfile") is _update_brewfile
        assert _get_manifest_updater("Pipfile") is _update_pipfile
        assert _get_manifest_updater("packages.config") is _update_packages_config
        assert _get_manifest_updater("environment.yml") is _update_environment_yml
        assert _get_manifest_updater("apt-packages.txt") is _update_simple
        assert _get_manifest_updater("apk-packages.txt") is _update_simple
        assert _get_manifest_updater("pom.xml") is _update_pom_xml

    def test_gemspec_files(self):
        updater = _get_manifest_updater("mygem.gemspec")
        from backend.cli.shared import _update_gemspec_dependency

        assert updater is _update_gemspec_dependency

    def test_cabal_files(self):
        updater = _get_manifest_updater("my-package.cabal")
        from backend.cli.shared import _update_cabal

        assert updater is _update_cabal

    def test_unknown_returns_none(self):
        assert _get_manifest_updater("unknown.txt") is None


class TestSelectManifestsInteractive:
    def test_selects_all_by_default(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        manifests = [{"ecosystem": "pypi", "filename": "requirements.txt"}]
        result = _select_manifests_interactive(manifests)
        assert result == manifests

    def test_selects_all_explicit(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "all")
        manifests = [{"ecosystem": "pypi", "filename": "req.txt"}]
        result = _select_manifests_interactive(manifests)
        assert result == manifests

    def test_selects_by_indices(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "2")
        manifests = [
            {"ecosystem": "pypi", "filename": "req.txt"},
            {"ecosystem": "npm", "filename": "package.json"},
        ]
        result = _select_manifests_interactive(manifests)
        assert len(result) == 1
        assert result[0]["ecosystem"] == "npm"


class TestBuildTargetSystemInfo:
    """Tests for _build_target_system_info — cross-compilation target builder."""

    def test_no_overrides_returns_none(self):
        class Args:
            target = None
            platform = None
            cuda = None
        assert _build_target_system_info(Args(), {}) is None

    def test_target_os_only(self):
        class Args:
            target = "windows"
            platform = None
            cuda = None
        result = _build_target_system_info(Args(), {})
        assert result == {"os": "windows"}

    def test_target_arch_only(self):
        class Args:
            target = None
            platform = "aarch64"
            cuda = None
        result = _build_target_system_info(Args(), {})
        assert result == {"architecture": "aarch64"}

    def test_target_cuda_only(self):
        class Args:
            target = None
            platform = None
            cuda = "11.8"
        result = _build_target_system_info(Args(), {})
        assert result == {"cuda": "11.8"}

    def test_all_overrides(self):
        class Args:
            target = "linux"
            platform = "x86_64"
            cuda = "12.1"
        result = _build_target_system_info(Args(), {})
        assert result == {"os": "linux", "architecture": "x86_64", "cuda": "12.1"}

    def test_amd64_normalized_to_x86_64(self):
        class Args:
            target = None
            platform = "amd64"
            cuda = None
        result = _build_target_system_info(Args(), {})
        assert result == {"architecture": "x86_64"}

    def test_arm64_normalized_to_aarch64(self):
        class Args:
            target = None
            platform = "arm64"
            cuda = None
        result = _build_target_system_info(Args(), {})
        assert result == {"architecture": "aarch64"}

    # === Cross-compilation integration tests (2.18) ===

    def test_target_overrides_host_os(self):
        """Cross-compilation to windows overrides os in system_info."""
        from backend.cli.shared import _build_target_system_info
        class Args:
            target = "windows"
            platform = None
            cuda = None
        result = _build_target_system_info(Args(), {})
        assert result == {"os": "windows"}

    def test_target_arch_normalizes_arm64(self):
        """Cross-compilation to arm64 normalizes arch."""
        from backend.cli.shared import _build_target_system_info
        class Args:
            target = None
            platform = "arm64"
            cuda = None
        result = _build_target_system_info(Args(), {})
        assert result == {"architecture": "aarch64"}

    def test_target_with_cuda_version(self):
        """Cross-compilation with explicit CUDA version."""
        from backend.cli.shared import _build_target_system_info
        class Args:
            target = "linux"
            platform = "x86_64"
            cuda = "11.8"
        result = _build_target_system_info(Args(), {})
        assert result == {"os": "linux", "architecture": "x86_64", "cuda": "11.8"}

    def test_target_partial_override_no_host_cuda(self):
        """Explicit platform with no host CUDA detected."""
        from backend.cli.shared import _build_target_system_info
        class Args:
            target = None
            platform = "x86_64"
            cuda = None
        result = _build_target_system_info(Args(), {})
        assert result == {"architecture": "x86_64"}
