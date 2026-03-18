"""Tests for _common.py utilities and new API methods."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

from weibo_cli.auth import Credential
from weibo_cli.commands import auth as auth_commands
from weibo_cli.commands.auth import (
    _extract_current_uid_from_feed_groups,
    _extract_current_uid_from_homepage_html,
)
from weibo_cli.commands._common import format_count, strip_html
from weibo_cli.exceptions import CaptchaChallengeError, SessionExpiredError, WeiboApiError


# ── strip_html tests ─────────────────────────────────────────────────


class TestStripHtml:
    def test_basic_tags(self):
        assert strip_html("<b>hello</b>") == "hello"

    def test_nested_tags(self):
        assert strip_html("<a href='#'><span>link</span></a>") == "link"

    def test_empty_string(self):
        assert strip_html("") == ""

    def test_none_input(self):
        assert strip_html(None) == ""

    def test_no_tags(self):
        assert strip_html("plain text") == "plain text"

    def test_self_closing_tags(self):
        assert strip_html("hello<br/>world") == "helloworld"

    def test_mixed_content(self):
        assert strip_html("Hello <b>world</b>! <i>Good</i>") == "Hello world! Good"


# ── format_count tests ──────────────────────────────────────────────


class TestFormatCount:
    def test_small_number(self):
        assert format_count(1000) == "1000"

    def test_exact_10000(self):
        assert format_count(10000) == "1.0万"

    def test_large_number(self):
        assert format_count(113614253) == "11361.4万"

    def test_string_input(self):
        assert format_count("5000") == "5000"

    def test_string_large(self):
        assert format_count("50000") == "5.0万"

    def test_invalid_string(self):
        assert format_count("abc") == "abc"

    def test_none_input(self):
        assert format_count(None) == "None"

    def test_zero(self):
        assert format_count(0) == "0"


class TestCurrentUidExtraction:
    def test_extract_uid_from_feed_groups(self):
        data = {
            "groups": [
                {"title": "默认分组", "group": [{"gid": "1", "uid": "6205005713", "title": "全部关注"}]},
            ],
        }
        assert _extract_current_uid_from_feed_groups(data) == "6205005713"

    def test_extract_uid_from_feed_groups_missing(self):
        assert _extract_current_uid_from_feed_groups({"groups": [{"group": [{}]}]}) is None

    def test_extract_uid_from_homepage_html(self):
        html = '<script>window.__INITIAL_STATE__={"uid":6205005713,"apmSampleRate":0.01}</script>'
        assert _extract_current_uid_from_homepage_html(html) == "6205005713"

    def test_extract_uid_from_homepage_html_missing(self):
        assert _extract_current_uid_from_homepage_html("<html></html>") is None


# ── _handle_response unwrap tests ────────────────────────────────────


class TestHandleResponseUnwrap:
    def test_unwrap_true_extracts_data(self, mock_client):
        raw = {"ok": 1, "data": {"items": [1, 2, 3]}}
        result = mock_client._handle_response(raw, "test", unwrap=True)
        assert result == {"items": [1, 2, 3]}

    def test_unwrap_false_returns_full(self, mock_client):
        raw = {"ok": 1, "data": {"items": [1, 2, 3]}}
        result = mock_client._handle_response(raw, "test", unwrap=False)
        assert result == raw

    def test_unwrap_false_with_raw_api(self, mock_client):
        """APIs like statuses/show return data at top level, not wrapped."""
        raw = {"ok": 1, "mblogid": "abc", "text": "hello"}
        result = mock_client._handle_response(raw, "test", unwrap=False)
        assert result == raw
        assert result["mblogid"] == "abc"

    def test_session_expired_precise_match(self, mock_client):
        """Only precise keywords should trigger SessionExpiredError."""
        raw = {"ok": 0, "message": "请先登录"}
        with pytest.raises(SessionExpiredError):
            mock_client._handle_response(raw, "test")

    def test_login_related_not_falsely_matched(self, mock_client):
        """Messages containing '登录' but not matching keywords should raise WeiboApiError."""
        raw = {"ok": 0, "message": "登录设备异常"}
        with pytest.raises(WeiboApiError, match="登录设备异常"):
            mock_client._handle_response(raw, "test")

    def test_auth_url_in_payload_raises_session_expired(self, mock_client):
        raw = {
            "ok": 0,
            "message": "需要跳转",
            "url": "https://passport.weibo.com/sso/signin?entry=miniblog",
        }
        with pytest.raises(SessionExpiredError):
            mock_client._handle_response(raw, "test")

    def test_captcha_url_in_payload_raises_captcha_required(self, mock_client):
        raw = {
            "ok": 0,
            "message": "请完成安全验证",
            "url": "https://passport.weibo.com/verify?from=search",
        }
        with pytest.raises(CaptchaChallengeError):
            mock_client._handle_response(raw, "test")


# ── New API method tests ─────────────────────────────────────────────


def _mock_response(data, *, url="https://weibo.com/ajax/test"):
    """Create a mock httpx response for the given data."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = json.dumps(data)
    resp.json.return_value = data
    resp.cookies = httpx.Cookies()
    resp.url = httpx.URL(url)
    return resp


