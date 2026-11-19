"""方案差异：条件变了什么、名单因此变了什么。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bosscreen.diff import diff_requirements, diff_results, summarize  # noqa: E402
from bosscreen.models import Candidate  # noqa: E402
from bosscreen.requirement import requirement_from_dict  # noqa: E402
from bosscreen.scoring import rank  # noqa: E402
from bosscreen.web import Board  # noqa: E402

CANDS = [
    Candidate(uid="jia", name="甲", degree="硕士", work_years=6.0, expect_city=["深圳"], skills=["Python"]),
    Candidate(uid="yi", name="乙", degree="本科", work_years=3.0, expect_city=["广州"], skills=["Go"]),
    Candidate(uid="bing", name="丙", degree="大专", work_years=1.0, expect_city=["深圳"]),
]

STRICT = requirement_from_dict({
    "name": "严格版", "threshold": 70,
    "must": [{"field": "degree", "op": "gte", "value": "硕士"}],
    "nice": [{"field": "skills", "op": "contains_any", "value": ["Python"], "weight": 3}],
})
LOOSE = requirement_from_dict({
    "name": "放宽版", "threshold": 20,
    "must": [{"field": "work_years", "op": "gte", "value": 3}],
    "nice": [{"field": "expect_city", "op": "contains_any", "value": ["深圳"], "weight": 1},
             {"field": "skills", "op": "contains_any", "value": ["Go"], "weight": 2}],
})


class TestRequirementDiff(unittest.TestCase):
    def test_threshold_and_conditions(self):
        d = diff_requirements(STRICT, LOOSE)
        self.assertTrue(d["threshold"]["changed"])
        self.assertEqual((d["threshold"]["a"], d["threshold"]["b"]), (70.0, 20.0))
        self.assertEqual([c["field"] for c in d["must"]["removed"]], ["degree"])
        self.assertEqual([c["field"] for c in d["must"]["added"]], ["work_years"])
        self.assertEqual([c["field"] for c in d["nice"]["removed"]], ["skills"])
        self.assertEqual(len(d["nice"]["added"]), 2)

    def test_same_requirement_has_no_diff(self):
        d = diff_requirements(STRICT, STRICT)
        self.assertFalse(d["threshold"]["changed"])
        self.assertEqual(d["must"], {"added": [], "removed": []})
        self.assertEqual(d["nice"], {"added": [], "removed": []})
        self.assertFalse(d["renamed"])

    def test_condition_text_is_readable(self):
        d = diff_requirements(STRICT, LOOSE)
        self.assertEqual(d["must"]["added"][0]["text"], "至少 3 年经验")


class TestResultDiff(unittest.TestCase):
    def test_entered(self):
        d = diff_results(CANDS, STRICT, LOOSE)
        self.assertEqual([r["name"] for r in d["entered"]], ["乙"])
        self.assertEqual(d["entered"][0]["score_b"], 66.7)

    def test_left_when_reversed(self):
        d = diff_results(CANDS, LOOSE, STRICT)
        self.assertEqual([r["name"] for r in d["left"]], ["乙"])
        # 分数没动的人也换了名单，原因必须写清是哪条硬条件没过
        self.assertEqual(d["left"][0]["why"], "学历 硕士 及以上")

    def test_moved_by_score(self):
        d = diff_results(CANDS, STRICT, LOOSE)
        # 按 |delta| 倒序：甲 -66.7 在前，丙 +33.3 在后（丙两份都没过硬条件，只是分数变了）
        self.assertEqual([r["name"] for r in d["moved"]], ["甲", "丙"])
        self.assertEqual(d["moved"][0]["delta"], -66.7)

    def test_counts(self):
        d = diff_results(CANDS, STRICT, LOOSE)
        self.assertEqual(d["counts"], {"a": 1, "b": 2})

    def test_summarize_mentions_people(self):
        text = summarize(CANDS, STRICT, LOOSE)
        self.assertIn("严格版 → 放宽版", text)
        self.assertIn("阈值 70 → 20", text)
        self.assertIn("进来：乙", text)


class TestBoardDiff(unittest.TestCase):
    def _loaders(self):
        schemes = {"严格版": STRICT, "放宽版": LOOSE}

        def load(sid):
            req = schemes.get(sid)
            if req is None:
                return None
            return req, {"name": req.name, "threshold": req.threshold, "must": [], "nice": []}

        return load

    def test_diff_schemes_does_not_touch_current_requirement(self):
        board = Board(rank(CANDS, LOOSE), LOOSE, CANDS,
                      list_schemes=lambda: [{"id": "严格版", "name": "严格版"},
                                            {"id": "放宽版", "name": "放宽版"}],
                      load_scheme=self._loaders())
        payload = board.diff_schemes("严格版", "放宽版")
        self.assertEqual(payload["a"]["name"], "严格版")
        self.assertEqual(payload["b"]["name"], "放宽版")
        self.assertEqual(payload["results"]["counts"], {"a": 1, "b": 2})
        self.assertEqual(board.req.name, "放宽版")

    def test_missing_scheme_raises_keyerror(self):
        board = Board(rank(CANDS, LOOSE), LOOSE, CANDS,
                      list_schemes=lambda: [], load_scheme=self._loaders())
        with self.assertRaises(KeyError):
            board.diff_schemes("严格版", "没有这个")

    def test_without_loader_raises_keyerror(self):
        board = Board(rank(CANDS, LOOSE), LOOSE, CANDS)
        with self.assertRaises(KeyError):
            board.diff_schemes("a", "b")


if __name__ == "__main__":
    unittest.main()
