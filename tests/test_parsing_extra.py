"""更细的简历字段：求职状态、教育经历、项目经历。

这些字段是"老板真筛人时会问"的东西：他做过什么项目、什么时候能到岗、
学校是哪儿的。解析层只负责原文搬运，不做结构化猜测——页面上是一行文字，
就存一行文字；拆成"学校/专业/起止"得等真机看过页面结构再定。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bosscreen.export import HEADER, rows, to_csv  # noqa: E402
from bosscreen.models import Candidate, Condition, Requirement  # noqa: E402
from bosscreen.parsing import _as_lines, dedupe, from_platform  # noqa: E402
from bosscreen.scoring import HIT, MISS, evaluate, rank  # noqa: E402


class TestParseExtraFields(unittest.TestCase):
    def test_snake_case_keys(self):
        c = from_platform("u1", {
            "name": "张三",
            "job_status": "离职-随时到岗",
            "educations": ["2015-2019 深圳大学 计算机 本科"],
            "projects": ["订单中台：P99 从 800ms 压到 120ms"],
        })
        self.assertEqual(c.job_status, "离职-随时到岗")
        self.assertEqual(c.educations, ["2015-2019 深圳大学 计算机 本科"])
        self.assertEqual(c.projects, ["订单中台：P99 从 800ms 压到 120ms"])

    def test_camel_case_keys(self):
        c = from_platform("u1", {"jobStatus": "在职-月内到岗", "projectList": ["A", "B"]})
        self.assertEqual(c.job_status, "在职-月内到岗")
        self.assertEqual(c.projects, ["A", "B"])

    def test_missing_stays_none_or_empty(self):
        c = from_platform("u1", {"name": "李四"})
        self.assertIsNone(c.job_status)
        self.assertEqual(c.educations, [])
        self.assertEqual(c.projects, [])

    def test_as_lines_keeps_spaces(self):
        """按空格切会把"2015-2019 深圳大学 本科"切成三段。"""
        self.assertEqual(_as_lines("2015-2019 深圳大学 本科"),
                         ["2015-2019 深圳大学 本科"])

    def test_as_lines_splits_newlines(self):
        self.assertEqual(_as_lines("第一条\n第二条\n\n第三条"), ["第一条", "第二条", "第三条"])

    def test_as_lines_from_dicts(self):
        self.assertEqual(_as_lines([{"school": "深圳大学", "major": "计算机"}]), ["深圳大学 计算机"])

    def test_dedupe_merges_extra_lists(self):
        a = Candidate(uid="u1", name="张三")
        b = Candidate(uid="u1", name="张三", job_status="离职-随时到岗", projects=["项目 A"])
        merged = dedupe([a, b])[0]
        self.assertEqual(merged.job_status, "离职-随时到岗")
        self.assertEqual(merged.projects, ["项目 A"])

    def test_dedupe_does_not_duplicate_lists(self):
        a = Candidate(uid="u1", projects=["项目 A"])
        b = Candidate(uid="u1", projects=["项目 B"])
        merged = dedupe([a, b])[0]
        self.assertEqual(merged.projects, ["项目 A"], "已有值不被后一条覆盖")


class TestScoreExtraFields(unittest.TestCase):
    def test_exists_hits_when_projects_present(self):
        c = Candidate(uid="u1", projects=["订单中台"])
        self.assertEqual(evaluate(Condition("projects", "exists"), c), HIT)

    def test_exists_misses_when_section_blank(self):
        """空列表 = 页面上没有这一节，算"没写"，不是"不知道"。见 docs/decisions.md D18。"""
        self.assertEqual(evaluate(Condition("projects", "exists"), Candidate(uid="u1")), MISS)

    def test_contains_any_searches_project_text(self):
        c = Candidate(uid="u1", projects=["订单中台：把 P99 压到 120ms"])
        self.assertEqual(evaluate(Condition("projects", "contains_any", ["订单"]), c), HIT)
        self.assertEqual(evaluate(Condition("projects", "contains_any", ["支付"]), c), MISS)

    def test_job_status_eq(self):
        c = Candidate(uid="u1", job_status="离职-随时到岗")
        self.assertEqual(evaluate(Condition("job_status", "contains_any", ["随时到岗"]), c), HIT)


class TestExportColumns(unittest.TestCase):
    def test_header_order_is_stable(self):
        self.assertEqual(HEADER, [
            "姓名", "分数", "完整度", "硬条件", "期望城市", "学历", "工作年限", "期望薪资",
            "当前职位", "当前公司", "求职状态", "教育经历", "项目经历", "技能", "理由", "uid",
        ])

    def test_new_columns_are_filled(self):
        c = Candidate(uid="u1", name="张三", job_status="离职-随时到岗",
                      educations=["2015-2019 深圳大学 本科"], projects=["订单中台", "支付对账"],
                      skills=["Python"])
        text = to_csv(rank([c], Requirement(name="x", threshold=1.0)), {"u1": c})
        header = text.splitlines()[0].split(",")
        row = text.splitlines()[1].split(",")
        rec = dict(zip(header, row))
        self.assertEqual(rec["求职状态"], "离职-随时到岗")
        self.assertEqual(rec["教育经历"], "2015-2019 深圳大学 本科")
        self.assertEqual(rec["项目经历"], "订单中台｜支付对账", "多条用全角竖线隔开，别用逗号破坏列")

    def test_rows_count_matches_results(self):
        c = Candidate(uid="u1", name="张三")
        results = rank([c], Requirement(name="x", threshold=1.0))
        self.assertEqual(len(rows(results, {"u1": c})), 1)


if __name__ == "__main__":
    unittest.main()
