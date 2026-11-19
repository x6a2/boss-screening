"""需求定义的读写：JSON ↔ Requirement。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Condition, Requirement, Weighted


def condition_from_dict(d: dict[str, Any]) -> Condition:
    return Condition(
        field=d["field"],
        op=d["op"],
        value=d.get("value"),
        label=d.get("label", ""),
    )


def requirement_from_dict(d: dict[str, Any]) -> Requirement:
    return Requirement(
        name=d.get("name", "未命名需求"),
        must=[condition_from_dict(x) for x in d.get("must", [])],
        nice=[Weighted(weight=float(x.get("weight", 1)), condition=condition_from_dict(x)) for x in d.get("nice", [])],
        threshold=float(d.get("threshold", 60)),
    )


def load_requirement(path: str | Path) -> Requirement:
    return requirement_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def requirement_to_dict(req: Requirement) -> dict[str, Any]:
    return {
        "name": req.name,
        "threshold": req.threshold,
        "must": [
            {"field": c.field, "op": c.op, "value": c.value, "label": c.text} for c in req.must
        ],
        "nice": [
            {"weight": w.weight, **{"field": w.condition.field, "op": w.condition.op,
                                   "value": w.condition.value, "label": w.condition.text}}
            for w in req.nice
        ],
    }


# --- 给看板用的字段/操作符清单，以及合法性校验 -------------------------

FIELD_CHOICES: list[tuple[str, str]] = [
    ("work_years", "工作年限"),
    ("degree", "学历"),
    ("expect_city", "期望城市"),
    ("expect_salary", "期望薪资"),
    ("skills", "技能"),
    ("current_title", "当前职位"),
    ("current_company", "当前公司"),
    ("expect_title", "期望职位"),
    ("age", "年龄"),
    ("school", "学校"),
    ("gender", "性别"),
]

OP_CHOICES: list[tuple[str, str]] = [
    ("gte", "大于等于"),
    ("lte", "小于等于"),
    ("eq", "等于"),
    ("ne", "不等于"),
    ("contains_any", "包含任一"),
    ("contains_all", "包含全部"),
    ("in", "属于其中之一"),
    ("exists", "有值"),
]

_LIST_OPS = {"contains_any", "contains_all", "in", "not_in"}
_NUMERIC_OPS = {"gte", "lte"}
_OP_NAMES = {k for k, _ in OP_CHOICES} | {"not_in", "any_in"}
_FIELD_NAMES = {k for k, _ in FIELD_CHOICES}


def _split_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value is None:
        return []
    import re

    return [p.strip() for p in re.split(r"[,，/、\s]+", str(value)) if p.strip()]


def prepare_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """把看板提交的需求规整成合法结构；不合法就抛 ValueError（带人能看懂的原因）。"""
    problems: list[str] = []
    name = str(spec.get("name") or "").strip()
    if not name:
        problems.append("需求名称不能为空")

    try:
        threshold = float(spec.get("threshold", 60))
    except (TypeError, ValueError):
        threshold = -1
    if not 0 <= threshold <= 100:
        problems.append("阈值要在 0-100 之间")

    def _clean(items: Any, where: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i, item in enumerate(items or []):
            pos = f"{where}第 {i + 1} 条"
            field = str(item.get("field") or "").strip()
            op = str(item.get("op") or "").strip()
            if field not in _FIELD_NAMES:
                problems.append(f"{pos}：不认识的字段 {field!r}")
                continue
            if op not in _OP_NAMES:
                problems.append(f"{pos}：不认识的操作 {op!r}")
                continue
            value = item.get("value")
            if op in _LIST_OPS:
                value = _split_value(value)
                if not value:
                    problems.append(f"{pos}：这个操作至少要填一个值")
                    continue
            elif op == "exists":
                value = None
            elif op in _NUMERIC_OPS:
                if field == "degree":
                    value = str(value or "").strip()
                    if not value:
                        problems.append(f"{pos}：学历要填具体学历（如 本科）")
                        continue
                else:
                    try:
                        value = float(str(value).strip())
                    except (TypeError, ValueError):
                        problems.append(f"{pos}：这个操作要填数字")
                        continue
            else:
                value = str(value or "").strip()
                if not value:
                    problems.append(f"{pos}：值不能为空")
                    continue
            row: dict[str, Any] = {"field": field, "op": op, "value": value}
            if "weight" in item:
                try:
                    row["weight"] = max(0.0, float(item["weight"]))
                except (TypeError, ValueError):
                    problems.append(f"{pos}：权重要是数字")
                    continue
            label = str(item.get("label") or "").strip()
            if label:
                row["label"] = label
            out.append(row)
        return out

    must = _clean(spec.get("must"), "硬条件")
    nice = _clean(spec.get("nice"), "加分项")
    if not must and not nice:
        problems.append("至少要有一条硬条件或加分项")

    if problems:
        raise ValueError("；".join(problems))
    return {"name": name, "threshold": threshold, "must": must, "nice": nice}
