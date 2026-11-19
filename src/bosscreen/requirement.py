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
