"""核心数据模型。纯数据结构，不含 IO。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 条件判断的三态：命中 / 不满足 / 未知
HIT = "hit"
MISS = "miss"
UNKNOWN = "unknown"


@dataclass
class Candidate:
    """一份结构化后的候选人（来自在线简历）。"""

    uid: str
    name: str = ""
    age: int | None = None
    gender: str | None = None
    degree: str | None = None
    school: str | None = None
    work_years: float | None = None
    current_title: str | None = None
    current_company: str | None = None
    expect_title: list[str] = field(default_factory=list)
    expect_city: list[str] = field(default_factory=list)
    expect_salary: str | None = None
    skills: list[str] = field(default_factory=list)
    experiences: list[dict[str, Any]] = field(default_factory=list)
    applied_job_id: str | None = None
    applied_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str) -> Any:
        return getattr(self, name, None)

    def merge_missing_from(self, other: "Candidate") -> None:
        """把另一份记录里"有值而我没有"的字段补过来（去重时用）。"""
        for f in self.__dataclass_fields__:
            if f in ("uid", "raw"):
                continue
            if not _has_value(getattr(self, f)) and _has_value(getattr(other, f)):
                setattr(self, f, getattr(other, f))


def _has_value(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, (str, list, dict)):
        return len(v) > 0
    return True


@dataclass
class Condition:
    """单条判断条件。op 见 scoring.evaluate。"""

    field: str
    op: str
    value: Any = None
    label: str = ""

    @property
    def text(self) -> str:
        return self.label or f"{self.field} {self.op} {self.value}"


@dataclass
class Weighted:
    weight: float
    condition: Condition


@dataclass
class Requirement:
    """老板自己写的需求：硬条件 + 加权偏好。"""

    name: str
    must: list[Condition] = field(default_factory=list)
    nice: list[Weighted] = field(default_factory=list)
    threshold: float = 60.0

    @property
    def total_weight(self) -> float:
        return sum(w.weight for w in self.nice) or 1.0


@dataclass
class ScoreResult:
    uid: str
    name: str
    total: float
    passed_must: bool
    pending: list[str] = field(default_factory=list)
    hits: list[str] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    coverage: float = 1.0  # 有信息可判断的权重占比，1.0 表示信息完整
    reason: str = ""

    @property
    def short(self) -> str:
        """名单里一行的简短说明。"""
        return f"{self.total:5.1f}  {self.name or self.uid}  {self.reason}"
