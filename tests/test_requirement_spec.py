"""需求编辑：校验规则 + 改完之后重新打分。

看板上的"编辑需求"最终走的就是这两条路，所以在这里挡住脏数据。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bosscreen.models import Candidate  # noqa: E402
from bosscreen.requirement import prepare_spec, requirement_from_dict  # noqa: E402
from bosscreen.scoring import rank  # noqa: E402
from bosscreen.web import Board  # noqa: E402


def _cands() -> list[Candidate]:
    return [
        Candidate(uid="a", name="甲", degree="硕士", work_years=5.0, skills=["Python"],
                  expect_city="深圳", current_title="后端工程师"),
        Candidate(uid="b", name="乙", degree="本科", work_years=3.0, skills=["Python", "Go"],
                  expect_city="广州", current_title="服务端工程师"),
        Candidate(uid="c", name="丙", degree=None, work_years=None, skills=[]),
    ]


class TestPrepareSpec(unittest.TestCase):
    def test_normalizes_strings_and_numbers(self):
        clean = prepare_spec({
            "name": "  后端  ",
            "threshold": "70",
            "must": [{"field": "work_years", "op": "gte", "value": "3"}],
            "nice": [{"field": "skills", "op": "contains_any", "value": "Python、Go", "weight": "2"}],
        })
        self.assertEqual(clean["name"], "后端")
        self.assertEqual(clean["threshold"], 70.0)
        self.assertEqual(clean["must"][0]["value"], 3.0)
        self.assertEqual(clean["nice"][0]["value"], ["Python", "Go"])
        self.assertEqual(clean["nice"][0]["weight"], 2.0)

    def test_rejects_empty_name(self):
        with self.assertRaises(ValueError) as ctx:
            prepare_spec({"name": " ", "must": [{"field": "degree", "op": "gte", "value": "本科"}]})
        self.assertIn("名称", str(ctx.exception))

    def test_rejects_unknown_field_and_op(self):
        with self.assertRaises(ValueError) as ctx:
            prepare_spec({
                "name": "x",
                "must": [
                    {"field": "salary_expectation", "op": "gte", "value": 3},
                    {"field": "degree", "op": "sounds_like", "value": "本科"},
                ],
            })
        msg = str(ctx.exception)
        self.assertIn("不认识的字段", msg)
        self.assertIn("不认识的操作", msg)

    def test_rejects_empty_list_value(self):
        with self.assertRaises(ValueError) as ctx:
            prepare_spec({"name": "x", "nice": [{"field": "skills", "op": "contains_any", "value": "  "}]})
        self.assertIn("至少要填一个值", str(ctx.exception))

    def test_requires_at_least_one_condition(self):
        with self.assertRaises(ValueError):
            prepare_spec({"name": "x", "must": [], "nice": []})


class TestBoardApply(unittest.TestCase):
    def _board(self, saved: list | None = None) -> Board:
        req = requirement_from_dict({
            "name": "初始",
            "threshold": 60,
            "must": [{"field": "degree", "op": "gte", "value": "本科"}],
            "nice": [{"field": "skills", "op": "contains_any", "value": ["Python"], "weight": 3}],
        })
        cands = _cands()
        board = Board(rank(cands, req), req, cands,
                      on_save=(lambda r, s: saved.append(s)) if saved is not None else None)
        return board

    def test_apply_rescores(self):
        board = self._board()
        before = {r.uid: r.total for r in board.results}
        payload = board.apply({
            "name": "只看硕士",
            "threshold": 80,
            "must": [{"field": "degree", "op": "gte", "value": "硕士"}],
            "nice": [{"field": "expect_city", "op": "contains_any", "value": "深圳", "weight": 2}],
        })
        self.assertEqual(board.req.name, "只看硕士")
        after = {r["uid"]: r["total"] for r in payload["rows"]}
        self.assertNotEqual(before, after, "改需求必须重算分数")
        flags = {r["uid"]: r["passed_must"] for r in payload["rows"]}
        self.assertFalse(flags["b"], "本科不该过硬条件『硕士及以上』")
        self.assertTrue(flags["a"])
        self.assertGreater(after["a"], after["b"], "深圳 + 硕士的甲应排到乙前面")

    def test_apply_persists_via_callback(self):
        saved: list = []
        board = self._board(saved)
        board.apply({"name": "n", "threshold": 60,
                     "must": [{"field": "skills", "op": "contains_any", "value": "Python"}]})
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["name"], "n")

    def test_apply_rejects_bad_spec_without_mutating(self):
        board = self._board()
        with self.assertRaises(ValueError):
            board.apply({"name": "", "must": []})
        self.assertEqual(board.req.name, "初始", "非法输入不能改动现有需求")

    def test_payload_carries_editable_spec(self):
        payload = self._board().payload()
        self.assertIn("spec", payload)
        self.assertEqual(payload["spec"]["must"][0]["field"], "degree")
        self.assertEqual(payload["choices"]["fields"][0][0], "work_years")
        self.assertTrue(payload["saved"]["ok"])

    def test_save_failure_is_reported_not_swallowed(self):
        def boom(_req, _spec):
            raise RuntimeError("磁盘满了")

        req = requirement_from_dict({"name": "初始", "must": [{"field": "degree", "op": "gte", "value": "本科"}]})
        cands = _cands()
        board = Board(rank(cands, req), req, cands, on_save=boom)
        payload = board.apply({"name": "改", "must": [{"field": "degree", "op": "gte", "value": "硕士"}]})
        self.assertFalse(payload["saved"]["ok"], "存不上必须让页面知道")
        self.assertIn("磁盘满了", payload["saved"]["error"])
        self.assertEqual(board.req.name, "改", "存不上也不该回滚已经算好的分")


if __name__ == "__main__":
    unittest.main()
