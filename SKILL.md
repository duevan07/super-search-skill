---
name: super-search
description: MUST USE as the top-level routed search skill when the user asks to 搜索/search/搜一下/查一下/调研/research/look up/find, asks for GitHub alternatives, asks to read a URL/link/page/article, or asks where/how to search across web, GitHub, Chinese media, social media, paid APIs, or browser automation. Prefer this skill before directly using raw web search, raw Agent Reach commands, GitHub search, or browser automation; it calls the installed or bundled `super-search` router and only escalates to paid sources or browser actions after explicit confirmation.
---

# Super Search

## Overview

Use the installed `super-search` command as the first-pass router for search and research tasks. It routes:

- URLs to Jina Reader.
- GitHub/open-source queries to GitHub CLI plus Exa.
- General web queries to Exa.
- Chinese media queries toward RedFox as a recommended next step.
- Global social queries toward TikHub as a recommended next step.
- Login/click/download/screenshot tasks toward browser automation as a confirmed next step.

Prefer the installed `super-search` command when available. If it is not available, resolve this skill's folder and run the bundled script at `scripts/super_search.py`.

## Workflow

1. Start with a dry run when intent or cost is ambiguous:

```bash
super-search "USER QUERY" --dry-run --format json
```

If `super-search` is not on `PATH`, run the bundled script from this skill folder:

```bash
python3 scripts/super_search.py "USER QUERY" --dry-run --format json
```

2. If the route is free and read-only, run it directly:

```bash
super-search "USER QUERY" --limit 5
```

Fallback:

```bash
python3 scripts/super_search.py "USER QUERY" --limit 5
```

3. Use JSON when downstream synthesis, tables, or reports need structured evidence:

```bash
super-search "USER QUERY" --limit 5 --format json
```

4. Summarize results with sources. Preserve each result's source, title, URL, snippet, and time when present.

## Routing Rules

- For a URL/link/page/article: use `super-search "URL"` first.
- For GitHub/open-source alternatives: use `super-search "QUERY" --mode github`.
- For general web research: use default auto mode.
- For Chinese media data such as 公众号、抖音、小红书、快手、视频号、账号诊断、热榜: run a dry route first. If deeper structured data is needed, tell the user RedFox is the right next adapter and ask before using paid APIs.
- For TikTok, Instagram, X/Twitter, Reddit, YouTube, Bilibili, or global social depth: run a dry route first. If deeper structured data is needed, tell the user TikHub is the right next adapter and ask before using paid APIs.
- For login, clicking, screenshots, downloads, forms, or dashboards: do not drive a browser automatically from this skill alone. Ask for confirmation, then use the appropriate browser automation skill/tool.

## Boundaries

- Do not silently call paid providers.
- Do not silently use login state, click pages, submit forms, or download private data.
- Do not invent connectors or pretend RedFox, TikHub, or AgentKey are already wired into the command.
- If `super-search` returns a provider failure in `notes`, report it honestly and choose the next smallest verified fallback.
- If the raw Agent Reach skill also triggers, treat this skill as the top-level router and use raw Agent Reach commands only when `super-search` lacks the needed channel or fails.

## Verification

At minimum, from the skill folder run:

```bash
python3 scripts/super_search.py "https://example.com" --dry-run --format json
python3 scripts/super_search.py "github 上类似 Agent Reach 的项目" --dry-run --format json
```
