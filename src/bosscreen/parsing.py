"""原始页面数据 → Candidate。

纯函数：不碰网络、不碰浏览器、不碰数据库。
平台字段名变了只需要改这里的 KEY 映射，不影响下游。
"""

from __future__ import annotations

import re
from typing import Any

from .models import Candidate

# 平台原始 dict 的键名映射。改版时只改这张表。
# 采集层输出的键名是 snake_case（与选择器配置的 fields 键一致），
# 这里同时接受驼峰写法，方便手工导入的历史数据。
FIELD_MAP: dict[str, str] = {
    "name": "name",
    "age": "age",
    "gender": "gender",
    "degree": "degree",
    "school": "school",
    "workYears": "work_years",
    "workYearsText": "work_years",
    "work_years": "work_years",
    "currentTitle": "current_title",
    "current_title": "current_title",
    "currentCompany": "current_company",
    "current_company": "current_company",
    "expectTitle": "expect_title",
    "expect_title": "expect_title",
    "expectCity": "expect_city",
    "expect_city": "expect_city",
    "expectSalary": "expect_salary",
    "expect_salary": "expect_salary",
    "skills": "skills",
    "jobStatus": "job_status",
    "job_status": "job_status",
    "educations": "educations",
    "education": "educations",
    "projects": "projects",
    "projectList": "projects",
    "experiences": "experiences",
    "jobId": "applied_job_id",
    "applied_job_id": "applied_job_id",
    "appliedAt": "applied_at",
    "applied_at": "applied_at",
}

_YEAR_RE = re.compile(r"(\d+(?:\.\d+)?)")


def parse_years(value: Any) -> float | None:
    """把 '3年'、'3-5年'、'应届' 之类变成数字。取区间下界，宁保守。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if "应届" in text or "在校" in text:
        return 0.0
    m = _YEAR_RE.search(text)
    return float(m.group(1)) if m else None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        parts = re.split(r"[,，/、\s]+", value)
        return [p.strip() for p in parts if p.strip()]
    return [str(value)]


def _as_lines(value: Any) -> list[str]:
    """多行文本/列表 → 若干条原文。

    和 _as_list 的区别：这里不按空格切。"2015-2019 深圳大学 计算机 本科"
    是一个整体，按空格切开就没法读了。
    """
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for v in value:
            if isinstance(v, dict):
                text = " ".join(str(x).strip() for x in v.values() if str(x).strip())
            else:
                text = str(v).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    m = _YEAR_RE.search(str(value))
    return int(float(m.group(1))) if m else None


def from_platform(uid: str, raw: dict[str, Any]) -> Candidate:
    """平台原始数据 → Candidate。缺字段一律 None，不猜默认值。"""
    data: dict[str, Any] = {}
    for src_key, dst in FIELD_MAP.items():
        if src_key in raw:
            value = raw[src_key]
            if dst in data and data[dst] is not None:
                continue  # 先到先得，避免同义键互相覆盖
            data[dst] = value

    return Candidate(
        uid=str(uid),
        name=str(data.get("name") or "").strip(),
        age=_as_int(data.get("age")),
        gender=(str(data["gender"]).strip() if data.get("gender") else None),
        degree=(str(data["degree"]).strip() if data.get("degree") else None),
        school=(str(data["school"]).strip() if data.get("school") else None),
        work_years=parse_years(data.get("work_years")),
        current_title=(str(data["current_title"]).strip() if data.get("current_title") else None),
        current_company=(str(data["current_company"]).strip() if data.get("current_company") else None),
        expect_title=_as_list(data.get("expect_title")),
        expect_city=_as_list(data.get("expect_city")),
        expect_salary=(str(data["expect_salary"]).strip() if data.get("expect_salary") else None),
        skills=_as_list(data.get("skills")),
        experiences=data.get("experiences") or [],
        job_status=(str(data["job_status"]).strip() if data.get("job_status") else None),
        educations=_as_lines(data.get("educations")),
        projects=_as_lines(data.get("projects")),
        applied_job_id=(str(data["applied_job_id"]) if data.get("applied_job_id") else None),
        applied_at=(str(data["applied_at"]) if data.get("applied_at") else None),
        raw=raw,
    )


def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    """同一个人多次投递 → 合并成一条。

    合并策略：主记录按出现顺序，后面的记录只补"我缺它有"的字段；
    applied_job_id 记录最近一次投递的职位。
    """
    merged: dict[str, Candidate] = {}
    order: list[str] = []
    for c in candidates:
        if c.uid not in merged:
            merged[c.uid] = c
            order.append(c.uid)
            continue
        keep = merged[c.uid]
        keep.merge_missing_from(c)
        if c.applied_job_id:
            keep.applied_job_id = c.applied_job_id
    return [merged[u] for u in order]
