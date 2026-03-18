"""API client for Weibo with rate limiting, retry, and anti-detection."""

from __future__ import annotations

import html
import logging
import random
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

from .auth import Credential
from .constants import (
    BASE_URL,
    BUILD_COMMENTS_URL,
    FEED_GROUPS_URL,
    FOLLOWERS_URL,
    FRIENDS_TIMELINE_URL,
    FRIENDS_URL,
    GET_CONFIG_URL,
    HEADERS,
    HOT_BAND_URL,
    HOT_SEARCH_URL,
    HOT_TIMELINE_URL,
    MOBILE_BASE_URL,
    MOBILE_HEADERS,
    MOBILE_SEARCH_URL,
    MY_MBLOG_URL,
    PC_REALTIME_SEARCH_URL,
    PC_SEARCH_BASE_URL,
    PC_SEARCH_HEADERS,
    PROFILE_INFO_URL,
    REPOST_TIMELINE_URL,
    SEARCH_BAND_URL,
    STATUSES_SHOW_URL,
)
from .exceptions import CaptchaChallengeError, WeiboApiError, SessionExpiredError

logger = logging.getLogger(__name__)

_SESSION_EXPIRED_KEYWORDS = ("请先登录", "请登录后使用", "请登录", "用户未登录")
_AUTH_URL_MARKERS = (
    "passport.weibo.com",
    "passport.weibo.cn",
    "login.sina.com.cn",
    "/sso/",
    "/signin",
    "/login.php",
)
_AUTH_HTML_MARKERS = (
    "请先登录",
    "请登录后使用",
    "扫码登录",
    "微博通行证",
    "passport.weibo",
    "login.sina.com",
    "sso/login",
)
_CAPTCHA_KEYWORDS = (
    "验证码",
    "请输入验证码",
    "图形验证码",
    "安全验证",
    "完成验证",
    "异常验证",
)
_CAPTCHA_URL_MARKERS = (
    "captcha",
    "/verify",
    "passport.weibo.com/visitor/visitor",
    "passport.weibo.com/visitor/genvisitor",
)
_PC_SEARCH_PAGE_MARKERS = (
    "<title>微博搜索</title>",
    "$config['product'] = 'search';",
    'class="m-main-nav"',
)
_PC_SEARCH_CARD_RE = re.compile(
    r'<div class="card-wrap" action-type="feed_list_item" mid="(?P<mid>\d+)"(?P<body>.*?)<!--/card-wrap-->',
    re.S,
)
_PC_USER_RE = re.compile(
    r'<a href="(?P<href>//weibo\.com/[^"]+)" class="name"[^>]*>(?P<name>.*?)</a>',
    re.S,
)
_PC_FROM_RE = re.compile(
    r'<div class="from"[^>]*>\s*<a href="(?P<href>//weibo\.com/[^"]+)"[^>]*>\s*(?P<created>.*?)\s*</a>(?P<rest>.*?)</div>',
    re.S,
)
_PC_SOURCE_RE = re.compile(r"来自\s*<a[^>]*>(?P<source>.*?)</a>", re.S)
_PC_TEXT_FULL_RE = re.compile(r'<p class="txt"[^>]*node-type="feed_list_content_full"[^>]*>(?P<text>.*?)</p>', re.S)
_PC_TEXT_RE = re.compile(r'<p class="txt"[^>]*node-type="feed_list_content"[^>]*>(?P<text>.*?)</p>', re.S)
_PC_ACTION_RE = re.compile(r'<a[^>]*action-type="(?P<action>feed_list_(?:forward|comment|like))"[^>]*>(?P<html>.*?)</a>', re.S)
_PC_PIC_IDS_RE = re.compile(r"pic_ids=([^\"&]+)")
_PC_UID_RE = re.compile(r"//weibo\.com/(?:u/)?(?P<uid>\d+)")
_PC_MBLOGID_RE = re.compile(r"//weibo\.com/(?:u/)?\d+/(?P<mblogid>[A-Za-z0-9]+)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_BR_RE = re.compile(r"<br\s*/?>", re.I)
_HTML_IMG_ALT_RE = re.compile(r'<img[^>]+(?:alt|title)="([^"]+)"[^>]*>', re.I)
_HTML_UNFOLD_RE = re.compile(r'<a[^>]*action-type="fl_(?:unfold|fold)"[^>]*>.*?</a>', re.S)


class WeiboClient:
    """Weibo API client with Gaussian jitter, exponential backoff, and session-stable identity.

    Anti-detection strategy:
    - Gaussian jitter delay between requests (~1s mean, σ=0.3)
    - 5% chance of a random long pause (2-5s) to mimic reading behavior
    - Exponential backoff on HTTP 429/5xx (up to 3 retries)
    - Response cookies merged back into session jar
    """

    def __init__(
        self,
        credential: Credential | None = None,
        timeout: float = 30.0,
        request_delay: float = 1.0,
        max_retries: int = 3,
    ):
        self.credential = credential
        self._timeout = timeout
        self._request_delay = request_delay
        self._base_request_delay = request_delay
        self._max_retries = max_retries
        self._last_request_time = 0.0
        self._request_count = 0
        self._rate_limit_count = 0
        self._http: httpx.Client | None = None

    def _build_client(self) -> httpx.Client:
        cookies = {}
        if self.credential:
            cookies = self.credential.cookies_for_target(BASE_URL)
        return httpx.Client(
            base_url=BASE_URL,
            headers=dict(HEADERS),
            cookies=cookies,
            follow_redirects=True,
            timeout=httpx.Timeout(self._timeout),
        )

    @property
    def client(self) -> httpx.Client:
        if not self._http:
            raise RuntimeError("Client not initialized. Use 'with WeiboClient() as client:'")
        return self._http

    def __enter__(self) -> WeiboClient:
        self._http = self._build_client()
        return self

    def __exit__(self, *args: Any) -> None:
        if self._http:
            self._http.close()
            self._http = None

    # ── Rate limiting ───────────────────────────────────────────────

    def _rate_limit_delay(self) -> None:
        if self._request_delay <= 0:
            return
        elapsed = time.time() - self._last_request_time
        if elapsed < self._request_delay:
            jitter = max(0, random.gauss(0.3, 0.15))
            if random.random() < 0.05:
                jitter += random.uniform(2.0, 5.0)
            sleep_time = self._request_delay - elapsed + jitter
            logger.debug("Rate-limit delay: %.2fs", sleep_time)
            time.sleep(sleep_time)

    def _mark_request(self) -> None:
        self._last_request_time = time.time()
        self._request_count += 1

    # ── Response handling ───────────────────────────────────────────

    def _merge_response_cookies(self, resp: httpx.Response) -> None:
        for name, value in resp.cookies.items():
            if value:
                self.client.cookies.set(name, value)

    def _is_auth_url(self, value: Any) -> bool:
        """Return True when *value* points to a known Weibo auth/SSO URL."""
        if not value:
            return False
        url_str = str(value).lower()
        return any(marker in url_str for marker in _AUTH_URL_MARKERS)

    def _is_captcha_url(self, value: Any) -> bool:
        """Return True when *value* looks like a captcha/verification URL."""
        if not value:
            return False
        url_str = str(value).lower()
        return any(marker in url_str for marker in _CAPTCHA_URL_MARKERS)

    def _is_captcha_payload(self, data: dict[str, Any]) -> bool:
        """Detect payloads that require captcha or risk verification."""
        message = str(data.get("msg", data.get("message", "")))
        if any(keyword in message for keyword in _CAPTCHA_KEYWORDS):
            return True

        for field in ("url", "redirect", "login_url", "scheme"):
            if self._is_captcha_url(data.get(field)):
                return True

        return False

    def _is_session_expired_payload(self, data: dict[str, Any]) -> bool:
        """Detect JSON payloads that mean the current login session is invalid."""
        message = str(data.get("msg", data.get("message", "")))
        if any(kw in message for kw in _SESSION_EXPIRED_KEYWORDS):
            return True

        for field in ("url", "redirect", "login_url"):
            if self._is_auth_url(data.get(field)):
                return True

        return False

    def _is_auth_html_response(self, resp: httpx.Response, text: str) -> bool:
        """Detect HTML SSO/login pages returned instead of JSON."""
        if self._is_auth_url(resp.url):
            return True

        text_lower = text.lower()
        return any(marker in text_lower for marker in _AUTH_HTML_MARKERS)

    def _is_captcha_html_response(self, resp: httpx.Response, text: str) -> bool:
        """Detect captcha/verification HTML pages returned instead of JSON."""
        if self._is_captcha_url(resp.url):
            return True

        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in _CAPTCHA_KEYWORDS)

    def _handle_response(self, data: dict[str, Any], action: str, *, unwrap: bool = True) -> dict[str, Any]:
        """Validate API response.

        Weibo uses {ok: 1, data: {...}} format for most endpoints.
        When unwrap=True (default), extract and return data["data"].
        When unwrap=False, return the full response dict (for APIs that don't wrap data).
        """
        ok = data.get("ok")

        if ok == -100:
            if self._is_captcha_payload(data):
                raise CaptchaChallengeError()
            raise SessionExpiredError()

        message = data.get("msg", data.get("message", "Unknown error"))

        if ok == 0:
            if self._is_captcha_payload(data):
                raise CaptchaChallengeError()
            if self._is_session_expired_payload(data):
                raise SessionExpiredError()
            raise WeiboApiError(f"{action}: {message} (ok={ok})", code=ok, response=data)

        if ok == 1:
            return data.get("data", data) if unwrap else data

        # ok is some other truthy value (e.g. raw APIs return full dict)
        if ok:
            return data.get("data", data) if unwrap else data

        raise WeiboApiError(f"{action}: {message} (ok={ok})", code=ok, response=data)

    # ── Request with retry ──────────────────────────────────────────

    def _request_response(self, method: str, url: str, *, client: httpx.Client | None = None, **kwargs) -> httpx.Response:
        self._rate_limit_delay()
        last_exc: Exception | None = None
        http = client or self.client

        for attempt in range(self._max_retries):
            t0 = time.time()
            try:
                resp = http.request(method, url, **kwargs)
                elapsed = time.time() - t0
                if not client:  # only merge cookies for the main client
                    self._merge_response_cookies(resp)
                self._mark_request()

                logger.info("[#%d] %s %s → %d (%.2fs)", self._request_count, method, url[:60], resp.status_code, elapsed)

                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning("HTTP %d, retrying in %.1fs (%d/%d)", resp.status_code, wait, attempt + 1, self._max_retries)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                return resp

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                wait = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait)

        if last_exc:
            raise WeiboApiError(f"Request failed after {self._max_retries} retries: {last_exc}") from last_exc
        raise WeiboApiError(f"Request failed after {self._max_retries} retries")

    def _request(self, method: str, url: str, *, client: httpx.Client | None = None, **kwargs) -> dict[str, Any]:
        resp = self._request_response(method, url, client=client, **kwargs)
        text = resp.text
        if text.lstrip().startswith("<"):
            if self._is_captcha_html_response(resp, text):
                raise CaptchaChallengeError()
            if self._is_auth_html_response(resp, text):
                raise SessionExpiredError()
            raise WeiboApiError(f"Received HTML instead of JSON from {url}")
        try:
            return resp.json()
        except ValueError as exc:
            raise WeiboApiError(f"Invalid JSON response from {url}") from exc

    def _request_html(self, method: str, url: str, *, client: httpx.Client | None = None, **kwargs) -> str:
        resp = self._request_response(method, url, client=client, **kwargs)
        text = resp.text
        if self._is_captcha_html_response(resp, text):
            raise CaptchaChallengeError()
        if self._is_auth_html_response(resp, text):
            raise SessionExpiredError()
        return text

    def _get(self, url: str, params: dict[str, Any] | None = None, action: str = "", *, unwrap: bool = True) -> dict[str, Any]:
        data = self._request("GET", url, params=params)
        return self._handle_response(data, action, unwrap=unwrap)

    # ── Hot Search / Trending ───────────────────────────────────────

    def get_hot_search(self) -> dict[str, Any]:
        """Get hot search list (微博热搜 sidebar, ~52 items)."""
        return self._get(HOT_SEARCH_URL, action="热搜")

    def get_hot_band(self) -> dict[str, Any]:
        """Get full hot band list (微博热搜榜)."""
        return self._get(HOT_BAND_URL, action="热搜榜")

    def get_search_band(self) -> dict[str, Any]:
        """Get search band (trending sidebar, ~16 items)."""
        return self._get(SEARCH_BAND_URL, action="搜索推荐")

    # ── Feed / Timeline ─────────────────────────────────────────────

    def get_hot_timeline(self, group_id: str = "102803", count: int = 10, max_id: str = "0") -> dict[str, Any]:
        """Get hot timeline (热门微博 feed)."""
        return self._get(HOT_TIMELINE_URL, params={
            "since_id": "0", "refresh": "0",
            "group_id": group_id, "containerid": group_id,
            "extparam": "discover|new_feed",
            "max_id": max_id, "count": str(count),
        }, action="热门Feed", unwrap=False)

    def get_friends_timeline(self, count: int = 20, max_id: str = "0", list_id: str = "0") -> dict[str, Any]:
        """Get friends timeline (关注者 feed, requires auth)."""
        return self._get(FRIENDS_TIMELINE_URL, params={
            "count": str(count), "max_id": max_id, "list_id": list_id,
        }, action="关注Feed", unwrap=False)

    def get_feed_groups(self) -> dict[str, Any]:
        """Get feed group configuration."""
        return self._get(FEED_GROUPS_URL, params={"is_new_segment": "1", "fetch_hot": "1"}, action="Feed分组", unwrap=False)

    # ── User / Profile ──────────────────────────────────────────────

    def get_profile(self, uid: str) -> dict[str, Any]:
        """Get user profile info."""
        return self._get(PROFILE_INFO_URL, params={"uid": uid}, action="用户资料")

    def get_user_weibos(self, uid: str, page: int = 1, count: int = 20, feature: int = 0) -> dict[str, Any]:
        """Get user's weibo list."""
        return self._get(MY_MBLOG_URL, params={
            "uid": uid, "page": str(page), "feature": str(feature),
        }, action="用户微博")

    # ── Weibo Detail ────────────────────────────────────────────────

    def get_weibo_detail(self, mblogid: str) -> dict[str, Any]:
        """Get single weibo detail by mblogid (e.g. 'Qw06Kd98p')."""
        return self._get(STATUSES_SHOW_URL, params={"id": mblogid}, action="微博详情", unwrap=False)

    # ── Comments / Reposts ──────────────────────────────────────────

    def get_comments(self, weibo_id: str, count: int = 20, max_id: int = 0) -> dict[str, Any]:
        """Get comments for a weibo."""
        params: dict[str, Any] = {"id": weibo_id, "is_show_bulletin": "2", "count": str(count), "flow": "0"}
        if max_id:
            params["max_id"] = str(max_id)
        return self._get(BUILD_COMMENTS_URL, params=params, action="评论")

    def get_reposts(self, weibo_id: str, page: int = 1, count: int = 10) -> dict[str, Any]:
        """Get repost/forward list for a weibo."""
        return self._get(REPOST_TIMELINE_URL, params={
            "id": weibo_id, "page": str(page), "count": str(count),
        }, action="转发", unwrap=False)

    # ── Social ──────────────────────────────────────────────────────

    def get_following(self, uid: str, page: int = 1) -> dict[str, Any]:
        """Get user's following list."""
        return self._get(FRIENDS_URL, params={"uid": uid, "page": str(page)}, action="关注列表", unwrap=False)

    def get_followers(self, uid: str, page: int = 1) -> dict[str, Any]:
        """Get user's follower list."""
        return self._get(FOLLOWERS_URL, params={
            "uid": uid, "page": str(page), "relate": "fans",
        }, action="粉丝列表", unwrap=False)

    # ── Search ──────────────────────────────────────────────────────

    def _build_mobile_client(self) -> httpx.Client:
        """Build a mobile API client for m.weibo.cn endpoints."""
        cookies = self.credential.cookies_for_target(MOBILE_BASE_URL) if self.credential else {}
        headers = dict(MOBILE_HEADERS)
        xsrf_token = cookies.get("XSRF-TOKEN") or cookies.get("SRF")
        if xsrf_token:
            headers["x-xsrf-token"] = xsrf_token
        return httpx.Client(
            base_url=MOBILE_BASE_URL,
            headers=headers,
            cookies=cookies,
            follow_redirects=True,
            timeout=httpx.Timeout(self._timeout),
        )

    def _build_pc_search_client(self) -> httpx.Client:
        """Build a desktop search client for s.weibo.com HTML search."""
        cookies = self.credential.cookies_for_target(BASE_URL) if self.credential else {}
        return httpx.Client(
            base_url=PC_SEARCH_BASE_URL,
            headers=dict(PC_SEARCH_HEADERS),
            cookies=cookies,
            follow_redirects=True,
            timeout=httpx.Timeout(self._timeout),
        )

    def _strip_html_fragment(self, fragment: str) -> str:
        """Convert an HTML fragment from PC search into readable plain text."""
        text = fragment or ""
        text = _HTML_UNFOLD_RE.sub("", text)
        text = _HTML_IMG_ALT_RE.sub(lambda match: match.group(1), text)
        text = _HTML_BR_RE.sub("\n", text)
        text = _HTML_TAG_RE.sub("", text)
        text = html.unescape(text).replace("\u200b", "")
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line).strip()

    def _extract_pc_action_counts(self, block: str) -> dict[str, int]:
        counts = {
            "feed_list_forward": 0,
            "feed_list_comment": 0,
            "feed_list_like": 0,
        }
        for match in _PC_ACTION_RE.finditer(block):
            action = match.group("action")
            text = self._strip_html_fragment(match.group("html"))
            digits = re.search(r"\d[\d,]*", text)
            counts[action] = int(digits.group(0).replace(",", "")) if digits else 0
        return counts

    def _build_search_result(self, statuses: list[dict[str, Any]], *, source: str) -> dict[str, Any]:
        return {
            "ok": 1,
            "search_source": source,
            "data": {
                "cards": [{"card_type": 9, "mblog": status} for status in statuses],
            },
        }

    def _parse_pc_search_card(self, mid: str, block: str) -> dict[str, Any] | None:
        user_match = _PC_USER_RE.search(block)
        from_match = _PC_FROM_RE.search(block)
        if not user_match or not from_match:
            return None

        user_href = user_match.group("href")
        weibo_href = from_match.group("href")
        uid_match = _PC_UID_RE.search(user_href)
        if not uid_match:
            return None

        full_text_match = _PC_TEXT_FULL_RE.search(block)
        text_match = full_text_match or _PC_TEXT_RE.search(block)
        text_raw = self._strip_html_fragment(text_match.group("text")) if text_match else ""

        source_match = _PC_SOURCE_RE.search(from_match.group("rest"))
        counts = self._extract_pc_action_counts(block)
        pic_ids_match = _PC_PIC_IDS_RE.search(block)
        pic_ids = [pic_id for pic_id in (pic_ids_match.group(1).split(",") if pic_ids_match else []) if pic_id]
        mblogid_match = _PC_MBLOGID_RE.search(weibo_href)

        uid = uid_match.group("uid")
        return {
            "id": int(mid),
            "idstr": mid,
            "mid": mid,
            "mblogid": mblogid_match.group("mblogid") if mblogid_match else "",
            "created_at": self._strip_html_fragment(from_match.group("created")),
            "source": self._strip_html_fragment(source_match.group("source")) if source_match else "",
            "text_raw": text_raw,
            "reposts_count": counts["feed_list_forward"],
            "comments_count": counts["feed_list_comment"],
            "attitudes_count": counts["feed_list_like"],
            "pic_ids": pic_ids,
            "user": {
                "id": int(uid),
                "idstr": uid,
                "screen_name": self._strip_html_fragment(user_match.group("name")),
                "verified": "woo-avatar-icon" in block,
                "profile_url": f"https:{user_href}" if user_href.startswith("//") else user_href,
            },
        }

    def _parse_pc_search_html(self, html_text: str) -> dict[str, Any]:
        card_matches = list(_PC_SEARCH_CARD_RE.finditer(html_text))
        if not card_matches:
            if any(marker in html_text.lower() for marker in _PC_SEARCH_PAGE_MARKERS):
                return self._build_search_result([], source="pc")
            raise WeiboApiError("PC 搜索未返回可解析页面")

        statuses: list[dict[str, Any]] = []
        for match in card_matches:
            status = self._parse_pc_search_card(match.group("mid"), match.group(0))
            if status:
                statuses.append(status)

        if not statuses:
            raise WeiboApiError("PC 搜索解析失败")

        return self._build_search_result(statuses, source="pc")

    def search_weibo_pc(self, keyword: str, page: int = 1) -> dict[str, Any]:
        """Search weibos by keyword using the desktop HTML search page."""
        params = {
            "q": keyword,
            "rd": "realtime",
            "tw": "realtime",
            "Refer": "weibo_realtime",
            "page": str(page),
        }
        headers = {
            "Referer": f"{PC_SEARCH_BASE_URL}/realtime?q={quote(keyword)}&rd=realtime&tw=realtime&Refer=weibo_realtime&page={page}",
        }
        with self._build_pc_search_client() as pc:
            html_text = self._request_html("GET", PC_REALTIME_SEARCH_URL, params=params, headers=headers, client=pc)
        return self._parse_pc_search_html(html_text)

    def search_weibo_mobile(self, keyword: str, page: int = 1) -> dict[str, Any]:
        """Search weibos by keyword using the mobile JSON API."""
        containerid = f"100103type=61&q={keyword}"
        params = {
            "containerid": containerid,
            "page_type": "searchall",
        }
        if page > 1:
            params["page"] = str(page)

        headers = {
            "Referer": f"{MOBILE_BASE_URL}/search?containerid={quote(containerid, safe='')}",
        }
        with self._build_mobile_client() as mobile:
            data = self._request("GET", MOBILE_SEARCH_URL, params=params, headers=headers, client=mobile)
        result = self._handle_response(data, "搜索", unwrap=False)
        result["search_source"] = "mobile"
        return result

    def search_weibo(self, keyword: str, page: int = 1) -> dict[str, Any]:
        """Search weibos by keyword, preferring PC search with mobile fallback."""
        try:
            return self.search_weibo_pc(keyword, page=page)
        except WeiboApiError as exc:
            logger.warning("PC search failed, falling back to mobile search: %s", exc)
            return self.search_weibo_mobile(keyword, page=page)

    # ── Config ──────────────────────────────────────────────────────

    def get_config(self) -> dict[str, Any]:
        """Get app configuration (contains current user info)."""
        return self._get(GET_CONFIG_URL, action="配置")
