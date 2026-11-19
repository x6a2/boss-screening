"""导出 CSV：列、编码、留空语义。"""

from __future__ import annotations

import csv
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bosscreen.export import HEADER, filename_for, to_csv  # noqa: E402
from bosscreen.models import Candidate, Requirement  # noqa: E402
from bosscreen.scoring import rank  # noqa: E402


def _cands():
    return [
        Candidate(uid="a", name="张伟", degree="本科", work_years=6.0, expect_city=["深圳"],
                  expect_salary="25-35K", current_title="后端开发工程师", current_company="某电商",
                  skills=["Python", "Redis"]),
        Candidate(uid="b", name="刘洋", work_years=5.0, expect_city=["深圳"], skills=["Python"]),
    ]


def _req():
    return Requirement(name="深圳后端", threshold=60.0)


class TestCsv(unittest.TestCase):
    def test_header_and_row_count(self):
        cands = _cands()
        results = rank(cands, _req())
        text = to_csv(results, {c.uid: c for c in cands})
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], ",".join(HEADER))
        self.assertEqual(len(lines), 3)

    def test_unknown_fields_are_empty_not_zero(self):
        cands = _cands()
        results = rank(cands, _req())
        text = to_csv(results, {c.uid: c for c in cands})
        row = next(r for r in csv.DictReader(io.StringIO(text)) if r["姓名"] == "刘洋")
        self.assertEqual(row["学历"], "")
        self.assertEqual(row["期望薪资"], "")
        self.assertNotEqual(row["完整度"], "100%", "缺字段的人完整度要低于 100%")

    def test_comma_in_reason_does_not_break_columns(self):
        cands = [Candidate(uid="x", name="某人", skills=["Python", "Go"], expect_city=["深圳", "广州"])]
        results = rank(cands, _req())
        text = to_csv(results, {c.uid: c for c in cands})
        parsed = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["姓名"], "某人")

    def test_file_written_with_bom(self):
        import tempfile

        cands = _cands()
        results = rank(cands, _req())
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.csv"
            to_csv(results, {c.uid: c for c in cands}, path)
            raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "要带 BOM，Excel 才不乱码")

    def test_filename_carries_requirement_name(self):
        self.assertIn("深圳后端", filename_for(_req()))
        self.assertEqual(filename_for(Requirement(name="a/b:c")), "abc-筛选结果.csv")
        self.assertTrue(filename_for(Requirement(name="")).endswith(".csv"))


if __name__ == "__main__":
    unittest.main()
