"""需求 × 候选人 → 分数与理由。

纯函数：不碰网络、不碰数据库。规则先过硬条件，再算加权偏好。
核心原则：字段缺失是 UNKNOWN，不是 MISS。未知不扣分，但必须显示出来。
"""

from __future__ import annotations

import re
from typing import Any

from .models import (
    HIT,
    MISS,
    UNKNOWN,
    Candidate,
    Condition,
    Requirement,
    ScoreResult,
    Weighted,
)

# 学历阶梯。比较用等级，展示用原字符串。
_DEGREE_LEVELS: list[tuple[str, int]] = [
    ("博士", 5),
    ("硕士", 4),
    ("研究生", 4),
    ("本科", 3),
    ("学士", 3),
    ("大专", 2),
    ("专科", 2),
    ("高职", 2),
    ("中专", 1),
    ("高中", 1),
    ("职高", 1),
    ("技校", 1),
    ("初中", 0),
]

_SALARY_RE = re.compile(r"(\d+(?:\.\d+)?)")


def degree_level(text: str | None) -> int | None:
    if not text:
        return None
    for key, level in _DEGREE_LEVELS:
        if key in text:
            return level
    return None


def parse_salary(text: str | None) -> tuple[float, float] | None:
    """'20-30K' → (20, 30)，单位统一为 K/月。解析不出返回 None。"""
    if not text:
        return None
    text = text.replace(" ", "")
    factor = 10.0 if "万" in text else 1.0
    nums = [float(n) for n in _SALARY_RE.findall(text)]
    if not nums:
        return None
    if len(nums) == 1:
        return (nums[0] * factor, nums[0] * factor)
    return (nums[0] * factor, nums[1] * factor)


def _candidate_values(cand: Candidate, field: str) -> list[str] | None:
    """把任意字段统一成"字符串列表"，用于包含类判断。字段不存在返回 None。"""
    if not hasattr(cand, field):
        return None
    value = cand.get(field)
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _numeric(cand: Candidate, field: str) -> float | None:
    if field == "degree":
        level = degree_level(cand.degree)
        return float(level) if level is not None else None
    value = cand.get(field) if hasattr(cand, field) else None
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _SALARY_RE.search(str(value))
    return float(m.group(1)) if m else None


def evaluate(cond: Condition, cand: Candidate) -> str:
    """返回 hit / miss / unknown。"""
    op = cond.op
    target = cond.value

    if op == "exists":
        vals = _candidate_values(cand, cond.field)
        return HIT if vals else (MISS if vals == [] else UNKNOWN)

    if op in ("eq", "ne", "in", "not_in"):
        vals = _candidate_values(cand, cond.field)
        if not vals:
            return UNKNOWN
        if op == "eq":
            ok = any(v == str(target) for v in vals)
        elif op == "ne":
            ok = all(v != str(target) for v in vals)
        elif op == "in":
            ok = any(v in {str(t) for t in (target or [])} for v in vals)
        else:
            ok = all(v not in {str(t) for t in (target or [])} for v in vals)
        return HIT if ok else MISS

    if op in ("contains_any", "contains_all", "any_in"):
        vals = _candidate_values(cand, cond.field)
        if not vals:
            return UNKNOWN
        targets = [str(t) for t in (target or [])]
        joined = " ".join(vals)
        if op == "contains_any":
            ok = any(t in joined for t in targets) if targets else False
        else:
            ok = all(t in joined for t in targets) if targets else False
        return HIT if ok else MISS

    if op in ("gte", "lte"):
        actual = _numeric(cand, cond.field)
        if actual is None:
            return UNKNOWN
        if cond.field == "degree":
            need = float(degree_level(str(target)) or 0)
        else:
            need = float(_SALARY_RE.search(str(target)).group(1)) if _SALARY_RE.search(str(target)) else 0.0
        ok = actual >= need if op == "gte" else actual <= need
        return HIT if ok else MISS

    raise ValueError(f"未知操作符: {op}")


def score(cand: Candidate, req: Requirement) -> ScoreResult:
    result = ScoreResult(uid=cand.uid, name=cand.name, total=0.0, passed_must=True)

    for cond in req.must:
        state = evaluate(cond, cand)
        if state == MISS:
            result.passed_must = False
            result.misses.append(cond.text)
        elif state == UNKNOWN:
            result.pending.append(cond.text)

    hit_w = 0.0
    judged_w = 0.0
    total_w = 0.0
    for w in req.nice:
        total_w += w.weight
        state = evaluate(w.condition, cand)
        if state == HIT:
            hit_w += w.weight
            judged_w += w.weight
            result.hits.append(w.condition.text)
        elif state == MISS:
            judged_w += w.weight
            result.misses.append(w.condition.text)
        else:
            result.unknowns.append(w.condition.text)

    # 未知既不加分也不扣分，但分母包含它们：
    # 信息不全的人不会被"白送"高分，也不会被当成不满足丢掉。
    result.total = round(100.0 * hit_w / total_w, 1) if total_w else 0.0
    result.coverage = round(judged_w / total_w, 2) if total_w else 0.0
    result.reason = _reason(req, result, judged_w)
    return result


def _reason(req: Requirement, r: ScoreResult, judged_w: float) -> str:
    parts: list[str] = []
    if not r.passed_must:
        parts.append("未过硬条件")
    if r.pending:
        parts.append("待确认 " + "、".join(r.pending[:3]))
    if r.hits:
        parts.append("命中 " + "、".join(r.hits[:3]))
    if r.misses:
        parts.append("缺 " + "、".join(r.misses[:2]))
    if r.unknowns:
        parts.append("信息不足 " + "、".join(r.unknowns[:2]))
    if not judged_w:
        parts.append("无足够信息打分")
    return "；".join(parts) or "无明显倾向"


def rank(cands: list[Candidate], req: Requirement) -> list[ScoreResult]:
    """按分数排序；未过硬条件的沉底，但保留（不静默丢弃）。"""
    results = [score(c, req) for c in cands]
    results.sort(key=lambda r: (r.passed_must, r.total), reverse=True)
    return results