def _mock_html_response(html, *, url):
    """Create a mock HTML response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = html
    resp.cookies = httpx.Cookies()
    resp.url = httpx.URL(url)
    return resp


def _pc_search_html():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>微博搜索</title>
    <script>
        var $CONFIG = {};
        $CONFIG['product'] = 'search';
    </script>
</head>
<body>
<div class="card-wrap" action-type="feed_list_item" mid="5277908669302546" >
    <div class="card">
        <div class="card-feed">
            <div class="avator">
                <a href="//weibo.com/7499890871?refer_flag=1001030103_"><span class="woo-avatar-icon"></span></a>
            </div>
            <div class="content" node-type="like">
                <div class="info">
                    <div style="padding: 6px 0 3px;">
                        <a href="//weibo.com/7499890871?refer_flag=1001030103_" class="name" target="_blank">云养芋头</a>
                    </div>
                </div>
                <div class="from">
                    <a href="//weibo.com/7499890871/QwGL8D214?refer_flag=1001030103_" target="_blank">
                        1分钟前
                    </a>
                    &nbsp;来自 <a href="//weibo.com/" rel="nofollow">冬天的第一场雪</a>
                </div>
                <p class="txt" node-type="feed_list_content" nick-name="云养芋头">
                    我是真想吃喜茶的蛋挞<img src="https://face.t.sinajs.cn/test.png" title="[并不简单]" alt="[并不简单]" class="face" />
                </p>
            </div>
        </div>
        <div class="card-act">
            <ul>
                <li><a action-type="feed_list_forward">转发</a></li>
                <li><a action-type="feed_list_comment"><span>3</span></a></li>
                <li><a action-type="feed_list_like"><button><span class="woo-like-count">12</span></button></a></li>
            </ul>
        </div>
    </div>
</div>
<!--/card-wrap-->
<div class="card-wrap" action-type="feed_list_item" mid="5277908253018454" >
    <div class="card">
        <div class="card-feed">
            <div class="content" node-type="like">
                <div class="info">
                    <div style="padding: 6px 0 3px;">
                        <a href="//weibo.com/5229243284?refer_flag=1001030103_" class="name" target="_blank">-Pizzzal-</a>
                    </div>
                </div>
                <div class="from">
                    <a href="//weibo.com/5229243284/QwGKtcFeK?refer_flag=1001030103_" target="_blank">
                        3分钟前
                    </a>
                    &nbsp;来自 <a href="//weibo.com/" rel="nofollow">iPhone客户端</a>
                </div>
                <p class="txt" node-type="feed_list_content" nick-name="-Pizzzal-">
                    今天感觉特别幸福<br/>其实只是很平淡的一天。<a href="//weibo.com/5229243284/QwGKtcFeK?refer_flag=1001030103_" action-type="fl_unfold" target="_blank">展开<i class="wbicon">c</i></a>
                </p>
                <p class="txt" node-type="feed_list_content_full" nick-name="-Pizzzal-" style="display: none">
                    今天感觉特别幸福<br/>其实只是很平淡的一天。<br/>所以最后我俩一人一杯喜茶。
                </p>
                <div node-type="feed_list_media_prev">
                    <div action-data="uid=5229243284&mid=5277908253018454&pic_ids=502bae5a1,502bae5a2"></div>
                </div>
            </div>
        </div>
        <div class="card-act">
            <ul>
                <li><a action-type="feed_list_forward">8</a></li>
                <li><a action-type="feed_list_comment">评论</a></li>
                <li><a action-type="feed_list_like"><button><span class="woo-like-count">赞</span></button></a></li>
            </ul>
        </div>
    </div>
</div>
<!--/card-wrap-->
</body>
</html>
"""


class TestGetFollowersAPI:
    def test_get_followers_passes_params(self, mock_client):
        response = {"ok": 1, "users": [{"screen_name": "test"}]}
        mock_client._http.request.return_value = _mock_response(response)

        result = mock_client.get_followers("12345", page=2)
        params = mock_client._http.request.call_args[1].get("params", {})
        assert params["uid"] == "12345"
        assert params["page"] == "2"
        assert params["relate"] == "fans"
        assert "users" in result


class TestGetFriendsTimelineAPI:
    def test_get_friends_timeline_default(self, mock_client):
        response = {"ok": 1, "statuses": [], "max_id": "0"}
        mock_client._http.request.return_value = _mock_response(response)

        result = mock_client.get_friends_timeline()
        params = mock_client._http.request.call_args[1].get("params", {})
        assert params["count"] == "20"
        assert params["max_id"] == "0"
        assert params["list_id"] == "0"
        assert "statuses" in result


