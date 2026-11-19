"""选择器体检：生成探测脚本 + 在样例页上真的探一遍。"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bosscreen.collector import probe_detail_js, probe_list_js  # noqa: E402

LIST = {
    "container": ".bosschat-conversation-wrap",
    "item": ".bosschat-conversation-item",
    "fields": {"name": ".geek-name", "href": "a", "degree": ""},
}
DETAIL = {
    "container": ".resume-content",
    "fields": {"name": ".geek-name", "degree": ".degree"},
    "list_fields": {"skills": ".skill-tag", "_note": "忽略我"},
}


class TestProbeScripts(unittest.TestCase):
    def test_list_probe_carries_selectors_and_skips_empty(self):
        js = probe_list_js(LIST)
        self.assertIn(".bosschat-conversation-item", js)
        self.assertIn("skipped", js, "留空的字段要标成 skipped，而不是伪造命中")
        json.dumps(LIST)  # 规格本身可 JSON 化（脚本里就是这么嵌的）

    def test_detail_probe_covers_list_fields_and_ignores_underscore(self):
        js = probe_detail_js(DETAIL)
        self.assertIn(".skill-tag", js)
        self.assertIn("_note", js, "_ 开头的键交给脚本自己跳过")


@unittest.skipUnless(os.environ.get("BOSSSCREEN_CDP_PORT"), "需要 BOSSSCREEN_CDP_PORT")
class TestProbeLive(unittest.TestCase):
    def setUp(self):
        from bosscreen.collector import Collector, Usage

        self.root = ROOT
        port = int(os.environ["BOSSSCREEN_CDP_PORT"])
        sel = json.loads((ROOT / "tests/fixtures/selectors.fixture.json").read_text(encoding="utf-8"))
        self.tmp = ROOT / "tests" / "_usage_probe.json"
        self.col = Collector(
            port=port,
            list_spec=sel["conversation_list"],
            detail_spec=sel["resume_detail"],
            risk_markers=sel["risk_markers"],
            usage=Usage(self.tmp),
            delay=(0.0, 0.0),
        )

    def tearDown(self):
        self.tmp.unlink(missing_ok=True)

    def test_list_probe_reports_hits(self):
        info = self.col.probe_page((ROOT / "tests/fixtures/list.html").as_uri(), kind="list")
        self.assertTrue(info["container"])
        self.assertEqual(info["items"], 3)
        self.assertEqual(info["fields"]["name"]["hits"], 1)
        self.assertEqual(info["fields"]["name"]["sample"], "张伟")

    def test_detail_probe_counts_multi_values(self):
        info = self.col.probe_page((ROOT / "tests/fixtures/resume-zhangwei.html").as_uri(), kind="detail")
        self.assertEqual(info["fields"]["skills"]["hits"], 3, "技能标签应该数到 3 个")
        self.assertIn("Python", info["fields"]["skills"]["sample"])

    def test_wrong_container_is_reported_not_raised(self):
        bad = dict(self.col.detail_spec, container=".not-there")
        self.col.detail_spec = bad
        info = self.col.probe_page((ROOT / "tests/fixtures/resume-zhangwei.html").as_uri(), kind="detail")
        self.assertFalse(info["container"], "体检要报告问题，不能直接抛异常")


if __name__ == "__main__":
    unittest.main()
