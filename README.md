# weibo-cli

A CLI for Weibo (微博) — browse hot topics, search users, read timelines from the terminal.

## Installation

```bash
# Recommended
uv tool install weibo-cli

# Alternative
pipx install weibo-cli
```

## Quick Start

```bash
# Login via QR code
weibo login

# Check login status
weibo status

# View hot search (微博热搜 🔥)
weibo hot

# View hot feed
weibo feed

# View trending searches
weibo trending
```

## Commands

### Auth

| Command | Description |
|---------|-------------|
| `weibo login` | QR code login (scan with Weibo app) |
| `weibo logout` | Clear saved credentials |
| `weibo status` | Check authentication status |
| `weibo me` | View your profile |

### Browse

| Command | Description |
|---------|-------------|
| `weibo hot` | View hot search list (50+ items) 🔥 |
| `weibo feed [--count N]` | View hot timeline feed 📰 |
| `weibo trending` | View search trends 📈 |
| `weibo detail <mblogid>` | View weibo detail |
| `weibo comments <mblogid>` | View weibo comments |

### Profile

| Command | Description |
|---------|-------------|
| `weibo profile <uid>` | View user profile |
| `weibo weibos <uid> [--page N]` | View user's weibo list |
| `weibo following <uid>` | View user's following list |

## Output Formats

All data commands support `--json` and `--yaml` flags:

```bash
weibo hot --json
weibo profile 1699432410 --json | jq '.user.screen_name'
```

## Authentication

weibo-cli supports three auth methods (tried in order):

1. **Saved credentials** — `~/.config/weibo-cli/credential.json`  
2. **Browser cookies** — Auto-extracted from Chrome/Firefox/Edge via `browser-cookie3`  
3. **QR code login** — Scan with Weibo app (`weibo login`)

## Development

```bash
git clone git@github.com:jackwener/weibo-cli.git
cd weibo-cli
uv sync --all-extras
uv run pytest                           # unit tests
uv run pytest -m smoke                  # smoke tests (requires cookies)
uv run ruff check .                     # linting
```

## License

Apache-2.0
