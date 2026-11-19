"""招呼语草稿生成。

只生成文本，不发送、不点击、不调用任何平台接口。
草稿里的每个事实都来自候选人自己的资料，不编造公司、薪资、项目。
"""

from __future__ import annotations

from .models import Candidate, Requirement, ScoreResult

_OPENERS = [
    "你好{name}，",
    "Hi {name}，",
    "{name}你好，",
]

_BODY_YEARS = "看到你有 {years} 年工作经验，"
_BODY_TITLE = "你目前在{company}做{title}，"
_BODY_SKILL = "你的 {skill} 背景和我们在找的方向比较接近，"

_CLOSERS = [
    "我们这边在招{job}，方便聊两句吗？",
    "想和你确认一下{job}这个岗位是否在你考虑范围内？",
    "如果方便，想占用你几分钟聊聊{job}，你看可以吗？",
]


def _pick(seq: list[str], seed: str) -> str:
    return seq[sum(ord(ch) for ch in seed) % len(seq)] if seq else ""


def build_draft(cand: Candidate, result: ScoreResult, req: Requirement) -> str:
    """返回一段可直接复制的招呼语。信息不足时如实说明，不硬凑。"""
    parts: list[str] = []

    opener = _pick(_OPENERS, cand.uid).format(name=cand.name or "你好")
    parts.append(opener)

    if cand.work_years:
        parts.append(_BODY_YEARS.format(years=int(cand.work_years)))
    if cand.current_title:
        company = f"在{cand.current_company}" if cand.current_company else ""
        parts.append(_BODY_TITLE.format(company=company, title=cand.current_title))
    if cand.skills:
        parts.append(_BODY_SKILL.format(skill="、".join(cand.skills[:2])))

    if len(parts) == 1:  # 除了称呼没有任何可用信息
        parts.append("看到你的资料，想进一步了解一下你的方向，")

    parts.append(_pick(_CLOSERS, cand.uid).format(job=req.name))
    text = "".join(parts)

    if result.pending:
        # 待确认的硬条件，用括号提醒使用者自己去核实，而不是假装满足
        text += "\n\n（发送前确认：" + "、".join(result.pending) + "）"
    return text
