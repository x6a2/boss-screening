"""核心逻辑单测。不需要网络、浏览器、数据库。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bosscreen.models import Candidate, Condition, Requirement, Weighted  # noqa: E402
from bosscreen.parsing import dedupe, from_platform, parse_years  # noqa: E402
from bosscreen.scoring import degree_level, evaluate, parse_salary, score  # noqa: E402


class TestParsing(unittest.TestCase):
    def test_missing_fields_stay_none(self):
        c = from_platform("u1", {"name": "某人"})
        self.assertIsNone(c.degree)
        self.assertIsNone(c.work_years)
        self.assertEqual(c.skills, [])

    def test_parse_years(self):
        self.assertEqual(parse_years("3年"), 3.0)
        self.assertEqual(parse_years("3-5年"), 3.0)
        self.assertEqual(parse_years("应届"), 0.0)
        self.assertIsNone(parse_years(None))

    def test_dedupe_merges_missing(self):
        a = from_platform("u1", {"name": "张伟", "skills": ["Python"]})
        b = from_platform("u1", {"name": "张伟", "skills": ["Go"], "degree": "本科"})
        out = dedupe([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].degree, "本科")


class TestConditions(unittest.TestCase):
    def test_degree_level(self):
        self.assertGreater(degree_level("硕士"), degree_level("本科"))
        self.assertGreater(degree_level("本科"), degree_level("大专"))
        self.assertIsNone(degree_level("未知学历"))

    def test_salary_parse(self):
        self.assertEqual(parse_salary("20-30K"), (20.0, 30.0))
        self.assertEqual(parse_salary("1.5-2万"), (15.0, 20.0))
        self.assertIsNone(parse_salary("面议"))

    def test_missing_field_is_unknown_not_miss(self):
        c = Candidate(uid="u1", name="无学历者")
        cond = Condition(field="degree", op="gte", value="本科", label="本科及以上")
        self.assertEqual(evaluate(cond, c), "unknown")

    def test_contains_any(self):
        c = Candidate(uid="u1", skills=["Python", "Redis"])
        cond = Condition(field="skills", op="contains_any", value=["Go", "Python"])
        self.assertEqual(evaluate(cond, c), "hit")
        cond2 = Condition(field="skills", op="contains_any", value=["Rust"])
        self.assertEqual(evaluate(cond2, c), "miss")


class TestScoring(unittest.TestCase):
    def _req(self) -> Requirement:
        return Requirement(
            name="t",
            must=[Condition(field="degree", op="gte", value="本科", label="本科及以上")],
            nice=[Weighted(1.0, Condition(field="skills", op="contains_any", value=["Python"], label="会 Python"))],
            threshold=60,
        )

    def test_unknown_must_does_not_reject(self):
        c = Candidate(uid="u1", name="张三", skills=["Python"])
        r = score(c, self._req())
        self.assertTrue(r.passed_must)
        self.assertEqual(len(r.pending), 1)

    def test_must_fail_rejects(self):
        c = Candidate(uid="u1", name="李四", degree="大专", skills=["Python"])
        r = score(c, self._req())
        self.assertFalse(r.passed_must)
        self.assertEqual(r.total, 100.0)  # 分数照算，靠 passed_must 排序沉底

    def test_all_unknown_scores_zero(self):
        c = Candidate(uid="u1", name="王五")
        req = Requirement(
            name="t",
            nice=[Weighted(1.0, Condition(field="skills", op="contains_any", value=["Python"]))],
        )
        r = score(c, req)
        self.assertEqual(r.total, 0.0)
        self.assertIn("无足够信息", r.reason)


if __name__ == "__main__":
    unittest.main()
