"""配置与选择器。

原则：选择器不写在代码里。页面改版时改 JSON，不改代码。
缺失的键必须报错，不能静默返回空值。
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config.toml"
DEFAULT_SELECTORS = ROOT / "config" / "selectors.boss.json"

# 采集层必须具备的选择器分组；缺任何一组都不该开始跑
REQUIRED_SELECTOR_GROUPS = ("conversation_list", "resume_detail")


@dataclass
class AppConfig:
    db_path: str = "data/bosscreen.db"
    throttle_min_seconds: float = 3.0
    throttle_max_seconds: float = 7.0
    daily_page_limit: int = 300
    extra: dict[str, Any] = field(default_factory=dict)


def load_config(path: str | Path | None = None) -> AppConfig:
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.exists():
        return AppConfig()
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    known = {k: v for k, v in data.items() if k in AppConfig.__dataclass_fields__ and k != "extra"}
    return AppConfig(**known, extra={k: v for k, v in data.items() if k not in known})


def load_selectors(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_SELECTORS
    if not p.exists():
        raise FileNotFoundError(
            f"找不到选择器配置：{p}\n"
            "从 config/selectors.boss.example.json 复制一份再改。"
        )
    return json.loads(p.read_text(encoding="utf-8"))


def check_selectors(selectors: dict[str, Any]) -> list[str]:
    """返回问题列表；空列表表示可以跑。"""
    problems: list[str] = []
    for group in REQUIRED_SELECTOR_GROUPS:
        if group not in selectors:
            problems.append(f"缺少分组：{group}")
            continue
        if not isinstance(selectors[group], dict) or not selectors[group]:
            problems.append(f"分组 {group} 为空")
    risk = selectors.get("risk_markers")
    if not risk:
        problems.append("缺少 risk_markers：无法识别验证码/登录墙，这会让采集变得危险")
    return problems
