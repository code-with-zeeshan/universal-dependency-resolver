"""Unit tests for backend/cli/shared.py — manifest update functions and helpers."""

import json

from backend.cli.shared import (
    _get_manifest_updater,
    _select_manifests_interactive,
    _update_build_gradle,
    _update_cabal,
    _update_cargo_toml,
    _update_composer_json,
    _update_environment_yml,
    _update_gemfile,
    _update_go_mod,
    _update_mix_exs,
    _update_package_json,
    _update_package_swift,
    _update_packages_config,
    _update_pipfile,
    _update_podfile,
    _update_pubspec_yaml,
    _update_pyproject_toml,
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
        assert _get_manifest_updater("Brewfile") is not None
        assert _get_manifest_updater("Pipfile") is _update_pipfile
        assert _get_manifest_updater("packages.config") is _update_packages_config
        assert _get_manifest_updater("environment.yml") is _update_environment_yml

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
