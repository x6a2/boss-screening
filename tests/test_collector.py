"""采集层：JS 生成、预算闸、未校准拦截。

真正的"从浏览器取数据"在 tests/test_collector_live.py 里（需要 Chrome，默认跳过）。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bosscreen.collector import (  # noqa: E402
    BudgetExceeded,
    Usage,
    detail_js,
    list_js,
    risk_js,
)


class TestJs(unittest.TestCase):
    def test_list_js_embeds_spec(self):
        spec = {"container": ".wrap", "item": ".row", "fields": {"name": ".n"}}
        js = list_js(spec)
        self.assertIn('".wrap"', js)
        self.assertIn("querySelectorAll", js)
        # 不该出现直接拼接导致的语法问题：能作为 JSON 解析回来
        self.assertIn(json.dumps(spec, ensure_ascii=False), js)

    def test_list_js_handles_quotes_in_selector(self):
        js = list_js({"item": "[data-x='a\"b']", "fields": {}})
        self.assertIn("a\\\"b", js)

    def test_detail_js_reports_missing_container(self):
        js = detail_js({"container": ".nope", "fields": {}})
        self.assertIn("container-not-found", js)

    def test_detail_js_skips_underscore_keys(self):
        js = detail_js({"fields": {}, "list_fields": {"_note": "x", "skills": ".t"}})
        self.assertIn("startsWith('_')", js)

    def test_risk_js_includes_all_marker_groups(self):
        markers = {
            "captcha": [".cap"],
            "login_wall": ["/login"],
            "rate_limited": ["操作频繁"],
        }
        js = risk_js(markers)
        for needle in (".cap", "/login", "操作频繁"):
            self.assertIn(needle, js)


class TestUsage(unittest.TestCase):
    def test_counts_and_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage = Usage(Path(tmp) / "usage.json")
            usage.reserve(2)
            usage.reserve(2)
            with self.assertRaises(BudgetExceeded):
                usage.reserve(2)
            again = Usage(Path(tmp) / "usage.json")
            self.assertEqual(again.pages, 2, "重新加载后应当还记得今天读了几页")

    def test_ignores_stale_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.json"
            path.write_text(json.dumps({"date": "2000-01-01", "pages": 99}), encoding="utf-8")
            self.assertEqual(Usage(path).pages, 0, "昨天的计数不能算今天")


class TestUncalibratedGuard(unittest.TestCase):
    def test_example_config_is_rejected(self):
        from bosscreen.cli import main

        sel = ROOT / "config" / "selectors.boss.example.json"
        self.assertTrue(sel.exists())
        code = main(["collect", "--selectors", str(sel), "--port", "9"])
        self.assertEqual(code, 1, "未校准的选择器必须拒绝采集")


if __name__ == "__main__":
    unittest.main()
