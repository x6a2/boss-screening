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

## 看板的 HTTP 接口

只监听 `127.0.0.1`，无鉴权（本机自用）。全部 JSON 用 UTF-8。

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/` | 内嵌的看板页面（单个 HTML，无外部资源） |
| GET | `/api/board` | 当前需求 + 名单 + 筛选用的 facets + 可编辑的 spec/choices |
| POST | `/api/draft` | `{uid}` → `{text}`，招呼语草稿（只出文本） |
| POST | `/api/requirement` | `spec` → 校验、重算、落库，返回新的 board payload |

`/api/board` 的形状：

```json
{
  "req":    {"name": "...", "threshold": 60.0},
  "spec":   {"name": "...", "threshold": 60.0, "must": [...], "nice": [...]},
  "choices":{"fields": [["work_years","工作年限"], ...], "ops": [["gte","大于等于"], ...]},
  "facets": {"cities": ["深圳"], "degrees": ["硕士","本科"]},
  "rows":   [{"uid": "...", "total": 85.7, "passed_must": true, "pending": [], "coverage": 1.0, "cand": {...}}],
  "saved":  {"ok": true, "error": null}
}
```

`/api/requirement` 的三条约定：

- 校验失败 → HTTP 400，`{"error": "需求名称不能为空；阈值要在 0-100 之间；..."}`（中文、可直接展示）
- 校验通过但落库失败 → HTTP 200，`saved.ok=false` + `error`，**分数仍然按新需求重算**（页面不假装成功）
- 校验通过且落库成功 → `saved.ok=true`，同时把用户的 `--requirement` 文件回写（`mock` 目录下的样例不动）

## 滚动翻页的约定

`collector.list_spec["paging"]`：

```json
{"mode": "scroll", "scroll_container": "...", "max_scrolls": 10, "stall_limit": 3}
```

- `mode` 只认 `scroll`；没有这一段就只取首屏
- 每轮：滚动到底 → `_sleep()` 等懒加载 → 重新抽整页 → `merge_rows` 按 href（缺 href 时用 姓名+岗位）去重 → 风控检查
- 连续 `stall_limit` 次没新卡片 → 认定到底；到 `max_scrolls` 还没到底 → 日志明确写"可能还有更多"
- 滚动只在同一个 CDP 会话里做，不重新导航，所以**不额外计一次页面预算**

`_wait_ready(sess, url)` 必须同时满足 `readyState=complete` **且** `location.href` 与目标 URL 对得上。
少了后半句就会读到新标签页的初始 `about:blank`——它本来就是 complete。
