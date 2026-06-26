#!/usr/bin/env python3
"""A small routed search aggregator.

This MVP reuses existing local tools instead of inventing new data interfaces:
- GitHub: `gh search repos` JSON output, verified with `gh search repos --help`.
- Web search: Agent Reach's Exa channel through `mcporter call`.
- URL reading: Agent Reach's Jina Reader pattern, `https://r.jina.ai/{URL}`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit


Runner = Callable[[list[str], int], str]
SKILL_ROOT = Path(__file__).resolve().parents[1]


def resolve_mcporter_config() -> Path | None:
    env_path = os.environ.get("SUPER_SEARCH_MCPORTER_CONFIG")
    candidates = [
        Path(env_path).expanduser() if env_path else None,
        SKILL_ROOT / "config" / "mcporter.json",
        Path.cwd() / "config" / "mcporter.json",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


class ProviderError(RuntimeError):
    """Raised when an external provider command fails."""


@dataclass(frozen=True)
class SearchResult:
    source: str
    title: str
    url: str
    snippet: str = ""
    published: str | None = None
    score: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "published": self.published,
            "score": self.score,
            "meta": self.meta,
        }


@dataclass(frozen=True)
class RoutePlan:
    query: str
    mode: str
    providers: list[str]
    urls: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "providers": self.providers,
            "urls": self.urls,
            "notes": self.notes,
        }


URL_RE = re.compile(r"https?://[^\s，。；;）)\]}<>\"']+")
TRAILING_URL_PUNCTUATION = ".,;:!?，。；：！？、"


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(TRAILING_URL_PUNCTUATION)
        if url not in urls:
            urls.append(url)
    return urls


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def compact_text(value: str, max_chars: int = 700) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    unique: list[SearchResult] = []
    for result in results:
        key = normalize_url(result.url) if result.url else result.title.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


class SearchRouter:
    github_keywords = (
        "github",
        "repo",
        "repository",
        "仓库",
        "代码",
        "开源",
        "项目",
        "issue",
        "pull request",
    )
    chinese_media_keywords = (
        "公众号",
        "小红书",
        "抖音",
        "快手",
        "视频号",
        "账号诊断",
        "热榜",
        "redfox",
        "红狐",
    )
    global_social_keywords = (
        "tiktok",
        "instagram",
        "reddit",
        "twitter",
        "x.com",
        "youtube",
        "bilibili",
        "b站",
        "tikhub",
    )
    browser_keywords = (
        "登录",
        "后台",
        "点击",
        "按钮",
        "截图",
        "下载",
        "验证码",
        "表单",
        "浏览器",
    )

    def plan(self, query: str, mode: str = "auto", use_redfox: bool = False) -> RoutePlan:
        query = query.strip()
        lowered = query.lower()
        urls = extract_urls(query)
        providers: list[str] = []
        notes: list[str] = []

        if mode not in {"auto", "url", "github", "web"}:
            raise ValueError(f"unknown mode: {mode}")

        if urls and mode in {"auto", "url"}:
            providers.append("jina_reader")
            notes.append("发现 URL：先用 Jina Reader 读取页面正文。")
            return RoutePlan(query=query, mode=mode, providers=providers, urls=urls, notes=notes)

        is_github = mode == "github" or any(word in lowered for word in self.github_keywords)
        if is_github:
            providers.extend(["github", "exa"])
            notes.append("GitHub 意图：先查仓库，再用 Exa 补全网页语境。")
        else:
            providers.append("exa")
            notes.append("通用搜索：默认走 Exa 免费语义搜索。")

        if any(word in lowered for word in self.chinese_media_keywords):
            if use_redfox:
                providers.append("redfox")
                notes.append("中文新媒体：已显式启用 RedFox 付费源（--redfox）。")
            else:
                notes.append("中文新媒体深度数据建议接 RedFox；加 --redfox 且设置 REDFOX_API_KEY 后启用。")

        if any(word in lowered for word in self.global_social_keywords):
            notes.append("全球社媒深字段建议接 TikHub；MVP 暂不自动调用付费源。")

        if any(word in lowered for word in self.browser_keywords):
            notes.append("真实网页交互建议走浏览器兜底；MVP 暂不自动点击或登录。")

        return RoutePlan(query=query, mode=mode, providers=providers, urls=urls, notes=notes)


def run_command(argv: list[str], timeout: int) -> str:
    completed = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise ProviderError(f"{argv[0]} failed: {detail}")
    return completed.stdout


def parse_exa_text(text: str) -> list[SearchResult]:
    blocks = re.split(r"\n\s*---\s*\n", text.strip())
    results: list[SearchResult] = []
    for block in blocks:
        title = _field(block, "Title")
        url = _field(block, "URL")
        if not title or not url:
            continue
        published = _field(block, "Published")
        snippet = _section_after(block, "Highlights:")
        results.append(
            SearchResult(
                source="exa",
                title=title,
                url=url,
                published=published,
                snippet=compact_text(snippet),
            )
        )
    return results


def parse_jina_text(text: str, fallback_url: str) -> SearchResult:
    title = _field(text, "Title") or fallback_url
    url = _field(text, "URL Source") or fallback_url
    published = _field(text, "Published Time")
    content = _section_after(text, "Markdown Content:") or text
    return SearchResult(
        source="jina_reader",
        title=title,
        url=url,
        published=published,
        snippet=compact_text(content, 900),
    )


def _field(text: str, name: str) -> str | None:
    match = re.search(rf"^{re.escape(name)}:\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _section_after(text: str, marker: str) -> str:
    if marker not in text:
        return ""
    section = text.split(marker, 1)[1]
    lines: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if line in {"", "..."}:
            continue
        if re.match(r"^(Title|URL|Published|Author):\s", line):
            break
        lines.append(line)
    return "\n".join(lines).strip()


class GitHubProvider:
    json_fields = "fullName,description,stargazersCount,updatedAt,url,language"

    def __init__(self, runner: Runner = run_command, timeout: int = 30):
        self.runner = runner
        self.timeout = timeout

    # `gh search repos` ANDs every term across repo metadata, so multi-word
    # natural-language phrases (e.g. "chinese tts comparison") usually match
    # nothing and the provider silently returns []. Strip filler words first,
    # then progressively drop trailing tokens until we get hits.
    STOPWORDS = frozenset({
        "a", "an", "the", "of", "for", "to", "in", "on", "and", "or", "with",
        "best", "top", "good", "comparison", "compare", "vs", "versus", "how",
        "what", "which", "review", "reviews", "list", "awesome", "tool", "tools",
        "software", "app", "apps", "library", "libraries", "alternative",
        "alternatives", "use", "using", "guide", "tutorial", "example", "examples",
    })

    def _keywords(self, query: str) -> str:
        tokens = [t for t in query.split() if t]
        kept = [t for t in tokens if t.lower().strip(".,!?;:") not in self.STOPWORDS]
        return " ".join(kept)

    def _run_gh(self, query: str, limit: int) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        argv = [
            "gh", "search", "repos", query,
            "--sort", "stars", "--limit", str(limit),
            "--json", self.json_fields,
        ]
        return json.loads(self.runner(argv, self.timeout) or "[]")

    def _candidates(self, query: str) -> list[str]:
        reduced = self._keywords(query)
        candidates: list[str] = []
        for cand in (reduced, query):
            if cand and cand not in candidates:
                candidates.append(cand)
        tokens = reduced.split()
        while len(tokens) > 1:
            tokens = tokens[:-1]
            cand = " ".join(tokens)
            if cand not in candidates:
                candidates.append(cand)
        return candidates

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        rows: list[dict[str, Any]] = []
        for candidate in self._candidates(query):
            rows = self._run_gh(candidate, limit)
            if rows:
                break
        results: list[SearchResult] = []
        for row in rows:
            full_name = row.get("fullName") or row.get("name") or "unknown"
            stars = row.get("stargazersCount")
            language = row.get("language")
            description = row.get("description") or ""
            parts = []
            if stars is not None:
                parts.append(f"{stars} stars")
            if language:
                parts.append(str(language))
            if description:
                parts.append(description)
            results.append(
                SearchResult(
                    source="github",
                    title=full_name,
                    url=row.get("url") or "",
                    snippet=compact_text(" · ".join(parts)),
                    published=row.get("updatedAt"),
                    score=float(stars or 0),
                    meta={"language": language, "stars": stars},
                )
            )
        return results


class ExaProvider:
    def __init__(
        self,
        runner: Runner = run_command,
        timeout: int = 45,
        mcporter_config: Path | None = None,
    ):
        self.runner = runner
        self.timeout = timeout
        self.mcporter_config = mcporter_config if mcporter_config is not None else resolve_mcporter_config()

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        escaped = query.replace("\\", "\\\\").replace('"', '\\"')
        expression = f'exa.web_search_exa(query: "{escaped}", numResults: {limit})'
        argv = ["mcporter"]
        if self.mcporter_config:
            argv.extend(["--config", str(self.mcporter_config)])
        argv.extend(["call", expression])
        payload = self.runner(argv, self.timeout)
        return parse_exa_text(payload)


class JinaReaderProvider:
    def __init__(self, runner: Runner = run_command, timeout: int = 30):
        self.runner = runner
        self.timeout = timeout

    def read_urls(self, urls: list[str]) -> list[SearchResult]:
        results: list[SearchResult] = []
        for url in urls:
            reader_url = f"https://r.jina.ai/{url}"
            payload = self.runner(
                ["curl", "-L", "--max-time", str(self.timeout), "-s", reader_url],
                self.timeout + 5,
            )
            results.append(parse_jina_text(payload, url))
        return results


class RedFoxProvider:
    """Opt-in adapter for redfox.hk Chinese-media data (公众号 / 小红书 / B站).

    RedFox is a PAID source, so this provider never runs silently: it activates
    only when ``REDFOX_API_KEY`` is set AND the caller explicitly opts in
    (``--redfox`` on the CLI), honoring the skill's rule that paid providers
    require confirmation. Endpoints reverse-engineered from
    ``redfox.hk/story/web/api/doc/platform/<code>/interfaces``.
    """

    BASE = "https://redfox.hk/story/api"
    # platform code -> (search endpoint, human label)
    ENDPOINTS = {
        "gzh": ("gzhData/searchArticle", "公众号"),
        "xhs": ("xhsUser/searchArticle", "小红书"),
        "bili": ("bili/data/workSearch", "B站"),
    }
    PLATFORM_HINTS = (
        ("xhs", ("小红书", "xhs", "xiaohongshu", "红书")),
        ("bili", ("b站", "bili", "哔哩", "bilibili")),
        ("gzh", ("公众号", "gzh", "weixin", "微信")),
    )

    def __init__(self, api_key: str | None = None, timeout: int = 30):
        self.api_key = api_key if api_key is not None else os.environ.get("REDFOX_API_KEY", "")
        self.timeout = timeout

    @classmethod
    def detect_platform(cls, query: str) -> str:
        lowered = query.lower()
        for platform, hints in cls.PLATFORM_HINTS:
            if any(h in lowered for h in hints):
                return platform
        return "gzh"

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        import urllib.request

        request = urllib.request.Request(
            f"{self.BASE}/{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "REDFOX_API_KEY": self.api_key},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def search(self, query: str, platform: str | None = None, limit: int = 5) -> list[SearchResult]:
        if not self.api_key:
            raise ProviderError(
                "REDFOX_API_KEY 未设置；RedFox 为付费源，需显式提供 key 后再用 --redfox 启用。"
            )
        platform = platform or self.detect_platform(query)
        path, label = self.ENDPOINTS.get(platform, self.ENDPOINTS["gzh"])
        if platform == "xhs":
            payload = {"keyword": query, "offset": 0, "sortType": "default"}
        elif platform == "bili":
            payload = {"keyword": query}
        else:
            payload = {"keyword": query, "pageNum": 1, "pageSize": limit}
        try:
            data = (self._post(path, payload) or {}).get("data") or {}
        except (OSError, ValueError) as exc:  # network / JSON errors
            raise ProviderError(f"RedFox 调用失败：{exc}") from exc
        rows = data.get("list") or []
        results: list[SearchResult] = []
        for row in rows[:limit]:
            metrics = []
            for key, lbl in (("readCount", "读"), ("likeCount", "赞"), ("commentCount", "评")):
                if row.get(key) is not None:
                    metrics.append(f"{lbl}{row[key]}")
            results.append(
                SearchResult(
                    source=f"redfox:{platform}",
                    title=row.get("title") or row.get("workTitle") or "",
                    url=row.get("workUrl") or row.get("url") or "",
                    snippet=compact_text(" · ".join(metrics)),
                    published=row.get("publishTime"),
                    meta={"platform": platform, "label": label},
                )
            )
        return results


class SuperSearch:
    def __init__(
        self,
        router: SearchRouter | None = None,
        github: GitHubProvider | None = None,
        exa: ExaProvider | None = None,
        jina: JinaReaderProvider | None = None,
        redfox: RedFoxProvider | None = None,
        use_redfox: bool = False,
    ):
        self.router = router or SearchRouter()
        self.github = github or GitHubProvider()
        self.exa = exa or ExaProvider()
        self.jina = jina or JinaReaderProvider()
        self.redfox = redfox or RedFoxProvider()
        self.use_redfox = use_redfox

    def search(self, query: str, mode: str = "auto", limit: int = 5) -> dict[str, Any]:
        plan = self.router.plan(query, mode=mode, use_redfox=self.use_redfox)
        notes = list(plan.notes)
        results: list[SearchResult] = []

        for provider in plan.providers:
            try:
                if provider == "jina_reader":
                    results.extend(self.jina.read_urls(plan.urls))
                elif provider == "github":
                    gh_results = self.github.search(query, limit=limit)
                    if not gh_results:
                        notes.append("GitHub 未命中仓库（已尝试关键词降级与逐词回退）。")
                    results.extend(gh_results)
                elif provider == "exa":
                    results.extend(self.exa.search(query, limit=limit))
                elif provider == "redfox":
                    results.extend(self.redfox.search(query, limit=limit))
                else:
                    notes.append(f"未识别 provider：{provider}")
            except (ProviderError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                notes.append(f"{provider} 调用失败：{exc}")

        return {
            "plan": plan.to_dict(),
            "notes": notes,
            "results": [item.to_dict() for item in dedupe_results(results)],
        }


def format_markdown(payload: dict[str, Any]) -> str:
    plan = payload["plan"]
    lines = [
        "# Super Search",
        "",
        f"Query: `{plan['query']}`",
        f"Providers: `{', '.join(plan['providers']) or 'none'}`",
        "",
        "## Notes",
    ]
    for note in payload["notes"]:
        lines.append(f"- {note}")

    lines.extend(["", "## Results"])
    results = payload["results"]
    if not results:
        lines.append("- 没有拿到结果。")
        return "\n".join(lines)

    for index, result in enumerate(results, start=1):
        title = result["title"] or result["url"]
        url = result["url"]
        source = result["source"]
        snippet = result["snippet"]
        lines.append(f"{index}. [{title}]({url})")
        lines.append(f"   - source: `{source}`")
        if result.get("published"):
            lines.append(f"   - time: `{result['published']}`")
        if snippet:
            lines.append(f"   - {snippet}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Routed local super search MVP")
    parser.add_argument("query", nargs="+", help="Search query or URL")
    parser.add_argument("--mode", choices=["auto", "url", "github", "web"], default="auto")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--dry-run", action="store_true", help="Print the route plan without calling providers")
    parser.add_argument(
        "--redfox",
        action="store_true",
        help="Opt in to the RedFox paid source for Chinese-media queries (requires REDFOX_API_KEY)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    query = " ".join(args.query)
    router = SearchRouter()

    if args.dry_run:
        plan = router.plan(query, args.mode, use_redfox=args.redfox)
        payload: dict[str, Any] = {"plan": plan.to_dict(), "notes": list(plan.notes), "results": []}
    else:
        payload = SuperSearch(router=router, use_redfox=args.redfox).search(
            query, mode=args.mode, limit=args.limit
        )

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
