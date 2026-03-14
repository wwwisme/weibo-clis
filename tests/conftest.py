"""Shared test fixtures for Weibo CLI tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from weibo_cli.auth import Credential


@pytest.fixture
def mock_credential():
    """A valid fake credential for testing."""
    return Credential(cookies={"SUB": "test_sub", "SUBP": "test_subp", "X-CSRF-TOKEN": "test_csrf"})


@pytest.fixture
def empty_credential():
    """An empty credential for testing."""
    return Credential(cookies={})


@pytest.fixture
def mock_client(mock_credential):
    """A WeiboClient with a mocked httpx.Client — no real network calls."""
    from weibo_cli.client import WeiboClient

    client = WeiboClient.__new__(WeiboClient)
    client.credential = mock_credential
    client._timeout = 30.0
    client._request_delay = 0  # No delay in tests
    client._base_request_delay = 0
    client._max_retries = 1
    client._last_request_time = 0.0
    client._request_count = 0
    client._rate_limit_count = 0
    client._http = MagicMock()
    return client


@pytest.fixture
def hot_search_response():
    """Minimal hot search API response."""
    return {
        "ok": 1,
        "data": {
            "realtime": [
                {
                    "word": "省考",
                    "num": 1160335,
                    "icon_desc": "沸",
                    "rank": 0,
                    "topic_flag": 0,
                },
                {
                    "word": "申论",
                    "num": 814728,
                    "icon_desc": "",
                    "rank": 1,
                    "topic_flag": 0,
                },
            ],
            "hotgov": {
                "word": "#共赴新程之约#",
                "icon_desc": "热",
            },
        },
    }


@pytest.fixture
def profile_response():
    """Minimal profile API response."""
    return {
        "ok": 1,
        "data": {
            "user": {
                "id": 1699432410,
                "idstr": "1699432410",
                "screen_name": "新华社",
                "verified": True,
                "verified_reason": "新华社官方微博",
                "followers_count": 113614253,
                "friends_count": 3089,
                "statuses_count": 195607,
                "description": "新华社官方微博，重大新闻权威首发平台。",
            },
            "tabList": [{"name": "微博", "tabName": "weibo"}],
        },
    }


@pytest.fixture
def weibo_detail_response():
    """Minimal weibo detail API response."""
    return {
        "ok": 1,
        "visible": {"type": 0, "list_id": 0},
        "created_at": "Sat Mar 14 07:20:55 +0800 2026",
        "id": 5276269143133381,
        "idstr": "5276269143133381",
        "mid": "5276269143133381",
        "mblogid": "Qw06Kd98p",
        "user": {
            "id": 1699432410,
            "screen_name": "新华社",
            "verified": True,
        },
        "text_raw": "测试微博正文",
        "source": "微博视频号",
        "reposts_count": 57,
        "comments_count": 114,
        "attitudes_count": 500,
        "reads_count": 1595668,
        "pic_ids": [],
    }
