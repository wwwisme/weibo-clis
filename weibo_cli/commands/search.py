"""Search, hot-search and feed commands."""

from __future__ import annotations

import re

import click
from rich.panel import Panel
from rich.table import Table

from ._common import console, handle_command, require_auth, structured_output_options


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text or "")


@click.command(name="hot")
@structured_output_options
def hot(as_json, as_yaml):
    """查看微博热搜榜 🔥"""
    from ..auth import get_credential

    cred = get_credential()

    def _render(data):
        table = Table(title="🔥 微博热搜", show_lines=False, padding=(0, 1))
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("热搜词", style="bold")
        table.add_column("标签", width=4)
        table.add_column("热度", justify="right", style="cyan")

        items = data.get("realtime") or data.get("band_list") or []
        for i, item in enumerate(items[:50], 1):
            word = item.get("word", item.get("note", ""))
            icon = item.get("icon_desc", item.get("label_name", ""))
            num = item.get("num", item.get("raw_hot", ""))

            # Color the icon
            icon_color = "red" if icon == "沸" else "yellow" if icon == "热" else "green" if icon == "新" else ""
            icon_text = f"[{icon_color}]{icon}[/{icon_color}]" if icon_color and icon else icon

            num_str = ""
            if num:
                n = int(num) if isinstance(num, (int, float)) else 0
                if n > 10000:
                    num_str = f"{n / 10000:.1f}万"
                else:
                    num_str = str(num)

            table.add_row(str(i), word, icon_text, num_str)

        console.print(table)

    def _action(client):
        return client.get_hot_search()

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.option("--count", "-n", default=10, help="条数 (1-20)")
@structured_output_options
def feed(count, as_json, as_yaml):
    """查看热门微博 Feed 📰"""
    from ..auth import get_credential

    cred = get_credential()

    def _render(data):
        statuses = data.get("statuses", [])
        if not statuses:
            console.print("[yellow]暂无热门微博[/yellow]")
            return

        for i, s in enumerate(statuses[:count], 1):
            user = s.get("user", {})
            name = user.get("screen_name", "未知")
            verified = " ✓" if user.get("verified") else ""
            text = _strip_html(s.get("text_raw", s.get("text", "")))
            created = s.get("created_at", "")
            reposts = s.get("reposts_count", 0)
            comments = s.get("comments_count", 0)
            likes = s.get("attitudes_count", 0)
            mblogid = s.get("mblogid", "")

            content = f"[bold cyan]{name}{verified}[/bold cyan]  [dim]{created}[/dim]\n"
            content += f"{text[:200]}\n"
            if s.get("pic_ids"):
                content += f"[dim]📷 {len(s['pic_ids'])} 张图片[/dim]\n"
            content += f"[dim]💬 {comments}  🔁 {reposts}  ❤️ {likes}  [/dim]"
            if mblogid:
                content += f"  [dim]ID: {mblogid}[/dim]"

            console.print(Panel(content, title=f"#{i}", border_style="blue", padding=(0, 1)))

    def _action(client):
        return client.get_hot_timeline(count=min(count, 20))

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.argument("mblogid")
@structured_output_options
def detail(mblogid, as_json, as_yaml):
    """查看微博详情 (weibo detail <mblogid>)"""
    cred = require_auth()

    def _render(data):
        user = data.get("user", {})
        name = user.get("screen_name", "未知")
        verified = " ✓" if user.get("verified") else ""
        text = _strip_html(data.get("text_raw", data.get("text", "")))
        source = data.get("source", "")
        created = data.get("created_at", "")
        reposts = data.get("reposts_count", 0)
        comments_count = data.get("comments_count", 0)
        likes = data.get("attitudes_count", 0)
        reads = data.get("reads_count", 0)

        content = f"[bold cyan]{name}{verified}[/bold cyan]"
        if user.get("verified_reason"):
            content += f"  [dim]{user['verified_reason']}[/dim]"
        content += f"\n[dim]{created}  via {source}[/dim]\n\n"
        content += f"{text}\n\n"

        if data.get("pic_ids"):
            content += f"[dim]📷 {len(data['pic_ids'])} 张图片[/dim]\n"

        content += f"👁 {reads}  💬 {comments_count}  🔁 {reposts}  ❤️ {likes}"

        console.print(Panel(content, title=f"微博 {data.get('mblogid', '')}", border_style="cyan", padding=(0, 1)))

    def _action(client):
        return client.get_weibo_detail(mblogid)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.argument("mblogid")
@click.option("--count", "-n", default=20, help="评论条数")
@structured_output_options
def comments(mblogid, count, as_json, as_yaml):
    """查看微博评论 (weibo comments <mblogid>)"""
    cred = require_auth()

    # First get the weibo detail to find the numeric ID
    def _render(data):
        comment_list = data if isinstance(data, list) else []
        if not comment_list:
            console.print("[yellow]暂无评论[/yellow]")
            return

        for c in comment_list[:count]:
            user = c.get("user", {})
            name = user.get("screen_name", "未知")
            text = _strip_html(c.get("text", ""))
            created = c.get("created_at", "")
            likes = c.get("like_counts", 0)

            console.print(f"  [bold]{name}[/bold]  [dim]{created}[/dim]")
            console.print(f"    {text}")
            if likes:
                console.print(f"    [dim]❤️ {likes}[/dim]")
            console.print()

    def _action(client):
        # Get weibo detail to find numeric ID
        weibo = client.get_weibo_detail(mblogid)
        weibo_id = str(weibo.get("id", weibo.get("mid", "")))
        return client.get_comments(weibo_id, count=count)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@structured_output_options
def trending(as_json, as_yaml):
    """查看实时搜索趋势 📈"""
    from ..auth import get_credential

    cred = get_credential()

    def _render(data):
        items = data.get("realtime", [])
        table = Table(title="📈 实时搜索趋势", show_lines=False, padding=(0, 1))
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("关键词", style="bold")
        table.add_column("描述", style="dim")

        for i, item in enumerate(items[:16], 1):
            word = item.get("word", "")
            desc = str(item.get("description", ""))
            table.add_row(str(i), word, desc[:40])

        console.print(table)

    def _action(client):
        return client.get_search_band()

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)