class TestGetFollowingAPI:
    def test_get_following_passes_uid(self, mock_client):
        response = {"ok": 1, "users": []}
        mock_client._http.request.return_value = _mock_response(response)

        mock_client.get_following("12345")
        params = mock_client._http.request.call_args[1].get("params", {})
        assert params["uid"] == "12345"
        assert params["page"] == "1"


class TestGetConfigAPI:
    def test_get_config_returns_data(self, mock_client):
        response = {"ok": 1, "data": {"uid": "12345", "login": True}}
        mock_client._http.request.return_value = _mock_response(response)

        result = mock_client.get_config()
        assert result["uid"] == "12345"


class TestSearchWeiboAPI:
    def test_search_weibo_pc_parses_html_results(self, mock_client):
        mock_pc = MagicMock()
        mock_pc.__enter__ = MagicMock(return_value=mock_pc)
        mock_pc.__exit__ = MagicMock(return_value=False)
        mock_pc.request.return_value = _mock_html_response(
            _pc_search_html(),
            url="https://s.weibo.com/realtime?q=%E5%96%9C%E8%8C%B6&rd=realtime&tw=realtime&Refer=weibo_realtime&page=1",
        )

        with patch.object(mock_client, "_build_pc_search_client", return_value=mock_pc):
            result = mock_client.search_weibo_pc("喜茶")

        assert result["search_source"] == "pc"
        cards = result["data"]["cards"]
        assert len(cards) == 2

        first = cards[0]["mblog"]
        assert first["mid"] == "5277908669302546"
        assert first["mblogid"] == "QwGL8D214"
        assert first["created_at"] == "1分钟前"
        assert first["source"] == "冬天的第一场雪"
        assert first["text_raw"] == "我是真想吃喜茶的蛋挞[并不简单]"
        assert first["comments_count"] == 3
        assert first["attitudes_count"] == 12
        assert first["user"]["screen_name"] == "云养芋头"
        assert first["user"]["verified"] is True

        second = cards[1]["mblog"]
        assert second["mblogid"] == "QwGKtcFeK"
        assert second["text_raw"] == "今天感觉特别幸福\n其实只是很平淡的一天。\n所以最后我俩一人一杯喜茶。"
        assert second["pic_ids"] == ["502bae5a1", "502bae5a2"]
        assert second["reposts_count"] == 8
        assert second["comments_count"] == 0
        assert second["attitudes_count"] == 0

    def test_search_weibo_prefers_pc_before_mobile(self, mock_client):
        pc_result = {"ok": 1, "search_source": "pc", "data": {"cards": []}}
        with patch.object(mock_client, "search_weibo_pc", return_value=pc_result) as mock_pc, \
             patch.object(mock_client, "search_weibo_mobile") as mock_mobile:
            result = mock_client.search_weibo("test")

        assert result == pc_result
        mock_pc.assert_called_once_with("test", page=1)
        mock_mobile.assert_not_called()

    def test_search_weibo_falls_back_to_mobile_when_pc_fails(self, mock_client):
        search_response = {"ok": 1, "data": {"cards": []}}
        with patch.object(mock_client, "search_weibo_pc", side_effect=WeiboApiError("pc failed")) as mock_pc, \
             patch.object(mock_client, "search_weibo_mobile", return_value=search_response) as mock_mobile:
            result = mock_client.search_weibo("test")

        assert result == search_response
        mock_pc.assert_called_once_with("test", page=1)
        mock_mobile.assert_called_once_with("test", page=1)

    def test_search_weibo_mobile_uses_mobile_client(self, mock_client):
        """Verify mobile search creates a separate mobile client."""
        search_response = {"ok": 1, "data": {"cards": []}}
        mock_mobile = MagicMock()
        mock_mobile.__enter__ = MagicMock(return_value=mock_mobile)
        mock_mobile.__exit__ = MagicMock(return_value=False)
        mock_mobile.request.return_value = _mock_response(search_response)

        with patch.object(mock_client, "_build_mobile_client", return_value=mock_mobile):
            result = mock_client.search_weibo_mobile("test")

        assert result["search_source"] == "mobile"
        mock_mobile.request.assert_called_once()
        call_args = mock_mobile.request.call_args
        assert call_args[1]["params"]["containerid"] == "100103type=61&q=test"
        assert "page" not in call_args[1]["params"]
        assert call_args[1]["headers"]["Referer"].endswith("containerid=100103type%3D61%26q%3Dtest")

    def test_search_weibo_mobile_login_payload_raises_session_expired(self, mock_client):
        response = {"ok": 0, "message": "请先登录"}
        mock_mobile = MagicMock()
        mock_mobile.__enter__ = MagicMock(return_value=mock_mobile)
        mock_mobile.__exit__ = MagicMock(return_value=False)
        mock_mobile.request.return_value = _mock_response(
            response,
            url="https://m.weibo.cn/api/container/getIndex",
        )

        with patch.object(mock_client, "_build_mobile_client", return_value=mock_mobile):
            with pytest.raises(SessionExpiredError):
                mock_client.search_weibo_mobile("test")

    def test_search_weibo_mobile_html_login_page_raises_session_expired(self, mock_client):
        html = "<html><title>微博通行证</title><body>请先登录</body></html>"
        mock_mobile = MagicMock()
        mock_mobile.__enter__ = MagicMock(return_value=mock_mobile)
        mock_mobile.__exit__ = MagicMock(return_value=False)
        mock_mobile.request.return_value = _mock_html_response(
            html,
            url="https://passport.weibo.com/sso/signin?entry=miniblog",
        )

        with patch.object(mock_client, "_build_mobile_client", return_value=mock_mobile):
            with pytest.raises(SessionExpiredError):
                mock_client.search_weibo_mobile("test")

    def test_search_weibo_mobile_html_captcha_page_raises_captcha_required(self, mock_client):
        html = "<html><title>安全验证</title><body>请输入验证码</body></html>"
        mock_mobile = MagicMock()
        mock_mobile.__enter__ = MagicMock(return_value=mock_mobile)
        mock_mobile.__exit__ = MagicMock(return_value=False)
        mock_mobile.request.return_value = _mock_html_response(
            html,
            url="https://passport.weibo.com/verify?from=search",
        )

        with patch.object(mock_client, "_build_mobile_client", return_value=mock_mobile):
            with pytest.raises(CaptchaChallengeError):
                mock_client.search_weibo_mobile("test")

    def test_search_weibo_mobile_generic_html_stays_api_error(self, mock_client):
        html = "<html><body><h1>502 Bad Gateway</h1></body></html>"
        mock_mobile = MagicMock()
        mock_mobile.__enter__ = MagicMock(return_value=mock_mobile)
        mock_mobile.__exit__ = MagicMock(return_value=False)
        mock_mobile.request.return_value = _mock_html_response(
            html,
            url="https://m.weibo.cn/api/container/getIndex",
        )

        with patch.object(mock_client, "_build_mobile_client", return_value=mock_mobile):
            with pytest.raises(WeiboApiError, match="Received HTML instead of JSON"):
                mock_client.search_weibo_mobile("test")


