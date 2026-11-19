# 当前进度

> 每个会话收工时更新这一页。新会话开工先读它。

## 现在能跑什么

```bash
python -m bosscreen.cli demo              # mock 数据跑通：解析 → 打分 → 名单
python -m bosscreen.cli serve --mock      # 本地看板 http://127.0.0.1:8686/
python -m bosscreen.cli doctor            # 自检：配置、浏览器可达性、选择器
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
- [x] `doctor` 接入浏览器探测
- [x] 打包元数据静态校验（tomllib，不需要联网）
- [x] 单测 21 条

## 未完成

- [ ] 采集层：会话列表 → 简历详情（**需要真实招聘账号校准**）
- [ ] `doctor` 的选择器逐项核对流程（需要真机页面）
- [ ] `pip install -e .` 实机验证（离线环境装不了 setuptools）

## 阻塞

**采集层无法校准**：开发环境没有企业招聘者账号，`/web/boss/*` 一律跳回求职端。
因此采集器只按"配置 + 自检"设计，未在真机验证。**没有账号的会话不要试图重写采集层**，先做别的。

## 下一步（无账号也能做）

1. 简历字段解析的更细粒度（项目经历、教育经历）
2. 草稿的可选 LLM 改写（现在纯模板）
3. 采集层的"干跑"模式：只枚举列表页 URL 和骨架，不取字段
