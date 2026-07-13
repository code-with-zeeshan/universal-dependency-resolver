"""Tests for backend.core.pinning — PinningPolicy dataclass and pinning logic."""

from __future__ import annotations

from backend.core.pinning import (
    PinningPolicy,
    apply_pinning_policy,
    freeze_from_lock,
    _apply_pin_mode,
)


class TestPinningPolicy:
    """PinningPolicy dataclass construction, defaults, and serialization."""

    def test_defaults(self):
        policy = PinningPolicy()
        assert policy.pin_mode == "none"
        assert policy.pinned == {}
        assert policy.blocked == []
        assert policy.freeze is False

    def test_from_dict_explicit(self):
        policy = PinningPolicy(
            pin_mode="patch",
            pinned={"requests": "2.31.0"},
            blocked=["badlib"],
            freeze=True,
        )
        assert policy.pin_mode == "patch"
        assert policy.pinned == {"requests": "2.31.0"}
        assert policy.blocked == ["badlib"]
        assert policy.freeze is True

    def test_from_dict_partial(self):
        policy = PinningPolicy(pin_mode="exact", freeze=True)
        assert policy.pin_mode == "exact"
        assert policy.pinned == {}
        assert policy.blocked == []
        assert policy.freeze is True

    def test_to_dict(self):
        policy = PinningPolicy(pin_mode="minor", pinned={"foo": "1.0.0"}, blocked=["bar"])
        d = {
            "pin_mode": policy.pin_mode,
            "pinned": policy.pinned,
            "blocked": policy.blocked,
            "freeze": policy.freeze,
        }
        assert d == {
            "pin_mode": "minor",
            "pinned": {"foo": "1.0.0"},
            "blocked": ["bar"],
            "freeze": False,
        }


class TestApplyPinningPolicy:
    """apply_pinning_policy filtering and constraint rewriting."""

    def test_none_policy_returns_copy(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.0"}]
        result = apply_pinning_policy(pkgs, None)
        assert result == pkgs
        assert result is not pkgs

    def test_blocked_package_removed(self):
        pkgs = [
            {"name": "good", "version_constraint": ">=1.0"},
            {"name": "evil", "version_constraint": ">=2.0"},
        ]
        policy = PinningPolicy(blocked=["evil"])
        result = apply_pinning_policy(pkgs, policy)
        assert len(result) == 1
        assert result[0]["name"] == "good"

    def test_blocked_logs_and_skips(self):
        import logging

        logger = logging.getLogger("backend.core.pinning")
        logger.setLevel(logging.INFO)
        pkgs = [{"name": "bad", "version_constraint": "*"}]
        policy = PinningPolicy(blocked=["bad"])
        result = apply_pinning_policy(pkgs, policy)
        assert len(result) == 0

    def test_pinned_package_gets_exact(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.0,<2.0"}]
        policy = PinningPolicy(pinned={"foo": "1.5.0"})
        result = apply_pinning_policy(pkgs, policy)
        assert result[0]["version_constraint"] == "==1.5.0"

    def test_pin_mode_patch(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.2.3,<2.0"}]
        policy = PinningPolicy(pin_mode="patch")
        result = apply_pinning_policy(pkgs, policy)
        assert result[0]["version_constraint"] == ">=1.2.3,<1.2.4"

    def test_pin_mode_minor(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.2.3,<2.0"}]
        policy = PinningPolicy(pin_mode="minor")
        result = apply_pinning_policy(pkgs, policy)
        assert result[0]["version_constraint"] == ">=1.2.3,<1.3.0"

    def test_pin_mode_none_is_noop(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.0"}]
        policy = PinningPolicy(pin_mode="none")
        result = apply_pinning_policy(pkgs, policy)
        assert result[0]["version_constraint"] == ">=1.0"

    def test_pinned_takes_precedence_over_pin_mode(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.0,<2.0"}]
        policy = PinningPolicy(pin_mode="patch", pinned={"foo": "2.0.0"})
        result = apply_pinning_policy(pkgs, policy)
        assert result[0]["version_constraint"] == "==2.0.0"

    def test_missing_name_uses_empty_string(self):
        pkgs = [{"version_constraint": ">=1.0"}]
        policy = PinningPolicy(blocked=[""])
        result = apply_pinning_policy(pkgs, policy)
        assert len(result) == 0

    def test_pin_mode_without_constraint_is_noop(self):
        pkgs = [{"name": "foo"}]
        policy = PinningPolicy(pin_mode="patch")
        result = apply_pinning_policy(pkgs, policy)
        assert result[0].get("version_constraint") == "*"

    def test_pin_mode_exact_returns_original_constraint(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.0"}]
        policy = PinningPolicy(pin_mode="exact")
        result = apply_pinning_policy(pkgs, policy)
        assert result[0]["version_constraint"] == ">=1.0"


class TestFreezeFromLock:
    """freeze_from_lock overlays locked versions."""

    def test_no_lock_data_returns_copy(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.0"}]
        result = freeze_from_lock(pkgs, None)
        assert result == pkgs
        assert result is not pkgs

    def test_freeze_overwrites_constraint(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.0,<2.0"}]
        lock = {"packages": {"foo": {"resolved_version": "1.5.0"}}}
        result = freeze_from_lock(pkgs, lock)
        assert result[0]["version_constraint"] == "==1.5.0"

    def test_freeze_falls_back_to_version_field(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.0"}]
        lock = {"packages": {"foo": {"version": "1.5.0"}}}
        result = freeze_from_lock(pkgs, lock)
        assert result[0]["version_constraint"] == "==1.5.0"

    def test_unlocked_package_unchanged(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.0"}]
        lock = {"packages": {"bar": {"resolved_version": "2.0.0"}}}
        result = freeze_from_lock(pkgs, lock)
        assert result[0]["version_constraint"] == ">=1.0"

    def test_empty_lock_packages_is_noop(self):
        pkgs = [{"name": "foo", "version_constraint": ">=1.0"}]
        lock = {"packages": {}}
        result = freeze_from_lock(pkgs, lock)
        assert result[0]["version_constraint"] == ">=1.0"


class TestApplyPinMode:
    """_apply_pin_mode internal helper."""

    def test_patch_narrows_to_next_patch(self):
        result = _apply_pin_mode(">=1.2.3,<2.0", "patch", "foo")
        assert result == ">=1.2.3,<1.2.4"

    def test_minor_narrows_to_next_minor(self):
        result = _apply_pin_mode(">=1.2.3,<2.0", "minor", "foo")
        assert result == ">=1.2.3,<1.3.0"

    def test_exact_returns_input(self):
        result = _apply_pin_mode(">=1.0", "exact", "foo")
        assert result == ">=1.0"

    def test_no_upper_bound_returns_input(self):
        result = _apply_pin_mode("!=1.0", "patch", "foo")
        assert result == "!=1.0"

    def test_invalid_spec_returns_input(self):
        result = _apply_pin_mode("not a spec", "patch", "foo")
        assert result == "not a spec"

    def test_uses_highest_version_for_bound(self):
        result = _apply_pin_mode(">=1.0.0,>=1.1.0,<2.0", "patch", "foo")
        assert result == ">=1.1.0,<1.1.1"
