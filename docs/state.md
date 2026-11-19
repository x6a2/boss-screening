# 当前进度

> 每个会话收工时更新这一页。新会话开工先读它。

## 现在能跑什么

```bash
python -m bosscreen.cli demo              # mock 数据跑通：解析 → 打分 → 名单
python -m bosscreen.cli serve --mock      # 本地看板 http://127.0.0.1:8686/
python -m bosscreen.cli doctor            # 自检：配置、浏览器可达性、选择器
python -m bosscreen.cli collect --fixture # 用样例页面跑通"浏览器 → 选择器 → 名单"整条链路
```

`python -m bosscreen ...` 与 `bosscreen ...` 等价。

## 已完成

- [x] 仓库骨架、MIT 许可、文档四件套
- [x] 数据模型（Candidate / Requirement / ScoreResult）
- [x] 结构化简历解析（在线简历 dict → Candidate）
- [x] 硬条件 + 加权软分 + 理由生成
- [x] 去重（同人多次投递合并）
- [x] SQLite 存储
- [x] mock 数据 + demo 命令
- [x] 分数公式修正：未知计入分母（信息不全不再白拿高分）+ 完整度列
- [x] Web 看板（标准库 http.server，只读，127.0.0.1）
- [x] 看板筛选：状态 / 城市 / 学历 / 资料完整度
- [x] 招呼语草稿生成（规则模板，只出文本，不发送）
- [x] 自研 CDP 客户端（cdp.py，纯标准库 WebSocket + Runtime.evaluate，已在 headless Chrome 156 验证）
- [x] 浏览器探测（transport.py）：找调试端口、列标签页、判断是否在招聘端，全程不点击
- [x] **采集层（collector.py）**：选择器驱动、只读、带风控自检 + 日预算闸 + 节流；已在 `tests/fixtures/` 样例页面上端到端跑通（CDP → 抽取 → Candidate → 打分 → 写库）
- [x] `calibrated=false` 时拒绝采集（防止拿猜测的选择器上真机乱抓）
- [x] 页面结构对不上时直接报错，不静默返回空
- [x] `doctor` 接入浏览器探测
- [x] 打包元数据静态校验（tomllib，不需要联网）
- [x] **看板内编辑需求**：硬条件 / 加分项 / 权重 / 阈值都能改，保存即重算并落库，存不上会在弹窗里说明
- [x] **列表滚动翻页**：滚到底自动加载（`paging.mode=scroll`），按 href 去重，连续 3 次没有新卡片才认定到底
- [x] 修掉"新标签页还没加载完就去读"的竞态（新页一开始是 about:blank 且已 complete，会误判为加载完成）
- [x] **选择器体检 `bosscreen check`**：容器在不在、几条、每个字段命中几个、样本是什么；容器没命中直接退出 3，字段没命中退出 1，全命中才提示可以置 `calibrated=true`
- [x] **可发布性验证**：全新 `git clone` 到临时目录 → `python -m bosscreen demo` 与 55 条测试都通过；仓库无 pip 临时目录残留
- [x] 单测 55 条（含 6 条需要 Chrome 的端到端测试，默认跳过：滚动到底 / 短列表不空转 / 详情页紧接打开能读到 / 体检命中数与样本 / 容器错要报告不抛错）

## 未完成

- [ ] **真机选择器校准**：`config/selectors.boss.example.json` 里标 TODO 的字段
- [ ] `doctor` 的选择器逐项核对流程（需要真机页面）
- [ ] `pip install -e .` 实机验证（离线环境装不了 setuptools）

## 阻塞

**真机校准需要企业招聘者账号**：开发环境没有该账号，`/web/boss/*` 一律跳回求职端。

已经做到的是：把"真实页面上的选择器"隔离成配置 + 用样例页面验证整条链路可跑。
所以有账号之后的工作量很小——打开页面，逐个填选择器，把 `calibrated` 改 true。

**没有账号的会话不要重写采集层**，先做"下一步"里的活。

## 下一步（无账号也能做）

1. 简历字段解析更细（项目经历、教育经历、求职状态）
2. 看板导出名单（CSV）
3. 草稿的可选 LLM 改写（现在纯模板）
4. 多份需求方案并存（现在只有一份当前需求）

**有账号后的第一天**：开 9222 的 Chrome 登录招聘端 → `bosscreen check --kind list --page <投递列表 URL>` 改到全 ✓ →
`bosscreen check --kind detail --page <某个在线简历 URL>` 改到全 ✓ → 置 `calibrated=true` → `collect --limit 2`。

## 有账号之后

```bash
# 1. 自己开一个带调试端口的 Chrome，登录招聘端
chrome.exe --remote-debugging-port=9222
# 2. 自检：先确认能连上、页面能读
python -m bosscreen.cli doctor --selectors config/selectors.boss.json
# 3. 逐个字段对照页面，把选择器填进 config/selectors.boss.json
# 4. 把 calibrated 改成 true
# 5. 小批量试跑（先 --limit 2，确认无误再放大）
python -m bosscreen.cli collect --selectors config/selectors.boss.json --limit 2
```
