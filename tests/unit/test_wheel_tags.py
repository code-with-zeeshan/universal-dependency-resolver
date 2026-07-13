"""Regression tests for wheel compatibility checking via packaging.tags."""

from __future__ import annotations

from packaging.tags import Tag

from backend.core.wheel_tags import (
    _build_target_tags,
    check_wheel_compatibility,
)


class TestCheckWheelCompatibility:
    def test_host_tags_match_itself(self):
        """A wheel tagged for the host platform should be compatible."""
        from packaging.tags import sys_tags

        host_tags = list(sys_tags())
        if host_tags:
            tag_str = str(host_tags[0])
            assert check_wheel_compatibility([tag_str])

    def test_nonexistent_tags(self):
        assert not check_wheel_compatibility(["cp999-cp999-none-unknown"])

    def test_linux_x86_tags(self):
        tags = _build_target_tags("linux", "x86_64", None)
        assert any("manylinux" in str(t) for t in tags)

    def test_macos_arm_tags(self):
        tags = _build_target_tags("darwin", "arm64", None)
        assert any("macosx" in str(t) for t in tags)

    def test_windows_x86_tags(self):
        tags = _build_target_tags("windows", "amd64", None)
        assert any("win" in str(t) for t in tags)

    def test_specific_python_version(self):
        tags = _build_target_tags("linux", "x86_64", "3.11")
        assert any("cp311" in str(t) for t in tags)

    def test_none_targets_fallback_to_host(self):
        tags = _build_target_tags(None, None, None)
        assert len(tags) > 0


class TestBuildTargetTags:
    def test_returns_tag_set(self):
        tags = _build_target_tags("linux", "x86_64", "3.11")
        assert isinstance(tags, set)
        assert all(isinstance(t, Tag) for t in tags)

    def test_platform_string_is_correct(self):
        tags = _build_target_tags("linux", "aarch64", None)
        assert any("aarch64" in str(t) for t in tags)

    def test_arch_amd64_to_x86_64(self):
        tags = _build_target_tags("linux", "amd64", None)
        assert any("x86_64" in str(t) for t in tags)
