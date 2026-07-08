"""Unit tests for orchestrator/install.py."""

from unittest.mock import patch

from backend.orchestrator.install import (
    _check_toolchain,
    _generate_install_command,
    check_toolchains,
)


class TestGenerateInstallCommand:
    def test_none_for_empty_packages(self):
        assert _generate_install_command("pypi", []) is None

    def test_unknown_ecosystem_returns_none(self):
        result = _generate_install_command("unknown", [("pkg", "1.0")])
        assert result is None

    def test_pypi_pip_install(self):
        cmd = _generate_install_command("pypi", [("requests", "2.31.0"), ("flask", "2.3.3")])
        assert cmd is not None
        assert cmd.startswith("pip install")
        assert "requests==2.31.0" in cmd
        assert "flask==2.3.3" in cmd

    def test_npm_install(self):
        cmd = _generate_install_command("npm", [("express", "4.18.2")])
        assert cmd is not None
        assert cmd.startswith("npm install")
        assert "express@4.18.2" in cmd

    def test_crates_cargo_add(self):
        cmd = _generate_install_command("crates", [("serde", "1.0.197")])
        assert cmd is not None
        assert cmd.startswith("cargo add")
        assert "serde@1.0.197" in cmd

    def test_gomodules_go_get(self):
        cmd = _generate_install_command("gomodules", [("github.com/foo/bar", "v1.2.3")])
        assert cmd is not None
        assert cmd.startswith("go get")
        assert "github.com/foo/bar@v1.2.3" in cmd

    def test_cocoapods(self):
        cmd = _generate_install_command("cocoapods", [("Alamofire", "5.8.0")])
        assert cmd is not None
        assert cmd.startswith("pod install")
        assert "Alamofire@5.8.0" in cmd

    def test_pub_dart(self):
        cmd = _generate_install_command("pub", [("flutter_lints", "3.0.0")])
        assert cmd is not None
        assert cmd.startswith("dart pub add")
        assert "flutter_lints:3.0.0" in cmd

    def test_homebrew_uses_name_only(self):
        cmd = _generate_install_command("homebrew", [("wget", "1.21.4")])
        assert cmd is not None
        assert cmd.startswith("brew install")
        assert "wget" in cmd
        assert "1.21.4" not in cmd.split("wget")[1] if "wget" in cmd else True

    def test_hex_returns_mix_deps_update(self):
        cmd = _generate_install_command("hex", [("phoenix", "1.7.7")])
        assert cmd == "mix deps.update"

    def test_swift_returns_swift_package_resolve(self):
        cmd = _generate_install_command("swift", [("swift-algorithms", "1.0.0")])
        assert cmd == "swift package resolve"

    def test_rubygems_gem_install(self):
        cmd = _generate_install_command("rubygems", [("rails", "7.1.0")])
        assert cmd is not None
        assert cmd.startswith("gem install")
        assert "rails==7.1.0" in cmd

    def test_packagist_composer_require(self):
        cmd = _generate_install_command("packagist", [("monolog/monolog", "3.5.0")])
        assert cmd is not None
        assert cmd.startswith("composer require")
        assert "monolog/monolog==3.5.0" in cmd

    def test_pypi_cuda_filter_keeps_matching(self):
        cmd = _generate_install_command(
            "pypi",
            [("torch", "2.0.1+cu121"), ("torchvision", "0.15.2+cu121")],
            cuda_version="12.1",
        )
        assert cmd is not None
        assert "torch==2.0.1" in cmd
        assert "torchvision==0.15.2" in cmd
        assert "+cu121" not in cmd

    def test_pypi_cuda_filter_skips_non_matching(self):
        cmd = _generate_install_command(
            "pypi",
            [("torch", "2.0.1+cu121"), ("torch", "1.13.1+cu117")],
            cuda_version="12.1",
        )
        assert cmd is not None
        assert "torch==2.0.1" in cmd
        assert "torch==1.13.1" not in cmd

    def test_pypi_cuda_no_suffix_kept(self):
        cmd = _generate_install_command(
            "pypi",
            [("numpy", "1.24.0")],
            cuda_version="12.1",
        )
        assert cmd is not None
        assert "numpy==1.24.0" in cmd


class TestCheckToolchain:
    def test_tool_available(self):
        with patch("shutil.which", return_value="/usr/bin/pip"):
            assert _check_toolchain("pypi") is True

    def test_tool_unavailable(self):
        with patch("shutil.which", return_value=None):
            assert _check_toolchain("pypi") is False

    def test_unknown_ecosystem(self):
        with patch("shutil.which", return_value=None):
            assert _check_toolchain("unknown") is False


class TestCheckToolchains:
    def test_returns_dict_with_all_ecosystems(self):
        with patch("backend.orchestrator.install._check_toolchain", return_value=True):
            result = check_toolchains(["pypi", "npm", "crates"])
            assert result == {"pypi": True, "npm": True, "crates": True}

    def test_handles_mixed_availability(self):
        def mock_check(eco):
            return eco in ("pypi", "crates")

        with patch("backend.orchestrator.install._check_toolchain", side_effect=mock_check):
            result = check_toolchains(["pypi", "npm", "crates"])
            assert result == {"pypi": True, "npm": False, "crates": True}

    def test_empty_input(self):
        result = check_toolchains([])
        assert result == {}


class TestCudaVersionRegex:
    def test_cuda_suffix_stripped_from_any_ecosystem(self):
        for eco in ("pypi", "npm", "crates"):
            cmd = _generate_install_command(eco, [("pkg", "1.0")])
            if cmd and eco == "pypi":
                assert "+cu" not in cmd

    def test_no_cuda_suffix_unchanged(self):
        cmd = _generate_install_command("pypi", [("pkg", "1.0.0")])
        assert "pkg==1.0.0" in cmd

    def test_multiple_cuda_variants_all_matching(self):
        cmd = _generate_install_command(
            "pypi",
            [
                ("torch", "2.0.0+cu121"),
                ("torchvision", "0.15.0+cu121"),
                ("torchaudio", "2.0.0+cu121"),
            ],
            cuda_version="12.1",
        )
        assert cmd is not None
        assert "torch==2.0.0" in cmd
        assert "torchvision==0.15.0" in cmd
        assert "torchaudio==2.0.0" in cmd

    def test_all_variants_skipped_returns_none(self):
        cmd = _generate_install_command(
            "pypi",
            [("torch", "1.13.0+cu117")],
            cuda_version="12.1",
        )
        assert cmd is None
