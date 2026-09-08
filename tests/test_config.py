"""
Tests for configuration helpers.
"""

from config import _env_int, _env_float


def test_env_int_returns_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_INT", raising=False)
    assert _env_int("SOME_INT", 7) == 7


def test_env_int_parses_valid_value(monkeypatch):
    monkeypatch.setenv("SOME_INT", "42")
    assert _env_int("SOME_INT", 7) == 42


def test_env_int_falls_back_on_invalid_value(monkeypatch):
    monkeypatch.setenv("SOME_INT", "not-a-number")
    assert _env_int("SOME_INT", 7) == 7


def test_env_float_parses_valid_value(monkeypatch):
    monkeypatch.setenv("SOME_FLOAT", "1.5")
    assert _env_float("SOME_FLOAT", 0.5) == 1.5


def test_env_float_falls_back_on_invalid_value(monkeypatch):
    monkeypatch.setenv("SOME_FLOAT", "oops")
    assert _env_float("SOME_FLOAT", 0.5) == 0.5
