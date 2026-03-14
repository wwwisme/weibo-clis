"""Personal & profile commands: profile, weibos, following."""

from __future__ import annotations

import re

import click
from rich.panel import Panel
from rich.table import Table

from ._common import console, handle_command, require_auth, structured_output_options


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def _format_count(n: int | str) -> str:
    """Format large numbers with 万."""
    try:
        n = int(n)
    except (ValueError, TypeError):
        return str(n)
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


@click.command()
@click.argument("uid")
@structured_output_options
def profile(uid, as_json, as_yaml):
    """查看用户资料 (weibo profile <uid>)"""
    cred = require_auth()

    def _render(data):
        user = data.get("user", data)
        lines = []
        name = user.get("screen_name", "未知")
        verified = " ✓" if user.get("verified") else ""
        lines.append(f"[bold cyan]{name}{verified}[/bold cyan]")
        if user.get("verified_reason"):
            lines.append(f"[dim]{user['verified_reason']}[/dim]")
        if user.get("description"):
            lines.append(f"\n{user['description']}")

        lines.append("")
        stats = []
        if user.get("followers_count") is not None:
            stats.append(f"[bold]粉丝[/bold] {_format_count(user['followers_count'])}")
        if user.get("friends_count") is not None:
            stats.append(f"[bold]关注[/bold] {_format_count(user['friends_count'])}")
        if user.get("statuses_count") is not None:
            stats.append(f"[bold]微博[/bold] {_format_count(user['statuses_count'])}")
        if stats:
            lines.append("  |  ".join(stats))

        if user.get("location"):
            lines.append(f"\n📍 {user['location']}")
        if user.get("gender"):
            gender = "♂ 男" if user["gender"] == "m" else "♀ 女" if user["gender"] == "f" else ""
            if gender:
                lines.append(f"  {gender}")

        console.print(Panel("\n".join(lines), title=f"@{name}", border_style="cyan", padding=(0, 1)))

        # Show tab list if available
        tabs = data.get("tabList", [])
        if tabs:
            tab_names = [t.get("tabName", t.get("name", "")) for t in tabs]
            console.print(f"[dim]可用 Tab: {' | '.join(tab_names)}[/dim]")

    def _action(client):
        return client.get_profile(uid)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.argument("uid")
@click.option("--page", "-p", default=1, help="页码")
@structured_output_options
def weibos(uid, page, as_json, as_yaml):
    """查看用户微博列表 (weibo weibos <uid>)"""
    cred = require_auth()

    def _render(data):
        statuses = data if isinstance(data, list) else data.get("list", data.get("statuses", []))
        if not statuses:
            console.print("[yellow]暂无微博[/yellow]")
            return

        for i, s in enumerate(statuses, 1):
            text = _strip_html(s.get("text_raw", s.get("text", "")))
            source = s.get("source", "")
            created = s.get("created_at", "")
            reposts = s.get("reposts_count", 0)
            comments_count = s.get("comments_count", 0)
            likes = s.get("attitudes_count", 0)
            mblogid = s.get("mblogid", "")

            content = f"[dim]{created}  via {source}[/dim]\n"
            content += f"{text[:300]}\n"
            if s.get("pic_ids"):
                content += f"[dim]📷 {len(s['pic_ids'])} 张图片[/dim]\n"
            content += f"[dim]💬 {comments_count}  🔁 {reposts}  ❤️ {likes}[/dim]"
            if mblogid:
                content += f"  [dim]ID: {mblogid}[/dim]"

            console.print(Panel(content, title=f"#{i}", border_style="blue", padding=(0, 1)))

    def _action(client):
        return client.get_user_weibos(uid, page=page)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.argument("uid")
@click.option("--page", "-p", default=1, help="页码")
@structured_output_options
def following(uid, page, as_json, as_yaml):
    """查看用户关注列表 (weibo following <uid>)"""
    cred = require_auth()

    def _render(data):
        users = data.get("users", []) if isinstance(data, dict) else data
        if not users:
            console.print("[yellow]暂无关注[/yellow]")
            return

        table = Table(title="关注列表", show_lines=False, padding=(0, 1))
        table.add_column("UID", style="dim", width=12)
        table.add_column("昵称", style="bold")
        table.add_column("粉丝", justify="right")
        table.add_column("简介", max_width=40)

        for u in users:
            uid_str = str(u.get("id", u.get("idstr", "")))
            name = u.get("screen_name", "")
            verified = " ✓" if u.get("verified") else ""
            followers = _format_count(u.get("followers_count", 0))
            desc = (u.get("description", "") or "")[:40]
            table.add_row(uid_str, f"{name}{verified}", followers, desc)

        console.print(table)

    def _action(client):
        return client.get_following(uid, page=page)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)
