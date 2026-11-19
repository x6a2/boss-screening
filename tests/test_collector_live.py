"""端到端：真 Chrome + 样例页面 → 结构化 → 打分。

默认跳过。要跑：

    chrome.exe --headless=new --remote-debugging-port=9334 --user-data-dir=<tmp>
    BOSSSCREEN_CDP_PORT=9334 python -m unittest tests.test_collector_live
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bosscreen.collector import Collector, Usage  # noqa: E402
from bosscreen.config import load_selectors  # noqa: E402
from bosscreen.parsing import dedupe, from_platform  # noqa: E402

PORT = os.environ.get("BOSSSCREEN_CDP_PORT")


@unittest.skipUnless(PORT, "设置 BOSSSCREEN_CDP_PORT 才跑（需要能连上的 Chrome 调试端口）")
class TestLiveFixture(unittest.TestCase):
    def _collector(self) -> Collector:
        sel = load_selectors(ROOT / "tests" / "fixtures" / "selectors.fixture.json")
        tmp = tempfile.mkdtemp()
        return Collector(
            port=int(PORT),
            list_spec=sel["conversation_list"],
            detail_spec=sel["resume_detail"],
            risk_markers=sel.get("risk_markers", {}),
            usage=Usage(Path(tmp) / "usage.json"),
            delay=(0.0, 0.0),
        )

    def test_list_and_details(self):
        col = self._collector()
        list_url = (ROOT / "tests" / "fixtures" / "list.html").as_uri()
        rows = col.list_page(list_url)
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0]["href"].endswith("resume-zhangwei.html"))

        import urllib.parse

        urls = [urllib.parse.urljoin(list_url, r["href"]) for r in rows]
        details = col.collect(urls, limit=3)
        self.assertEqual(len(details), 3)

        by_name = {d["name"]: d for d in details}
        self.assertEqual(by_name["张伟"]["degree"], "本科")
        self.assertEqual(by_name["张伟"]["work_years"], "6年")
        self.assertEqual(by_name["张伟"]["skills"], ["Python", "MySQL", "Redis"])

        from bosscreen.parsing import parse_years

        self.assertEqual(parse_years(by_name["张伟"]["work_years"]), 6.0)

        cands = dedupe([from_platform(d["_href"], d) for d in details])
        self.assertEqual(len(cands), 3)
        liu = next(c for c in cands if c.name == "刘洋")
        self.assertIsNone(liu.degree, "缺学历必须是 None，不能编")
        self.assertEqual(liu.expect_city, ["深圳"])

    def test_missing_container_is_loud(self):
        col = self._collector()
        col.detail_spec = {"container": ".definitely-not-here", "fields": {}}
        with self.assertRaises(Exception):
            col.detail_page((ROOT / "tests" / "fixtures" / "resume-zhangwei.html").as_uri())


if __name__ == "__main__":
    unittest.main()
