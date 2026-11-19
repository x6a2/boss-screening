"""Chrome 调试端口的 HTTP 侧 + 一次性的页面求值。

这里只做"连上一个已经开着的 Chrome"，不启动浏览器、不改配置、不登录。
工具的态度是：用户自己登录好，我们只读。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .cdp import CDPSession

DEFAULT_PORTS = (9222, 9229, 9333)


class ChromeUnavailable(RuntimeError):
    pass


def _get(port: int, path: str, method: str = "GET", timeout: float = 3.0) -> bytes:
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def version(port: int) -> dict[str, Any] | None:
    """连得上就返回 Browser 版本信息，否则 None。"""
    try:
        return json.loads(_get(port, "/json/version"))
    except (OSError, ValueError):
        return None


def find_port(ports: tuple[int, ...] = DEFAULT_PORTS) -> int | None:
    for p in ports:
        if version(p):
            return p
    return None


def list_targets(port: int) -> list[dict[str, Any]]:
    try:
        return json.loads(_get(port, "/json/list"))
    except (OSError, ValueError) as exc:
        raise ChromeUnavailable(f"读不到 {port} 的标签页列表：{exc}") from exc


def pages(port: int) -> list[dict[str, Any]]:
    return [t for t in list_targets(port) if t.get("type") == "page"]


def find_page(port: int, url_part: str) -> dict[str, Any] | None:
    for t in pages(port):
        if url_part in (t.get("url") or ""):
            return t
    return None


def open_tab(port: int, url: str, timeout: float = 10.0) -> dict[str, Any]:
    """新开一个后台标签。调用方负责之后关掉它。"""
    q = urllib.parse.quote(url, safe="")
    try:
        raw = _get(port, f"/json/new?{q}", method="PUT", timeout=timeout)
    except OSError:
        raw = _get(port, f"/json/new?{q}", method="GET", timeout=timeout)
    return json.loads(raw)


def close_tab(port: int, target_id: str) -> None:
    try:
        _get(port, f"/json/close/{target_id}")
    except OSError:
        pass


def evaluate(ws_url: str, expression: str) -> Any:
    sess = CDPSession(ws_url)
    try:
        return sess.eval(expression)
    finally:
        sess.close()


@dataclass
class ProbeResult:
    port: int | None
    browser: str = ""
    page_count: int = 0
    zhipin_pages: list[tuple[str, str]] = None  # (title, url)
    recruiter_page: str | None = None
    blocked_reason: str = ""

    def __post_init__(self) -> None:
        if self.zhipin_pages is None:
            self.zhipin_pages = []


def probe(ports: tuple[int, ...] = DEFAULT_PORTS) -> ProbeResult:
    """只读探测：Chrome 在不在、开了哪些 BOSS 页面、是不是招聘端。

    全程不对页面做任何操作，也不点"切换为招聘者"。
    """
    port = find_port(ports)
    if port is None:
        return ProbeResult(port=None, blocked_reason="没有发现开着远程调试端口的 Chrome")

    v = version(port) or {}
    res = ProbeResult(port=port, browser=str(v.get("Browser", "")))
    try:
        ts = pages(port)
    except ChromeUnavailable as exc:
        res.blocked_reason = str(exc)
        return res

    res.page_count = len(ts)
    for t in ts:
        url = t.get("url") or ""
        if "zhipin.com" not in url:
            continue
        res.zhipin_pages.append((t.get("title") or "", url))
        if "/web/boss/" in url:
            res.recruiter_page = url
    if not res.blocked_reason and res.recruiter_page is None:
        res.blocked_reason = (
            "Chrome 里没有招聘端页面。当前登录的可能仍是求职者账号——"
            "工具不会替你切换身份。"
        )
    return res
