"""Tests for Weibo CLI — importability, command registration, and smoke tests."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from click.testing import CliRunner

from weibo_cli.cli import cli


# ── Import & registration tests ─────────────────────────────────────


def test_import_cli():
    """CLI module is importable."""
    from weibo_cli import cli as cli_mod
    assert cli_mod is not None


def test_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Weibo CLI" in result.output


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


EXPECTED_COMMANDS = [
    "login", "logout", "status", "me",
    "hot", "feed", "detail", "comments", "trending",
    "profile", "weibos", "following",
]


@pytest.mark.parametrize("cmd", EXPECTED_COMMANDS)
def test_command_registered(cmd):
    """All expected commands are registered."""
    runner = CliRunner()
    result = runner.invoke(cli, [cmd, "--help"])
    assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"


def test_command_count():
    """Ensure we have exactly the expected number of commands."""
    assert len(cli.commands) == len(EXPECTED_COMMANDS)


# ── Constants tests ─────────────────────────────────────────────────


def test_constants_urls():
    from weibo_cli.constants import BASE_URL, PASSPORT_URL, HOT_SEARCH_URL
    assert BASE_URL == "https://weibo.com"
    assert PASSPORT_URL == "https://passport.weibo.com"
    assert HOT_SEARCH_URL.startswith("/ajax/")


def test_constants_headers():
    from weibo_cli.constants import HEADERS
    assert "User-Agent" in HEADERS
    assert "Chrome" in HEADERS["User-Agent"]


# ── Credential class tests ──────────────────────────────────────────


def test_credential_roundtrip():
    from weibo_cli.auth import Credential
    cred = Credential(cookies={"SUB": "abc", "SUBP": "xyz"})
    assert cred.is_valid
    data = cred.to_dict()
    assert "cookies" in data
    assert "saved_at" in data
    restored = Credential.from_dict(data)
    assert restored.cookies == cred.cookies


def test_credential_cookie_header():
    from weibo_cli.auth import Credential
    cred = Credential(cookies={"A": "1", "B": "2"})
    header = cred.as_cookie_header()
    assert "A=1" in header
    assert "B=2" in header


def test_credential_empty():
    from weibo_cli.auth import Credential
    cred = Credential(cookies={})
    assert not cred.is_valid


# ── Exception tests ─────────────────────────────────────────────────


def test_exception_hierarchy():
    from weibo_cli.exceptions import WeiboApiError, SessionExpiredError, QRExpiredError, error_code_for_exception
    assert issubclass(SessionExpiredError, WeiboApiError)
    assert issubclass(QRExpiredError, WeiboApiError)
    assert error_code_for_exception(SessionExpiredError()) == "not_authenticated"
    assert error_code_for_exception(QRExpiredError()) == "qr_expired"


# ── Smoke tests (require live cookies) ──────────────────────────────


@pytest.mark.smoke
def test_hot_search_live():
    """Smoke test: hot search should return data."""
    runner = CliRunner()
    result = runner.invoke(cli, ["hot", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "realtime" in data
    assert len(data["realtime"]) > 0


@pytest.mark.smoke
def test_detail_live():
    """Smoke test: weibo detail should return data."""
    runner = CliRunner()
    result = runner.invoke(cli, ["detail", "Qw06Kd98p", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "user" in data
    assert data["user"]["screen_name"] == "新华社"


@pytest.mark.smoke
def test_profile_live():
    """Smoke test: profile should return user data."""
    runner = CliRunner()
    result = runner.invoke(cli, ["profile", "1699432410", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "user" in data
    assert data["user"]["screen_name"] == "新华社"
