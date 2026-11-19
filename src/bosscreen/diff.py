"""两份需求的差异：条件变了什么、名单因此变了什么。

老板真正关心的不是"分数",而是"我放宽之后，谁进来了、谁出去了"。
所以这里把差异分成两半：

- 需求差异：加了哪条、删了哪条、哪条改了（人能看懂的句子）
- 名单差异：新进来的（之前没过、现在过了）、掉出去的、分数变化最大的

两份需求用同一批候选人重算，不缓存分数——分数是需求的函数，
拿旧分数比较等于在比较两个不同的东西。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import HIT, Candidate, Condition, Requirement, ScoreResult
from .scoring import evaluate, rank


def _cond_key(c: Condition) -> tuple[str, str, str]:
    return (c.field, c.op, str(c.value))


def _cond_row(c: Condition) -> dict[str, Any]:
    return {"field": c.field, "op": c.op, "value": c.value, "text": c.text}


def diff_requirements(a: Requirement, b: Requirement) -> dict[str, Any]:
    """a → b 的条件差异。added 是 b 多的，removed 是 b 删掉的，changed 是同一条改了值。"""
    must_add, must_del = _pair_diff(a.must, b.must)
    nice_add, nice_del = _pair_diff([w.condition for w in a.nice], [w.condition for w in b.nice])
    return {
        "threshold": {"a": a.threshold, "b": b.threshold, "changed": a.threshold != b.threshold},
        "must": {"added": must_add, "removed": must_del},
        "nice": {"added": nice_add, "removed": nice_del},
        "renamed": a.name != b.name,
        "names": {"a": a.name, "b": b.name},
    }


def _pair_diff(old: list[Condition], new: list[Condition]) -> tuple[list[dict], list[dict]]:
    old_map = {_cond_key(c): c for c in old}
    new_map = {_cond_key(c): c for c in new}
    added = [_cond_row(c) for k, c in new_map.items() if k not in old_map]
    removed = [_cond_row(c) for k, c in old_map.items() if k not in new_map]
    return added, removed


def _must_failures(cand: Candidate | None, req: Requirement) -> list[str]:
    """这条需求下没过哪些硬条件——名单变动时真正要告诉人的原因。"""
    if cand is None:
        return []
    return [c.text for c in req.must if evaluate(c, cand) != HIT]


def _by_uid(results: list[ScoreResult]) -> dict[str, ScoreResult]:
    return {r.uid: r for r in results}


@dataclass
class ResultDiff:
    """两份需求下的名单差异。"""

    entered: list[dict[str, Any]] = field(default_factory=list)
    left: list[dict[str, Any]] = field(default_factory=list)
    moved: list[dict[str, Any]] = field(default_factory=list)
    unchanged: int = 0


def diff_results(cands: list[Candidate], a: Requirement, b: Requirement, limit: int = 20) -> dict[str, Any]:
    """在 a、b 两份需求下分别重算，返回名单层面的差异。"""
    ra, rb = _by_uid(rank(cands, a)), _by_uid(rank(cands, b))
    by_uid = {c.uid: c for c in cands}

    entered: list[dict[str, Any]] = []
    left: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    unchanged = 0

    for uid in ra:
        x, y = ra[uid], rb.get(uid)
        if y is None:
            continue
        passed_a = x.passed_must and x.total >= a.threshold
        passed_b = y.passed_must and y.total >= b.threshold
        row = {
            "uid": uid,
            "name": y.name,
            "score_a": round(x.total, 1),
            "score_b": round(y.total, 1),
            "delta": round(y.total - x.total, 1),
            "passed_a": passed_a,
            "passed_b": passed_b,
            # 进了/出了的人，原因通常是硬条件而不是分数；分数没动也要说清为什么换名单。
            "why": "",
        }
        if passed_b and not passed_a:
            row["why"] = "；".join(_must_failures(by_uid.get(uid), a))
            entered.append(row)
        elif passed_a and not passed_b:
            row["why"] = "；".join(_must_failures(by_uid.get(uid), b))
            left.append(row)
        elif row["delta"]:
            moved.append(row)
        else:
            unchanged += 1

    moved.sort(key=lambda r: abs(r["delta"]), reverse=True)
    entered.sort(key=lambda r: r["score_b"], reverse=True)
    left.sort(key=lambda r: r["score_a"], reverse=True)
    return {
        "entered": entered,
        "left": left,
        "moved": moved[:limit],
        "unchanged": unchanged,
        "counts": {"a": sum(1 for r in ra.values() if r.passed_must and r.total >= a.threshold),
                   "b": sum(1 for r in rb.values() if r.passed_must and r.total >= b.threshold)},
    }


def summarize(cands: list[Candidate], a: Requirement, b: Requirement) -> str:
    """命令行用的一句话总结。"""
    d = diff_results(cands, a, b)
    req = diff_requirements(a, b)
    lines = [f"{a.name} → {b.name}"]
    if req["threshold"]["changed"]:
        lines.append(f"阈值 {req['threshold']['a']:g} → {req['threshold']['b']:g}")
    for part in ("must", "nice"):
        for row in req[part]["removed"]:
            lines.append(f"删掉条件：{row['text']}")
        for row in req[part]["added"]:
            lines.append(f"新增条件：{row['text']}")
    lines.append(f"达到阈值：{d['counts']['a']} 人 → {d['counts']['b']} 人")
    for row in d["entered"]:
        lines.append(f"  进来：{row['name']}（{row['score_a']} → {row['score_b']}）")
    for row in d["left"]:
        lines.append(f"  出去：{row['name']}（{row['score_a']} → {row['score_b']}）")
    for row in d["moved"][:5]:
        lines.append(f"  变动：{row['name']} {row['score_a']} → {row['score_b']}")
    if not (d["entered"] or d["left"] or d["moved"]):
        lines.append("  名单没有变化")
    return "\n".join(lines)
