---
name: weibo-cli
description: Weibo CLI reverse-engineering notes and API reference for AI agent integration
---

# weibo-cli SKILL

## Overview

`weibo-cli` is a terminal client for Weibo (微博). This document captures the reverse-engineered API details and architecture for AI agent integration.

## Authentication

### QR Code Login Flow

```
GET  passport.weibo.com/sso/signin → X-CSRF-TOKEN cookie
GET  /sso/v2/qrcode/image?entry=miniblog&size=180 → qrid + image URL
     QR data = https://passport.weibo.cn/signin/qrcode/scan?qr={qrid}
GET  /sso/v2/qrcode/check?qrid=...&rid=...&ver=20250520 → poll (2s interval)
     retcode=20000000 → success → follow crossdomain URL for session cookies
```

### Browser Cookie Extraction

Uses `browser-cookie3` subprocess to extract cookies from Chrome/Firefox/Edge/Brave/Arc for `.weibo.com` and `.sina.com` domains.

Required cookies: `SUB`, `SUBP`

## API Reference

Base URL: `https://weibo.com`

All endpoints use `GET` method with `Accept: application/json` header.

### Public APIs (no auth required)

| Endpoint | Description | Key Response Fields |
|----------|-------------|---------------------|
| `/ajax/side/hotSearch` | Hot search sidebar | `data.realtime[].{word, num, icon_desc}` |
| `/ajax/statuses/hot_band` | Hot search full list | `data.band_list[].{note, num, label_name}` |
| `/ajax/feed/allGroups` | Feed group config | `groups[].{gid, title}` |

### Authenticated APIs

| Endpoint | Params | Description |
|----------|--------|-------------|
| `/ajax/feed/hottimeline` | `group_id, count, max_id` | Hot timeline feed |
| `/ajax/profile/info` | `uid` | User profile |
| `/ajax/statuses/mymblog` | `uid, page, feature` | User's weibo list |
| `/ajax/statuses/show` | `id` (mblogid) | Single weibo detail |
| `/ajax/statuses/buildComments` | `id, count, flow` | Comments |
| `/ajax/statuses/repostTimeline` | `id, page, count` | Reposts |
| `/ajax/friendships/friends` | `uid, page` | Following list |
| `/ajax/side/searchBand` | — | Trending sidebar |

### Response Format

```json
{"ok": 1, "data": {...}}     // success
{"ok": -100, "url": "..."}   // session expired
{"ok": 0, "message": "..."}  // error
```

## Anti-Detection Headers

```python
{
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ... Chrome/145.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}
```

## CLI Commands

```
weibo login          # QR code login
weibo hot            # 热搜榜
weibo feed           # 热门 Feed
weibo trending       # 搜索趋势
weibo detail <id>    # 微博详情
weibo comments <id>  # 评论
weibo profile <uid>  # 用户资料
weibo weibos <uid>   # 用户微博列表
weibo following <uid> # 关注列表
```

## Project Structure

```
weibo_cli/
├── __init__.py        # version
├── constants.py       # endpoints, headers
├── exceptions.py      # WeiboApiError hierarchy
├── auth.py            # QR login + browser cookie extraction
├── client.py          # WeiboClient with rate-limit/retry
├── cli.py             # Click entry point
└── commands/
    ├── _common.py     # shared helpers
    ├── auth.py        # login/logout/status/me
    ├── search.py      # hot/feed/detail/comments/trending
    └── personal.py    # profile/weibos/following
```
