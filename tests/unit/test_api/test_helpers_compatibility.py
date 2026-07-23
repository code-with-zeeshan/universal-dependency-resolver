import pytest

from backend.api.helpers.compatibility import (
    SystemSpec,
    _check_cuda_compatibility,
    _check_os_compatibility,
    _check_python_compatibility,
    _check_version_compatibility,
    _check_version_compatibility_detailed,
    _is_prerelease,
)


class TestSystemSpec:
    def test_empty_string(self):
        spec = SystemSpec.from_string("")
        assert spec.os is None
        assert spec.architecture is None

    def test_os_parsed(self):
        spec = SystemSpec.from_string("os=linux")
        assert spec.os == "linux"

    def test_os_variant(self):
        spec = SystemSpec.from_string("operating_system=windows")
        assert spec.os == "windows"

    def test_architecture_parsed(self):
        spec = SystemSpec.from_string("arch=arm64")
        assert spec.architecture == "arm64"

    def test_python_parsed(self):
        spec = SystemSpec.from_string("python=3.10")
        assert spec.python_version == "3.10"

    def test_cuda_parsed(self):
        spec = SystemSpec.from_string("cuda=12.0")
        assert spec.cuda_version == "12.0"

    def test_gpu_true(self):
        spec = SystemSpec.from_string("gpu=true")
        assert spec.gpu_available is True

    def test_gpu_false(self):
        spec = SystemSpec.from_string("gpu=no")
        assert spec.gpu_available is False

    def test_multiple_fields(self):
        spec = SystemSpec.from_string("os=macos, arch=x86_64, python=3.11, cuda=11.8")
        assert spec.os == "macos"
        assert spec.architecture == "x86_64"

    def test_unknown_key_ignored(self):
        spec = SystemSpec.from_string("os=linux,unknown_key=val")
        assert spec.os == "linux"

    def test_os_version_parsed(self):
        spec = SystemSpec.from_string("os_version=22.04")
        assert spec.os_version == "22.04"


class TestCheckPythonCompatibility:
    def test_compatible(self):
        assert _check_python_compatibility("3.10", ">=3.8") is True

    def test_incompatible(self):
        assert _check_python_compatibility("3.7", ">=3.8") is False

    def test_invalid_specifier(self):
        assert _check_python_compatibility("3.10", "invalid") is True


class TestCheckOsCompatibility:
    def test_any_platform(self):
        assert _check_os_compatibility("linux", ["any"]) is True

    def test_empty_platforms(self):
        assert _check_os_compatibility("linux", []) is True

    def test_linux_compatible(self):
        assert _check_os_compatibility("linux", ["manylinux2014"]) is True

    def test_linux_incompatible(self):
        assert _check_os_compatibility("linux", ["win32", "win_amd64"]) is False

    def test_windows_compatible(self):
        assert _check_os_compatibility("windows", ["win32"]) is True

    def test_macos_compatible(self):
        assert _check_os_compatibility("macos", ["darwin"]) is True

    def test_darwin_compatible(self):
        assert _check_os_compatibility("darwin", ["macos"]) is True

    def test_case_insensitive(self):
        assert _check_os_compatibility("Linux", ["ManyLinux"]) is True


class TestCheckCudaCompatibility:
    def test_exact_match(self):
        assert _check_cuda_compatibility("12.0", ["12.0"]) is True

    def test_no_match(self):
        assert _check_cuda_compatibility("12.0", ["11.8"]) is False

    def test_major_x_wildcard(self):
        assert _check_cuda_compatibility("12.0", ["12.x"]) is True
        assert _check_cuda_compatibility("12.5", ["12.x"]) is True
        assert _check_cuda_compatibility("11.0", ["12.x"]) is False

    def test_specifier_match(self):
        assert _check_cuda_compatibility("12.0", [">=11.8"]) is True

    def test_specifier_no_match(self):
        assert _check_cuda_compatibility("11.0", [">=12.0"]) is False

    def test_invalid_version(self):
        assert _check_cuda_compatibility("not-a-version", ["12.0"]) is True


class TestCheckVersionCompatibility:
    def test_compatible_no_spec(self):
        assert _check_version_compatibility({}, "") is True

    def test_python_mismatch(self):
        info = {"python_requires": ">=3.8"}
        assert _check_version_compatibility(info, "python=3.7") is False

    def test_python_match(self):
        info = {"python_requires": ">=3.8"}
        assert _check_version_compatibility(info, "python=3.10") is True

    def test_os_mismatch(self):
        info = {"platforms": ["win32"]}
        assert _check_version_compatibility(info, "os=linux") is False

    def test_arch_mismatch(self):
        info = {"architectures": ["x86_64"]}
        assert _check_version_compatibility(info, "arch=arm64") is False

    def test_yanked_still_compatible(self):
        info = {"yanked": True}
        assert _check_version_compatibility(info, "") is True


class TestCheckVersionCompatibilityDetailed:
    def test_both_compatible(self):
        info = {"python_requires": ">=3.8", "platforms": ["linux"]}
        compat, notes = _check_version_compatibility_detailed(
            info, SystemSpec.from_string("os=linux, python=3.10")
        )
        assert compat is True

    def test_python_mismatch(self):
        info = {"python_requires": ">=3.8"}
        compat, notes = _check_version_compatibility_detailed(
            info, SystemSpec.from_string("python=3.7")
        )
        assert compat is False
        assert any("Python" in n for n in notes)

    def test_os_mismatch(self):
        info = {"platforms": ["win32"]}
        compat, notes = _check_version_compatibility_detailed(
            info, SystemSpec.from_string("os=linux")
        )
        assert compat is False
        assert any("linux" in n for n in notes)

    def test_arch_mismatch(self):
        info = {"architectures": ["x86_64"]}
        compat, notes = _check_version_compatibility_detailed(
            info, SystemSpec.from_string("arch=arm64")
        )
        assert compat is False
        assert any("arm64" in n for n in notes)

    def test_gpu_required_none_available(self):
        info = {"gpu_required": True, "cuda_versions": []}
        compat, notes = _check_version_compatibility_detailed(
            info, SystemSpec(cuda_version=None, gpu_available=False)
        )
        assert compat is False
        assert any("GPU" in n for n in notes)

    def test_yanked_note(self):
        info = {"yanked": True}
        compat, notes = _check_version_compatibility_detailed(info, SystemSpec())
        assert any("yanked" in n for n in notes)


class TestIsPrerelease:
    def test_pep440_dev(self):
        assert _is_prerelease("1.0.0.dev1") is True

    def test_pep440_alpha(self):
        assert _is_prerelease("1.0.0a1") is True

    def test_pep440_beta(self):
        assert _is_prerelease("1.0.0b1") is True

    def test_pep440_rc(self):
        assert _is_prerelease("1.0.0rc1") is True

    def test_stable(self):
        assert _is_prerelease("1.0.0") is False

    def test_npm_alpha(self):
        assert _is_prerelease("1.0.0-alpha.1") is True

    def test_npm_beta(self):
        assert _is_prerelease("1.0.0-beta.1") is True

    def test_invalid_versions(self):
        result = _is_prerelease("zzz")
        assert isinstance(result, bool)

    def test_pre_in_version(self):
        assert _is_prerelease("1.0.0-pre.1") is True
