"""Auth commands: login, logout, status."""

from __future__ import annotations

import json
import re

import click
from rich.panel import Panel

from ._common import console, handle_command, require_auth, structured_output_options


_CURRENT_UID_HTML_PATTERNS = (
    r'"uid"\s*:\s*(\d{5,})\s*,\s*"apmSampleRate"',
    r'\$CONFIG\[\s*["\']uid["\']\s*\]\s*=\s*["\'](\d+)',
)


def _extract_current_uid_from_feed_groups(data):
    """Extract the current account UID from feed group configuration."""
    if not isinstance(data, dict):
        return None

    for section in data.get("groups", []):
        groups = section.get("group", []) if isinstance(section, dict) else []
        for group in groups:
            uid = group.get("uid") if isinstance(group, dict) else None
            if uid:
                return str(uid)
    return None


def _extract_current_uid_from_homepage_html(html: str) -> str | None:
    """Extract the current account UID from the logged-in homepage HTML."""
    if not html:
        return None

    for pattern in _CURRENT_UID_HTML_PATTERNS:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


@click.command()
@click.option("--qrcode", is_flag=True, help="直接使用二维码扫码登录（跳过浏览器 Cookie 提取）")
@click.option("--cookie-source", type=str, default=None, help="指定浏览器 (chrome/firefox/edge/brave/arc/...)")
def login(qrcode, cookie_source):
    """登录微博（自动提取浏览器 Cookie 或 --qrcode 扫码）"""
    from ..auth import extract_browser_credential, get_credential, qr_login

    if qrcode:
        # Skip browser cookies, go straight to QR login
        try:
            cred = qr_login()
            if cred:
                console.print("[green]✅ 登录成功！[/green]")
            else:
                console.print("[red]❌ 登录失败[/red]")
        except Exception as e:
            console.print(f"[red]❌ 登录失败: {e}[/red]")
        return

    if cookie_source:
        # Try specific browser only
        cred = extract_browser_credential(cookie_source=cookie_source)
        if cred:
            console.print(f"[green]✅ 已从 {cookie_source} 提取 Cookie 并登录[/green]")
        else:
            console.print(f"[yellow]⚠️  未在 {cookie_source} 找到有效 Cookie[/yellow]")
            console.print("  提示: 使用 [bold]weibo login --qrcode[/bold] 扫码登录")
        return

    # Default: try saved → browser → QR
    cred = get_credential()
    if cred:
        console.print("[green]✅ 已登录[/green] (如需重新登录请先执行 weibo logout)")
        return

    try:
        cred = qr_login()
        if cred:
            console.print("[green]✅ 登录成功！[/green]")
        else:
            console.print("[red]❌ 登录失败[/red]")
    except Exception as e:
        console.print(f"[red]❌ 登录失败: {e}[/red]")


@click.command()
def logout():
    """清除已保存的登录凭证"""
    from ..auth import clear_credential

    clear_credential()
    console.print("[green]✅ 已清除登录凭证[/green]")


@click.command()
@structured_output_options
def status(as_json, as_yaml):
    """查看当前登录状态"""
    import sys

    from ..auth import get_credential

    cred = get_credential()
    info = {
        "authenticated": cred is not None,
        "cookie_count": len(cred.cookies) if cred else 0,
    }
    if as_json:
        click.echo(json.dumps(info, indent=2))
    elif as_yaml or not sys.stdout.isatty():
        try:
            import yaml
            click.echo(yaml.dump(info, allow_unicode=True, default_flow_style=False))
        except ImportError:
            click.echo(json.dumps(info, indent=2))
    else:
        if cred:
            console.print(f"[green]✅ 已登录[/green] ({len(cred.cookies)} cookies)")
        else:
            console.print("[yellow]⚠️  未登录[/yellow]")


@click.command()
@structured_output_options
def me(as_json, as_yaml):
    """查看个人资料"""
    cred = require_auth()

    def _render(data):
        user = data.get("user", data)
        lines = []
        if user.get("screen_name"):
            lines.append(f"[bold]昵称[/bold]: {user['screen_name']}")
        if user.get("description"):
            lines.append(f"[bold]简介[/bold]: {user['description']}")
        if user.get("followers_count") is not None:
            lines.append(f"[bold]粉丝[/bold]: {user['followers_count']}")
        if user.get("friends_count") is not None:
            lines.append(f"[bold]关注[/bold]: {user['friends_count']}")
        if user.get("statuses_count") is not None:
            lines.append(f"[bold]微博[/bold]: {user['statuses_count']}")
        if user.get("location"):
            lines.append(f"[bold]位置[/bold]: {user['location']}")
        if user.get("verified_reason"):
            lines.append(f"[bold]认证[/bold]: {user['verified_reason']}")
        text = "\n".join(lines) if lines else "无法获取个人资料"
        console.print(Panel(text, title="👤 个人资料", border_style="cyan"))

    def _action(client):
        # Try the direct ME endpoint first
        try:
            data = client._get("/ajax/profile/me", action="个人资料")
            return data
        except Exception:
            pass
        # Fallback: feed groups still expose the current UID
        try:
            groups = client.get_feed_groups()
            uid = _extract_current_uid_from_feed_groups(groups)
            if uid:
                return client.get_profile(uid)
        except Exception:
            pass
        # Last fallback: parse the logged-in homepage config block
        try:
            resp = client.client.get("/")
            resp.raise_for_status()
            uid = _extract_current_uid_from_homepage_html(resp.text)
            if uid:
                return client.get_profile(uid)
        except Exception:
            pass
        return {"error": "无法获取个人资料，请确认已登录"}

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)
