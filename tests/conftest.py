"""Shared pytest setup."""

try:  # dev-only: load the fixed Hypothesis profile for every run when Hypothesis is installed
    import hypothesis_gate  # noqa: F401
except ImportError:
    pass