class TestMeCommand:
    def test_me_uses_feed_groups_fallback(self, monkeypatch):
        runner = CliRunner()
        expected = {"user": {"screen_name": "测试用户", "followers_count": 1}}

        class FakeClient:
            def __init__(self):
                self.client = MagicMock()

            def _get(self, path, action=""):
                raise WeiboApiError(f"{action}: not found")

            def get_feed_groups(self):
                return {"groups": [{"group": [{"uid": "6205005713"}]}]}

            def get_profile(self, uid):
                assert uid == "6205005713"
                return expected

        monkeypatch.setattr(auth_commands, "require_auth", lambda: Credential(cookies={"SUB": "test"}))

        def fake_handle_command(credential, *, action, render=None, as_json=False, as_yaml=False):
            data = action(FakeClient())
            print(json.dumps(data, ensure_ascii=False))
            return data

        monkeypatch.setattr(auth_commands, "handle_command", fake_handle_command)

        result = runner.invoke(auth_commands.me, ["--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["user"]["screen_name"] == "测试用户"

    def test_me_uses_homepage_html_fallback(self, monkeypatch):
        runner = CliRunner()
        expected = {"user": {"screen_name": "首页用户", "followers_count": 2}}

        class FakeClient:
            def __init__(self):
                response = MagicMock()
                response.text = '<script>window.__INITIAL_STATE__={"uid":6205005713,"apmSampleRate":0.01}</script>'
                response.raise_for_status.return_value = None
                self.client = MagicMock()
                self.client.get.return_value = response

            def _get(self, path, action=""):
                raise WeiboApiError(f"{action}: not found")

            def get_feed_groups(self):
                raise WeiboApiError("Feed分组: unavailable")

            def get_profile(self, uid):
                assert uid == "6205005713"
                return expected

        monkeypatch.setattr(auth_commands, "require_auth", lambda: Credential(cookies={"SUB": "test"}))

        def fake_handle_command(credential, *, action, render=None, as_json=False, as_yaml=False):
            data = action(FakeClient())
            print(json.dumps(data, ensure_ascii=False))
            return data

        monkeypatch.setattr(auth_commands, "handle_command", fake_handle_command)

        result = runner.invoke(auth_commands.me, ["--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["user"]["screen_name"] == "首页用户"
