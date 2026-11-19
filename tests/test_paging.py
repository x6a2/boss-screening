"""列表滚动翻页：生成脚本、去重合并，以及在样例页上的真实滚动。"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bosscreen.collector import count_js, merge_rows, scroll_js  # noqa: E402

SPEC = {
    "container": ".bosschat-conversation-wrap",
    "item": ".bosschat-conversation-item",
    "fields": {"name": ".geek-name", "href": "a"},
    "paging": {"mode": "scroll", "scroll_container": ".bosschat-conversation-wrap"},
}


class TestScrollScripts(unittest.TestCase):
    def test_count_js_embeds_selector(self):
        js = count_js(SPEC)
        self.assertIn(".bosschat-conversation-item", js)
        self.assertIn("querySelectorAll", js)

    def test_scroll_js_scrolls_box_and_window(self):
        js = scroll_js(SPEC)
        self.assertIn("scrollTop = target.scrollHeight", js)
        self.assertIn("window.scrollTo", js)
        self.assertIn("new Event('scroll')", js)

    def test_scroll_js_survives_empty_spec(self):
        # 没配 scroll_container 时退到 document 滚动，不应该生成 querySelector(null)
        js = scroll_js({"item": ".x"})
        self.assertIn("document.scrollingElement", js)


class TestMergeRows(unittest.TestCase):
    def test_dedupes_by_href_keeping_first(self):
        a = [{"name": "甲", "href": "a.html"}, {"name": "乙", "href": "b.html"}]
        b = [{"name": "乙", "href": "b.html", "job": "x"}, {"name": "丙", "href": "c.html"}]
        merged = merge_rows(a, b)
        self.assertEqual([r["name"] for r in merged], ["甲", "乙", "丙"])
        self.assertNotIn("job", merged[1], "重复项保留先出现的那条")

    def test_falls_back_to_name_and_job(self):
        merged = merge_rows(
            [{"name": "甲", "job": "后端", "href": None}],
            [{"name": "甲", "job": "后端", "href": None}, {"name": "甲", "job": "前端", "href": None}],
        )
        self.assertEqual(len(merged), 2, "没有 href 时用 姓名+岗位 区分")

    def test_rows_without_any_key_do_not_collapse(self):
        merged = merge_rows([{"href": None}], [{"href": None}])
        self.assertEqual(len(merged), 1, "两个空行会被当成同一条，这是可接受的退化")


@unittest.skipUnless(os.environ.get("BOSSSCREEN_CDP_PORT"), "需要 BOSSSCREEN_CDP_PORT 指向已开调试端口的 Chrome")
class TestScrollLive(unittest.TestCase):
    """真浏览器里滚一遍样例页：3 条起步，滚两批到 9 条，然后到底停。"""

    def setUp(self):
        from bosscreen.collector import Collector, Usage

        port = int(os.environ["BOSSSCREEN_CDP_PORT"])
        self.selectors = json.loads((ROOT / "tests/fixtures/selectors.fixture.json").read_text(encoding="utf-8"))
        self.tmp = ROOT / "tests" / "_usage_scroll.json"
        self.collector = Collector(
            port=port,
            list_spec=self.selectors["conversation_list"],
            detail_spec=self.selectors["resume_detail"],
            risk_markers=self.selectors["risk_markers"],
            usage=Usage(self.tmp),
            delay=(0.0, 0.0),
        )
        self.url = (ROOT / "tests/fixtures/list-scroll.html").as_uri()

    def tearDown(self):
        self.tmp.unlink(missing_ok=True)

    def test_scrolls_until_end(self):
        rows = self.collector.list_page(self.url)
        names = [r["name"] for r in rows]
        self.assertEqual(len(rows), 9, f"应该滚出 9 条，实际 {names}")
        self.assertEqual(len(set(names)), 9, "滚动会重复抽到同一批卡片，必须去重")
        logs = " / ".join(self.collector.log)
        self.assertIn("到底", logs, f"到底了要记下来：{logs}")

    def test_does_not_scroll_forever_on_short_list(self):
        short = (ROOT / "tests/fixtures/list.html").as_uri()
        rows = self.collector.list_page(short)
        self.assertEqual(len(rows), 3)
        self.assertLessEqual(len(self.collector.log), 6, f"短列表不该反复滚：{self.collector.log}")

    def test_detail_right_after_open_finds_container(self):
        """回归：新标签页一开始是 about:blank，等错页面会导致"容器找不到"。"""
        data = self.collector.detail_page((ROOT / "tests/fixtures/resume-sunhao.html").as_uri())
        self.assertEqual(data.get("name"), "孙浩")
        self.assertEqual(data.get("degree"), "本科")


if __name__ == "__main__":
    unittest.main()
