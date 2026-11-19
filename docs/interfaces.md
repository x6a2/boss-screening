# 模块与数据结构

## 分层

```
cli.py            命令入口（demo / doctor / collect / serve）
  ├─ cdp.py        最小 WebSocket + CDP 客户端（Runtime.evaluate）
  ├─ transport.py  Chrome 调试端口 HTTP 侧：探测、列标签、开/关标签
  ├─ collector.py 采集：CDP → 选择器 → 原始 dict（唯一依赖浏览器的层）
  ├─ parsing.py   原始 dict → Candidate（纯函数，可单测）
  ├─ scoring.py   需求 × Candidate → ScoreResult（纯函数，可单测）
  ├─ draft.py     候选人 + 评分 → 招呼语文本（纯函数，只出文本）
  ├─ store.py     SQLite 持久化
  └─ web.py       本地看板（标准库 http.server）
```

**关键约束**：`parsing` 与 `scoring` 是纯函数，不碰网络、不碰浏览器、不碰数据库。
这样采集层坏掉时，其余部分仍然可测、可用。

## 数据结构

```python
@dataclass
class Candidate:
    uid: str                  # 平台内唯一 id（去重键）
    name: str
    age: int | None
    gender: str | None
    degree: str | None        # 学历，原始字符串
    school: str | None
    work_years: float | None  # 工作年限
    current_title: str | None
    current_company: str | None
    expect_title: list[str]   # 期望职位
    expect_city: list[str]
    expect_salary: str | None # 原始字符串，如 "20-30K"
    skills: list[str]
    experiences: list[dict]   # 工作经历，字段随平台
    applied_job_id: str | None
    applied_at: str | None    # ISO 时间
    raw: dict                 # 原始数据，便于回溯
```

```python
@dataclass
class Requirement:
    name: str
    must: list[Condition]     # 硬条件
    nice: list[Weighted]      # 软条件（条件 + 权重）
```

```python
@dataclass
class ScoreResult:
    uid: str
    total: float              # 0-100
    passed_must: bool
    pending: list[str]        # 因"未知"待确认的硬条件
    hits: list[str]           # 命中的软条件
    misses: list[str]         # 明确不满足的软条件
    unknowns: list[str]       # 因缺字段无法判断的软条件
    reason: str               # 一句话可读理由
```

## 三态判断

条件评估只有三种结果：`hit` / `miss` / `unknown`。

- `unknown` 不扣分，但会进入 `pending`（硬条件）或 `unknowns`（软条件），并在名单里显示
- 硬条件出现 `unknown` 时，`passed_must` 记 `True` 但标记待确认——宁可让人看，也不静默丢弃

## SQLite

```sql
candidates(uid PK, name, data JSON, first_seen, last_seen)
scores(uid, requirement_id, total, passed_must, detail JSON, scored_at)
requirements(id PK, name, definition JSON, created_at)
```

## 选择器配置

`config/selectors.boss.json`：

```json
{
  "conversation_list": { "item": "...", "name": "...", "job": "..." },
  "resume_detail": { "name": "...", "degree": "..." },
  "risk_markers": { "captcha": ["..."], "login_wall": ["..."] }
}
```

代码只通过键名取值；缺失的键必须报"未配置"，不能静默返回空。

## 采集层的约定

`collector.Collector` 只做三件事：开标签、跑一段由配置生成的 JS、关标签。它不知道 BOSS 的任何类名。

- `list_js(spec)` / `detail_js(spec)`：把选择器配置 JSON 编码进表达式，返回 JSON 字符串
- 详情页找不到 `container` 时返回 `{_error: "container-not-found"}`，调用方**必须**报错停下（不静默给空数据）
- `_check_risk` 每次导航后跑一次；命中验证码/登录墙/限流 → `RiskDetected`，整轮停
- `Usage` 记 `data/usage.json`：当天读了几页；超 `daily_page_limit` → `BudgetExceeded`
- `calibrated=false` 的选择器由 cli 拦下，采集器本身不管这个（它只认参数）

原始 dict 的键名 = 选择器配置里 `fields` 的键名（snake_case），由 `parsing.FIELD_MAP` 映射到 `Candidate`。
