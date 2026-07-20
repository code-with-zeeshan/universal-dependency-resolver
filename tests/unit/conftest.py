"""Conftest for unit tests — reduce Hypothesis max_examples for speed."""

from hypothesis import settings

settings.register_profile("ci", max_examples=100)
settings.register_profile("dev", max_examples=30)
settings.load_profile("dev")
