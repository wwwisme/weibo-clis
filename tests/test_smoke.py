"""Smoke tests for Weibo CLI — require live browser cookies.

Run with: uv run pytest tests/test_smoke.py -v -m smoke
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from weibo_cli.cli import cli


runner = CliRunner()


@pytest.mark.smoke
def test_hot_search_live():
    """Hot search returns 50+ items."""
    result = runner.invoke(cli, ["hot", "--json"])
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "realtime" in data
    assert len(data["realtime"]) > 10


@pytest.mark.smoke
def test_trending_live():
    """Trending sidebar returns items."""
    result = runner.invoke(cli, ["trending", "--json"])
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "realtime" in data
    assert len(data["realtime"]) > 0


@pytest.mark.smoke
def test_detail_live():
    """Weibo detail returns full data."""
    result = runner.invoke(cli, ["detail", "Qw06Kd98p", "--json"])
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "user" in data
    assert data["user"]["screen_name"] == "新华社"
    assert "text_raw" in data or "text" in data


@pytest.mark.smoke
def test_profile_live():
    """Profile returns user data with stats."""
    result = runner.invoke(cli, ["profile", "1699432410", "--json"])
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "user" in data
    user = data["user"]
    assert user["screen_name"] == "新华社"
    assert user["followers_count"] > 0


@pytest.mark.smoke
def test_feed_live():
    """Hot feed returns statuses."""
    result = runner.invoke(cli, ["feed", "--count", "3", "--json"])
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "statuses" in data


@pytest.mark.smoke
def test_status_live():
    """Status command reports login state."""
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    # Should contain either 已登录 or 未登录
    assert "已登录" in result.output or "未登录" in result.output
