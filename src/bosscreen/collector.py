"""采集层：用选择器配置从页面里取数据。

设计约束：
1. 选择器全在 JSON 里，代码里不出现任何 BOSS 类名。
2. 取不到就返回 None（未知），绝不用默认值填充。
3. 每次导航前过预算闸；命中风控立刻停。
4. 只读：不点按钮、不发消息、不改页面状态。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from . import transport


class RiskDetected(RuntimeError):
    """页面出现验证码/登录墙/限流，必须立刻停。"""


class BudgetExceeded(RuntimeError):
    """超过当天页面预算。"""


def _clean(text: str) -> str:
    return " ".join(text.split())


def list_js(spec: dict[str, Any]) -> str:
    """生成列表页抽取脚本。spec 会被 JSON 编码进表达式。"""
    return f"""(() => {{
  const SPEC = {json.dumps(spec, ensure_ascii=False)};
  const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
  const wrap = document.querySelector(SPEC.container || 'body') || document;
  const items = Array.from(wrap.querySelectorAll(SPEC.item || ':scope > *'));
  const out = items.map(it => {{
    const row = {{}};
    for (const [key, sel] of Object.entries(SPEC.fields || {{}})) {{
      if (!sel) {{ row[key] = null; continue; }}
      const el = it.querySelector(sel);
      row[key] = el ? (key === 'href' ? (el.href || el.getAttribute('href')) : clean(el.textContent)) : null;
    }}
    return row;
  }});
  return JSON.stringify({{count: items.length, rows: out}});
}})()"""


def detail_js(spec: dict[str, Any]) -> str:
    return f"""(() => {{
  const SPEC = {json.dumps(spec, ensure_ascii=False)};
  const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
  const root = document.querySelector(SPEC.container || 'body');
  if (!root) return JSON.stringify({{_error: 'container-not-found', container: SPEC.container}});
  const out = {{}};
  for (const [key, sel] of Object.entries(SPEC.fields || {{}})) {{
    if (!sel) {{ out[key] = null; continue; }}
    const el = root.querySelector(sel);
    out[key] = el ? clean(el.textContent) : null;
  }}
  for (const [key, sel] of Object.entries(SPEC.list_fields || {{}})) {{
    if (key.startsWith('_') || !sel) {{ out[key] = []; continue; }}
    out[key] = Array.from(root.querySelectorAll(sel)).map(e => clean(e.textContent)).filter(Boolean);
  }}
  out._href = location.href;
  return JSON.stringify(out);
}})()"""


def risk_js(markers: dict[str, Any]) -> str:
    return f"""(() => {{
  const M = {json.dumps(markers, ensure_ascii=False)};
  const hit = [];
  const html = document.documentElement.outerHTML.slice(0, 200000);
  for (const sel of (M.captcha || [])) {{
    try {{ if (document.querySelector(sel)) hit.push('captcha:' + sel); }} catch (e) {{}}
  }}
  const url = location.href, title = document.title || '';
  for (const s of (M.login_wall || [])) if (url.includes(s)) hit.push('login:' + s);
  for (const s of (M.blocked_paths || [])) if (url.includes(s)) hit.push('path:' + s);
  for (const s of (M.blocked_titles || [])) if (title.includes(s)) hit.push('title:' + s);
  for (const s of (M.rate_limited || [])) if (html.includes(s)) hit.push('rate:' + s);
  return JSON.stringify({{url: url, title: title, hits: hit}});
}})()"""


def _wait_ready(sess, timeout: float = 25.0) -> None:
    """等页面 readyState=complete。超时不抛错——有些页面永远不 complete。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if sess.eval("document.readyState") == "complete":
                return
        except Exception:  # noqa: BLE001 - 页面导航中断是正常的
            pass
        time.sleep(0.5)


@dataclass
class Usage:
    """当天读了多少个页面。存在本地，不进 git。"""

    path: Path
    pages: int = 0

    def __post_init__(self) -> None:
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if data.get("date") == date.today().isoformat():
            self.pages = int(data.get("pages", 0))

    def reserve(self, limit: int) -> None:
        if self.pages >= limit:
            raise BudgetExceeded(f"今天已读 {self.pages} 页，达到上限 {limit}")
        self.pages += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"date": date.today().isoformat(), "pages": self.pages}, ensure_ascii=False),
            encoding="utf-8",
        )


@dataclass
class Collector:
    port: int
    list_spec: dict[str, Any]
    detail_spec: dict[str, Any]
    risk_markers: dict[str, Any]
    usage: Usage
    daily_limit: int = 300
    delay: tuple[float, float] = (3.0, 7.0)
    log: list[str] = field(default_factory=list)

    # --- 单页操作 -----------------------------------------------------
    def _open(self, url: str):
        self.usage.reserve(self.daily_limit)
        tab = transport.open_tab(self.port, url)
        sess = transport.CDPSession(tab["webSocketDebuggerUrl"])
        _wait_ready(sess)
        self._check_risk(sess)
        return tab, sess

    def _check_risk(self, sess) -> None:
        """读一次风控信号。页面刚跳转时执行上下文可能已被销毁，重试一次。"""
        last: Exception | None = None
        for attempt in range(2):
            try:
                info = json.loads(sess.eval(risk_js(self.risk_markers)))
                break
            except Exception as exc:  # noqa: BLE001 - CDPError 或 JSON 错误都重试一次
                last = exc
                time.sleep(0.6)
        else:
            raise RiskDetected(f"页面读不出来（连续两次失败：{last}）") from last
        if info.get("hits"):
            raise RiskDetected(f"命中风控信号 {info['hits']} @ {info['url']}")

    def _close(self, tab, sess=None) -> None:
        if sess is not None:
            try:
                sess.close()
            except Exception:  # noqa: BLE001 - 关掉就行，不关心原因
                pass
        transport.close_tab(self.port, tab["id"])

    def _sleep(self) -> None:
        lo, hi = self.delay
        if hi <= 0:
            return
        time.sleep(lo + (hi - lo) * ((time.time() * 1000) % 1000) / 1000)

    # --- 对外 ---------------------------------------------------------
    def list_page(self, url: str | None = None) -> list[dict[str, Any]]:
        target = url or self.list_spec.get("url")
        if not target:
            raise ValueError("列表页 URL 未配置")
        tab, sess = self._open(target)
        try:
            raw = sess.eval(list_js(self.list_spec))
        finally:
            self._close(tab, sess)
        data = json.loads(raw)
        self.log.append(f"列表页取到 {data.get('count', 0)} 条")
        return data.get("rows", [])

    def detail_page(self, url: str) -> dict[str, Any]:
        self._sleep()
        tab, sess = self._open(url)
        try:
            raw = sess.eval(detail_js(self.detail_spec))
        finally:
            self._close(tab, sess)
        data = json.loads(raw)
        if data.get("_error") == "container-not-found":
            raise RiskDetected(
                f"页面结构对不上（找不到 {data.get('container')}）——"
                "选择器需要重新校准，不要硬取"
            )
        return data

    def collect(self, urls: list[str], limit: int = 10) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for i, url in enumerate(urls[:limit]):
            try:
                rows.append(self.detail_page(url))
            except RiskDetected as exc:
                self.log.append(f"第 {i + 1} 个中止：{exc}")
                break
        return rows
