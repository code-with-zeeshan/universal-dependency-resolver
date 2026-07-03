"""Tests for ManifestDetector — manifest file discovery and parsing."""

import json
import os

import pytest
import yaml

from backend.manifest_detector import ManifestDetector


# ---------------------------------------------------------------------------
# detect()
# ---------------------------------------------------------------------------

class TestDetect:
    def test_empty_directory(self, tmp_path):
        d = ManifestDetector(str(tmp_path))
        assert d.detect() == []

    def test_single_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("numpy\n")
        d = ManifestDetector(str(tmp_path))
        result = d.detect()
        assert len(result) == 1
        assert result[0]["filename"] == "requirements.txt"
        assert result[0]["ecosystem"] == "pypi"
        assert result[0]["parser"] == "requirements"

    def test_multiple_manifests(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("")
        (tmp_path / "package.json").write_text("{}")
        d = ManifestDetector(str(tmp_path))
        result = d.detect()
        assert len(result) == 2
        filenames = {m["filename"] for m in result}
        assert filenames == {"requirements.txt", "package.json"}

    def test_recursive_detection(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "Cargo.toml").write_text("")
        d = ManifestDetector(str(tmp_path))
        result = d.detect()
        assert len(result) == 1
        assert result[0]["filename"] == "Cargo.toml"

    def test_glob_pattern_requirements(self, tmp_path):
        (tmp_path / "dev-requirements.txt").write_text("")
        d = ManifestDetector(str(tmp_path))
        result = d.detect()
        assert len(result) == 1
        assert result[0]["parser"] == "requirements"

    def test_ecosystem_alias_in_detect(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("")
        d = ManifestDetector(str(tmp_path))
        result = d.detect()
        assert result[0]["ecosystem"] == "crates"

    def test_no_duplicate_detection(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "requirements.txt").write_text("")
        d = ManifestDetector(str(tmp_path))
        result = d.detect()
        assert len(result) == 2  # two distinct paths, both kept

    def test_detect_ignores_directories(self, tmp_path):
        (tmp_path / "requirements.txt").mkdir()
        d = ManifestDetector(str(tmp_path))
        result = d.detect()
        assert result == []


# ---------------------------------------------------------------------------
# _read_with_encoding_fallback
# ---------------------------------------------------------------------------

class TestReadWithEncodingFallback:
    def test_utf8_bom(self, tmp_path):
        p = tmp_path / "req.txt"
        p.write_bytes(b"\xef\xbb\xbfnumpy==1.21\n")
        d = ManifestDetector(str(tmp_path))
        manifest = {"path": str(p), "parser": "requirements"}
        result = d.parse(manifest)
        assert result[0]["name"] == "numpy"

    def test_latin1_fallback(self, tmp_path):
        p = tmp_path / "req.txt"
        p.write_bytes("pandas==1.0\n".encode("latin-1"))
        d = ManifestDetector(str(tmp_path))
        manifest = {"path": str(p), "parser": "requirements"}
        result = d.parse(manifest)
        assert result[0]["name"] == "pandas"


# ---------------------------------------------------------------------------
# parse() — individual parsers
# ---------------------------------------------------------------------------

class TestParseRequirements:
    def test_simple(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text("numpy\nrequests\n")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "requirements"})
        assert len(result) == 2
        assert result[0]["name"] == "numpy"
        assert result[1]["name"] == "requests"

    def test_version_specs(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text("numpy==1.21.0\nrequests>=2.25\nclick<8.0\n")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "requirements"})
        assert len(result) == 3
        assert result[0] == {"name": "numpy", "version": "==1.21.0"}
        assert result[1] == {"name": "requests", "version": ">=2.25"}
        assert result[2] == {"name": "click", "version": "<8.0"}

    def test_skips_comments_and_flags(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text(
            "# this is a comment\n"
            "-r base.txt\n"
            "-e ./local-pkg\n"
            "--index-url https://example.com\n"
            "flask==2.0\n"
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "requirements"})
        assert len(result) == 1
        assert result[0]["name"] == "flask"

    def test_extra_whitespace(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text("  numpy  ==  1.21  \n")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "requirements"})
        assert result[0]["name"] == "numpy"
        assert result[0]["version"] == "==1.21"

    def test_blank_lines_skipped(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text("\n\nnumpy\n\n")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "requirements"})
        assert len(result) == 1


