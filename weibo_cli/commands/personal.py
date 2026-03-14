"""Personal & profile commands: profile, weibos, following, followers, reposts, home."""

from __future__ import annotations

import click
from rich.panel import Panel

from ._common import console, format_count, handle_command, require_auth, structured_output_options
from .renderers import render_repost_list, render_user_table, render_weibo_list


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
            stats.append(f"[bold]粉丝[/bold] {format_count(user['followers_count'])}")
        if user.get("friends_count") is not None:
            stats.append(f"[bold]关注[/bold] {format_count(user['friends_count'])}")
        if user.get("statuses_count") is not None:
            stats.append(f"[bold]微博[/bold] {format_count(user['statuses_count'])}")
        if stats:
            lines.append("  |  ".join(stats))

        if user.get("location"):
            lines.append(f"\n📍 {user['location']}")
        if user.get("gender"):
            gender = "♂ 男" if user["gender"] == "m" else "♀ 女" if user["gender"] == "f" else ""
            if gender:
                lines.append(f"  {gender}")

        console.print(Panel("\n".join(lines), title=f"@{name}", border_style="cyan", padding=(0, 1)))

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
@click.option("--count", "-n", default=20, help="条数")
@structured_output_options
def weibos(uid, page, count, as_json, as_yaml):
    """查看用户微博列表 (weibo weibos <uid>)"""
    cred = require_auth()

    def _render(data):
        statuses = data if isinstance(data, list) else data.get("list", data.get("statuses", []))
        render_weibo_list(statuses, count=count, show_user=False)

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
        render_user_table(users, title="关注列表", empty_msg="[yellow]暂无关注[/yellow]")

    def _action(client):
        return client.get_following(uid, page=page)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.argument("uid")
@click.option("--page", "-p", default=1, help="页码")
@structured_output_options
def followers(uid, page, as_json, as_yaml):
    """查看用户粉丝列表 (weibo followers <uid>)"""
    cred = require_auth()

    def _render(data):
        users = data.get("users", []) if isinstance(data, dict) else data
        render_user_table(users, title="粉丝列表", empty_msg="[yellow]暂无粉丝[/yellow]")

    def _action(client):
        return client.get_followers(uid, page=page)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.argument("mblogid")
@click.option("--count", "-n", default=10, help="转发条数")
@click.option("--page", "-p", default=1, help="页码")
@structured_output_options
def reposts(mblogid, count, page, as_json, as_yaml):
    """查看微博转发 (weibo reposts <mblogid>)"""
    cred = require_auth()

    def _render(data):
        repost_list = data.get("data", []) if isinstance(data, dict) else data
        render_repost_list(repost_list, count=count)

    def _action(client):
        weibo = client.get_weibo_detail(mblogid)
        weibo_id = str(weibo.get("id", weibo.get("mid", "")))
        return client.get_reposts(weibo_id, page=page, count=count)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.option("--count", "-n", default=20, help="条数 (1-50)")
@structured_output_options
def home(count, as_json, as_yaml):
    """查看关注者 Feed (weibo home) 🏠"""
    cred = require_auth()

    def _render(data):
        statuses = data.get("statuses", [])
        render_weibo_list(statuses, count=count, border_style="green", empty_msg="[yellow]暂无关注者微博[/yellow]")

    def _action(client):
        return client.get_friends_timeline(count=min(count, 50))

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)
