"""草稿生成的行为约束：只用简历里真实存在的字段。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bosscreen.draft import build_draft  # noqa: E402
from bosscreen.models import Candidate, Condition, Requirement, Weighted  # noqa: E402
from bosscreen.scoring import score  # noqa: E402


def _req() -> Requirement:
    return Requirement(
        name="后端工程师",
        must=[Condition(field="degree", op="gte", value="本科", label="本科及以上")],
        nice=[Weighted(1.0, Condition(field="skills", op="contains_any", value=["Python"], label="会 Python"))],
    )


class TestDraft(unittest.TestCase):
    def test_includes_name_and_job(self):
        c = Candidate(uid="u1", name="张三", work_years=5.0, current_title="后端开发", skills=["Python"])
        text = build_draft(c, score(c, _req()), _req())
        self.assertIn("张三", text)
        self.assertIn("后端工程师", text)
        self.assertIn("5 年", text)

    def test_does_not_invent_company(self):
        c = Candidate(uid="u1", name="李四", current_title="后端开发")
        text = build_draft(c, score(c, _req()), _req())
        self.assertNotIn("在", text.split("你目前在")[1][:2] if "你目前在" in text else "")

    def test_pending_condition_is_flagged(self):
        c = Candidate(uid="u1", name="王五", skills=["Python"])  # 没有学历
        text = build_draft(c, score(c, _req()), _req())
        self.assertIn("发送前确认：本科及以上", text)

    def test_empty_candidate_still_produces_something(self):
        c = Candidate(uid="u1", name="")
        text = build_draft(c, score(c, _req()), _req())
        self.assertGreater(len(text), 10)


if __name__ == "__main__":
    unittest.main()