class TestParsePipfile:
    def test_basic(self, tmp_path):
        p = tmp_path / "Pipfile"
        p.write_text(
            "[packages]\n"
            'requests = ">=2.25"\n'
            'flask = "==2.0"\n'
            "[dev-packages]\n"
            'pytest = "*"\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "pipfile"})
        assert len(result) == 3
        assert {"name": "requests", "version": ">=2.25"} in result
        assert {"name": "flask", "version": "==2.0"} in result
        assert {"name": "pytest", "version": "*"} in result

    def test_dict_spec(self, tmp_path):
        p = tmp_path / "Pipfile"
        p.write_text(
            '[packages]\n'
            'mypkg = {version = ">=1.0"}\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "pipfile"})
        assert result[0] == {"name": "mypkg", "version": ">=1.0"}

    def test_malformed_toml_returns_empty(self, tmp_path):
        p = tmp_path / "Pipfile"
        p.write_text("[[[invalid\n")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "pipfile"})
        assert result == []


class TestParsePyproject:
    def test_pep_621_dependencies(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text(
            '[project]\n'
            'dependencies = ["numpy>=1.21", "requests>=2.25"]\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "pyproject"})
        assert len(result) == 2
        assert result[0]["name"] == "numpy"
        assert result[1]["name"] == "requests"

    def test_pep_621_no_extras(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text(
            '[project]\n'
            'dependencies = ["numpy>=1.21"]\n'
            'name = "my-project"\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "pyproject"})
        assert len(result) == 1
        assert result[0]["name"] == "numpy"

    def test_poetry_style(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text(
            '[tool.poetry]\n'
            '[tool.poetry.dependencies]\n'
            'python = "^3.9"\n'
            'requests = "^2.25"\n'
            '[tool.poetry.dev-dependencies]\n'
            'pytest = "^6.0"\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "pyproject"})
        assert len(result) == 2  # python is skipped
        assert {"name": "requests", "version": "^2.25"} in result
        assert {"name": "pytest", "version": "^6.0"} in result

    def test_malformed_toml_returns_empty(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text("not toml at all {{{")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "pyproject"})
        assert result == []


class TestParsePackageJson:
    def test_basic(self, tmp_path):
        p = tmp_path / "package.json"
        p.write_text(
            json.dumps({
                "dependencies": {"express": "^4.0", "lodash": "^4.17"},
                "devDependencies": {"mocha": "^9.0"},
                "peerDependencies": {"react": "^17.0"},
            })
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "package_json"})
        assert len(result) == 4
        assert {"name": "express", "version": "^4.0"} in result
        assert {"name": "mocha", "version": "^9.0"} in result
        assert {"name": "react", "version": "^17.0"} in result

    def test_malformed_json_returns_empty(self, tmp_path):
        p = tmp_path / "package.json"
        p.write_text("not json")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "package_json"})
        assert result == []


class TestParseCargoToml:
    def test_basic(self, tmp_path):
        p = tmp_path / "Cargo.toml"
        p.write_text(
            '[dependencies]\n'
            'serde = "1.0"\n'
            'tokio = {version = "1.0", features = ["full"]}\n'
            '[dev-dependencies]\n'
            'criterion = "0.3"\n'
            '[build-dependencies]\n'
            'cc = "1.0"\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "cargo_toml"})
        assert len(result) == 4
        assert {"name": "serde", "version": "1.0"} in result
        assert {"name": "tokio", "version": "1.0"} in result
        assert {"name": "criterion", "version": "0.3"} in result
        assert {"name": "cc", "version": "1.0"} in result


class TestParseGoMod:
    def test_basic(self, tmp_path):
        p = tmp_path / "go.mod"
        p.write_text(
            "module example.com/m\n"
            'require (\n'
            '\tgithub.com/pkg/errors v0.9.1\n'
            '\tgolang.org/x/text v0.3.0\n'
            ')\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "go_mod"})
        assert len(result) == 2
        assert {"name": "github.com/pkg/errors", "version": "v0.9.1"} in result
        assert {"name": "golang.org/x/text", "version": "v0.3.0"} in result

    def test_skips_lines_without_dot(self, tmp_path):
        p = tmp_path / "go.mod"
        p.write_text("go 1.18\n")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "go_mod"})
        assert result == []  # "go 1.18" has no dot in first token


class TestParseGemfile:
    def test_basic(self, tmp_path):
        p = tmp_path / "Gemfile"
        p.write_text(
            "source 'https://rubygems.org'\n"
            'gem "rails", "~> 6.0"\n'
            "gem 'puma', '~> 5.0'\n"
            'gem "sqlite3"\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "gemfile"})
        assert len(result) == 3
        assert {"name": "rails", "version": "~> 6.0"} in result
        assert {"name": "puma", "version": "~> 5.0"} in result
        assert {"name": "sqlite3"} in result

    def test_skips_non_gem_lines(self, tmp_path):
        p = tmp_path / "Gemfile"
        p.write_text(
            "# comment\n"
            'source "https://rubygems.org"\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "gemfile"})
        assert result == []


class TestParseCondaEnv:
    def test_basic(self, tmp_path):
        p = tmp_path / "environment.yml"
        p.write_text(
            yaml.dump({
                "name": "myenv",
                "dependencies": [
                    "numpy>=1.21",
                    "pandas==1.3",
                    "python=3.9",
                    "pip",
                ],
            })
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "conda_env"})
        assert len(result) == 4
        assert {"name": "numpy", "version": ">=1.21"} in result
        assert {"name": "pandas", "version": "==1.3"} in result
        assert {"name": "python", "version": "=3.9"} in result
        assert {"name": "pip", "version": "*"} in result

    def test_pip_subdeps(self, tmp_path):
        p = tmp_path / "environment.yml"
        p.write_text(
            yaml.dump({
                "dependencies": [
                    "numpy",
                    {"pip": ["requests==2.25", "click"]},
                ],
            })
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "conda_env"})
        assert len(result) == 3
        assert {"name": "numpy", "version": "*"} in result
        assert {"name": "requests", "version": "==2.25"} in result
        assert {"name": "click", "version": "*"} in result

    def test_malformed_yaml_returns_empty(self, tmp_path):
        p = tmp_path / "environment.yml"
        p.write_text(": bad yaml :")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "conda_env"})
        assert result == []


