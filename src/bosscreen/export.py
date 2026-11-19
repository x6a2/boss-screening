"""导出名单：CSV，给不用看板也得交表的人。"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable

from .models import Requirement, ScoreResult

HEADER = [
    "姓名",
    "分数",
    "完整度",
    "硬条件",
    "期望城市",
    "学历",
    "工作年限",
    "期望薪资",
    "当前职位",
    "当前公司",
    "求职状态",
    "教育经历",
    "项目经历",
    "技能",
    "理由",
    "uid",
]


def _must_label(r: ScoreResult) -> str:
    if not r.passed_must:
        return "未过硬条件"
    if r.pending:
        return "待确认"
    return "通过"


def rows(results: Iterable[ScoreResult], cands: dict) -> list[list[str]]:
    out: list[list[str]] = []
    for r in results:
        c = cands.get(r.uid)
        skills = "、".join(c.skills or []) if c and c.skills else ""
        educations = "｜".join(c.educations or []) if c and c.educations else ""
        projects = "｜".join(c.projects or []) if c and c.projects else ""
        out.append(
            [
                r.name or "",
                f"{r.total:.1f}",
                f"{r.coverage * 100:.0f}%",
                _must_label(r),
                "、".join(c.expect_city or []) if c else "",
                (c.degree or "") if c else "",
                f"{c.work_years:g} 年" if c and c.work_years is not None else "",
                (c.expect_salary or "") if c else "",
                (c.current_title or "") if c else "",
                (c.current_company or "") if c else "",
                (c.job_status or "") if c else "",
                educations,
                projects,
                skills,
                r.reason or "",
                r.uid,
            ]
        )
    return out


def to_csv(results: Iterable[ScoreResult], cands: dict, path: str | Path | None = None) -> str:
    """写 CSV（utf-8-sig，Excel 直接打开不乱码）。给了 path 就落盘，同时返回文本。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows(results, cands))
    text = buf.getvalue()
    if path is not None:
        Path(path).write_text(text, encoding="utf-8-sig")
    return text


def filename_for(req: Requirement) -> str:
    """文件名带上需求名，导出好几版时不至于互相覆盖。"""
    safe = "".join(ch for ch in (req.name or "名单") if ch not in '\\/:*?"<>|').strip() or "名单"
    return f"{safe}-筛选结果.csv"