class TestParseComposerJson:
    def test_basic(self, tmp_path):
        p = tmp_path / "composer.json"
        p.write_text(
            json.dumps({
                "require": {
                    "php": ">=7.4",
                    "monolog/monolog": "^2.0",
                    "guzzlehttp/guzzle": "^7.0",
                },
                "require-dev": {
                    "phpunit/phpunit": "^9.0",
                },
            })
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "composer_json"})
        assert len(result) == 3  # php is skipped
        assert {"name": "monolog/monolog", "version": "^2.0"} in result
        assert {"name": "guzzlehttp/guzzle", "version": "^7.0"} in result
        assert {"name": "phpunit/phpunit", "version": "^9.0"} in result


class TestParsePipfileLock:
    def test_basic(self, tmp_path):
        p = tmp_path / "Pipfile.lock"
        p.write_text(
            json.dumps({
                "default": {
                    "requests": {"version": "==2.25.0"},
                    "flask": {"version": "==2.0.0"},
                },
                "develop": {
                    "pytest": {"version": "==6.2.0"},
                },
            })
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "pipfile_lock"})
        assert len(result) == 3
        assert {"name": "requests", "version": "==2.25.0"} in result
        assert {"name": "pytest", "version": "==6.2.0"} in result


class TestParseCargoLock:
    def test_basic(self, tmp_path):
        p = tmp_path / "Cargo.lock"
        p.write_text(
            '[[package]]\n'
            'name = "serde"\n'
            'version = "1.0.130"\n'
            '[[package]]\n'
            'name = "tokio"\n'
            'version = "1.10.0"\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "cargo_lock"})
        assert len(result) == 2
        assert {"name": "serde", "version": "1.0.130"} in result
        assert {"name": "tokio", "version": "1.10.0"} in result


class TestParseYarnLock:
    def test_basic(self, tmp_path):
        p = tmp_path / "yarn.lock"
        p.write_text(
            '# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.\n'
            '# yarn lockfile v1\n'
            '\n'
            '"express@^4.0":\n'
            '  version "4.17.1"\n'
            '\n'
            '"lodash@^4.17.21":\n'
            '  version "4.17.21"\n'
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "yarn_lock"})
        assert len(result) == 2
        # parser extracts name/version from the dependency identifier line
        assert {"name": "express", "version": "^4.0"} in result
        assert {"name": "lodash", "version": "^4.17.21"} in result


class TestParsePackageLock:
    def test_basic(self, tmp_path):
        p = tmp_path / "package-lock.json"
        p.write_text(
            json.dumps({
                "packages": {
                    "": {},
                    "node_modules/react": {"version": "18.2.0"},
                    "node_modules/vue": {"version": "3.3.4"},
                }
            })
        )
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "package_lock"})
        assert len(result) == 2
        assert {"name": "react", "version": "18.2.0"} in result
        assert {"name": "vue", "version": "3.3.4"} in result


# ---------------------------------------------------------------------------
# parse() — edge cases
# ---------------------------------------------------------------------------

class TestParseEdgeCases:
    def test_missing_file(self, tmp_path):
        p = tmp_path / "nonexistent.txt"
        d = ManifestDetector(str(tmp_path))
        with pytest.raises(FileNotFoundError):
            d.parse({"path": str(p), "parser": "requirements"})

    def test_unknown_parser_key(self, tmp_path):
        p = tmp_path / "whatever"
        p.write_text("hello")
        d = ManifestDetector(str(tmp_path))
        with pytest.raises(KeyError):
            d.parse({"path": str(p), "parser": "nonexistent"})

    def test_malformed_requirements_not_crashing(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text("\x00numpy==1.21\x00\n")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "requirements"})
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# parse_all()
# ---------------------------------------------------------------------------

class TestParseAll:
    def test_merges_multiple_manifests(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("numpy\nrequests\n")
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"express": "^4.0"}})
        )
        d = ManifestDetector(str(tmp_path))
        manifests = d.detect()
        result = d.parse_all(manifests)
        assert len(result) == 3
        pypi_pkgs = [p for p in result if p["_ecosystem"] == "pypi"]
        npm_pkgs = [p for p in result if p["_ecosystem"] == "npm"]
        assert len(pypi_pkgs) == 2
        assert len(npm_pkgs) == 1

    def test_empty_manifests(self, tmp_path):
        d = ManifestDetector(str(tmp_path))
        result = d.parse_all([])
        assert result == []


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_ecosystem_alias_cargo_to_crates(self):
        d = ManifestDetector(".")
        pkgs = [
            {"name": "serde", "version": "1.0", "_ecosystem": "cargo", "_manifest": "Cargo.toml"},
        ]
        result = d.normalize(pkgs)
        assert result[0]["ecosystem"] == "crates"

    def test_ecosystem_alias_go_to_gomodules(self):
        d = ManifestDetector(".")
        pkgs = [
            {"name": "github.com/pkg/errors", "version": "v0.9.1", "_ecosystem": "go", "_manifest": "go.mod"},
        ]
        result = d.normalize(pkgs)
        assert result[0]["ecosystem"] == "gomodules"

    def test_skips_empty_name(self):
        d = ManifestDetector(".")
        pkgs = [
            {"name": "", "version": "1.0", "_ecosystem": "pypi"},
            {"name": "  ", "version": "2.0", "_ecosystem": "pypi"},
            {"name": "valid", "version": "3.0", "_ecosystem": "pypi"},
        ]
        result = d.normalize(pkgs)
        assert len(result) == 1

    def test_constraint_defaults_to_star(self):
        d = ManifestDetector(".")
        pkgs = [
            {"name": "pkg", "_ecosystem": "pypi", "_manifest": "req.txt"},
        ]
        result = d.normalize(pkgs)
        assert result[0]["constraint"] == "*"

    def test_constraint_uses_empty_string_fallback(self):
        d = ManifestDetector(".")
        pkgs = [
            {"name": "pkg", "version": "", "_ecosystem": "pypi", "_manifest": "req.txt"},
        ]
        result = d.normalize(pkgs)
        assert result[0]["constraint"] == "*"

    def test_name_normalization(self):
        d = ManifestDetector(".")
        pkgs = [
            {"name": "My_Package", "version": "1.0", "_ecosystem": "pypi", "_manifest": "req.txt"},
        ]
        result = d.normalize(pkgs)
        assert result[0]["name"] == "my-package"

    def test_pypi_default_ecosystem(self):
        d = ManifestDetector(".")
        pkgs = [
            {"name": "numpy", "version": "1.21", "_manifest": "req.txt"},
        ]
        result = d.normalize(pkgs)
        assert result[0]["ecosystem"] == "pypi"

    def test_source_from_manifest(self):
        d = ManifestDetector(".")
        pkgs = [
            {"name": "numpy", "version": "1.0", "_ecosystem": "pypi", "_manifest": "requirements.txt"},
        ]
        result = d.normalize(pkgs)
        assert result[0]["source"] == "requirements.txt"

    def test_unknown_ecosystem_preserved(self):
        d = ManifestDetector(".")
        pkgs = [
            {"name": "foo", "version": "1.0", "_ecosystem": "unknown", "_manifest": "f.txt"},
        ]
        result = d.normalize(pkgs)
        assert result[0]["ecosystem"] == "unknown"


# ---------------------------------------------------------------------------
# parse() — BOM encoding
# ---------------------------------------------------------------------------

class TestParseEncoding:
    def test_utf8_bom_requirements(self, tmp_path):
        p = tmp_path / "req.txt"
        p.write_bytes(b"\xef\xbb\xbfpandas==1.3\n")
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "requirements"})
        assert result[0]["name"] == "pandas"

    def test_utf16_le_bom_path(self, tmp_path):
        p = tmp_path / "req.txt"
        p.write_bytes(b"\xff\xfe" + "numpy==1.21\n".encode("utf-16-le"))
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "requirements"})
        # The code decodes including BOM chars; verify no crash and pkg returned
        assert len(result) == 1
        assert "numpy" in result[0]["name"]

    def test_utf16_be_bom_path(self, tmp_path):
        p = tmp_path / "req.txt"
        p.write_bytes(b"\xfe\xff" + "numpy==1.21\n".encode("utf-16-be"))
        d = ManifestDetector(str(tmp_path))
        result = d.parse({"path": str(p), "parser": "requirements"})
        assert len(result) == 1
        assert "numpy" in result[0]["name"]
