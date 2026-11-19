"""本地看板：127.0.0.1 上的一张只读榜单。

只用标准库。不联网、不写浏览器、不改平台数据。
页面里的"生成草稿"只是把文本算出来给你复制。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .draft import build_draft
from .models import Candidate, Requirement, ScoreResult
from .requirement import (
    FIELD_CHOICES,
    OP_CHOICES,
    prepare_spec,
    requirement_from_dict,
    requirement_to_dict,
)
from .scoring import degree_level, rank

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>简历筛选看板</title>
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#262b36; --text:#e6e8ec;
          --dim:#8b93a1; --ok:#3fb950; --warn:#d29922; --bad:#f85149; --accent:#388bfd; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }
  header { padding:18px 24px; border-bottom:1px solid var(--line); display:flex;
           gap:16px; align-items:baseline; flex-wrap:wrap; }
  h1 { font-size:16px; margin:0; font-weight:600; }
  .req { color:var(--dim); }
  .body { display:flex; height:calc(100vh - 61px); }
  .list { flex:1; overflow:auto; padding:0 0 40px; }
  .side { width:420px; border-left:1px solid var(--line); padding:20px; overflow:auto;
          background:var(--panel); display:none; }
  .side.on { display:block; }
  .filters { padding:12px 24px; display:flex; gap:8px; border-bottom:1px solid var(--line);
             align-items:center; flex-wrap:wrap; }
  .filters button { background:transparent; color:var(--dim); border:1px solid var(--line);
                    padding:4px 10px; border-radius:999px; cursor:pointer; font-size:13px; }
  .filters button.on { color:var(--text); border-color:var(--accent); background:#1b2534; }
  select { background:var(--panel); color:var(--text); border:1px solid var(--line);
           border-radius:6px; padding:4px 8px; font-size:13px; }
  .chk { color:var(--dim); font-size:13px; display:flex; gap:6px; align-items:center;
         margin-left:auto; cursor:pointer; }
  table { width:100%; border-collapse:collapse; }
  th { position:sticky; top:0; background:var(--bg); text-align:left; font-weight:500;
       color:var(--dim); font-size:12px; padding:10px 12px; border-bottom:1px solid var(--line); }
  td { padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }
  tr.row { cursor:pointer; }
  tr.row:hover td { background:#151922; }
  .score { font-variant-numeric:tabular-nums; font-weight:600; }
  .tag { font-size:12px; padding:1px 7px; border-radius:999px; border:1px solid var(--line); }
  .t-ok { color:var(--ok); border-color:#1f4d2b; }
  .t-warn { color:var(--warn); border-color:#4d3a13; }
  .t-bad { color:var(--bad); border-color:#5a1f1c; }
  .reason { color:var(--dim); font-size:13px; }
  .cov { color:var(--dim); font-size:12px; }
  h2 { font-size:15px; margin:0 0 4px; }
  .kv { display:grid; grid-template-columns:88px 1fr; gap:6px 12px; margin:14px 0; font-size:13px; }
  .kv dt { color:var(--dim); }
  .kv dd { margin:0; }
  .btn { background:var(--accent); color:#fff; border:0; padding:8px 14px; border-radius:6px;
         cursor:pointer; font-size:13px; }
  .btn.ghost { background:transparent; border:1px solid var(--line); color:var(--text); }
  textarea { width:100%; height:190px; margin-top:12px; background:#0c0e12; color:var(--text);
             border:1px solid var(--line); border-radius:6px; padding:12px; font:13px/1.7 inherit;
             resize:vertical; }
  .hint { color:var(--dim); font-size:12px; margin-top:8px; }
  .mask { position:fixed; inset:0; background:#0008; display:none; z-index:10; }
  .mask.on { display:block; }
  .modal { position:fixed; top:6vh; left:50%; transform:translateX(-50%); width:min(760px,92vw);
           max-height:86vh; overflow:auto; background:var(--panel); border:1px solid var(--line);
           border-radius:10px; padding:22px; z-index:11; display:none; }
  .modal.on { display:block; }
  .modal h3 { font-size:14px; margin:18px 0 8px; color:var(--dim); font-weight:500; }
  .cond { display:grid; grid-template-columns:150px 130px 1fr 74px 30px; gap:8px; margin-bottom:8px;
          align-items:center; }
  .cond input[type=text], .cond input[type=number] { width:100%; background:#0c0e12; color:var(--text);
          border:1px solid var(--line); border-radius:6px; padding:5px 8px; font-size:13px; }
  .cond .del { background:transparent; border:1px solid var(--line); color:var(--dim);
          border-radius:6px; cursor:pointer; height:28px; }
  .reqname { display:flex; gap:10px; align-items:center; margin-bottom:10px; }
  .reqname input { flex:1; background:#0c0e12; color:var(--text); border:1px solid var(--line);
          border-radius:6px; padding:7px 10px; font-size:14px; }
  .reqname input[type=number] { flex:0 0 110px; }
  .err { color:var(--bad); font-size:13px; margin-top:10px; white-space:pre-wrap; }
</style></head>
<body>
<header>
  <h1>简历筛选看板</h1>
  <span class="req" id="req"></span>
  <span class="req" id="stat"></span>
  <button class="btn ghost" id="editReq" style="margin-left:auto">编辑需求</button>
</header>
<div class="filters" id="filters">
  <button data-f="all" class="on">全部</button>
  <button data-f="pass">达到阈值</button>
  <button data-f="pending">待确认</button>
  <button data-f="fail">未过硬条件</button>
  <select id="city"><option value="">全部城市</option></select>
  <select id="deg"><option value="">不限学历</option></select>
  <label class="chk"><input type="checkbox" id="fullonly"> 只看资料完整</label>
</div>
<div class="body">
  <div class="list"><table>
    <thead><tr><th style="width:64px">分数</th><th style="width:70px">完整度</th>
      <th style="width:76px">硬条件</th><th style="width:110px">姓名</th><th>理由</th></tr></thead>
    <tbody id="rows"></tbody>
  </table></div>
  <aside class="side" id="side"></aside>
</div>
<div class="mask" id="mask"></div>
<div class="modal" id="modal">
  <div class="reqname">
    <input id="reqName" type="text" placeholder="这条需求叫什么，比如：深圳后端工程师">
    <input id="reqThreshold" type="number" min="0" max="100" step="5" title="达到多少分算推荐">
  </div>
  <p class="hint">硬条件：不满足就不推荐；填不满的字段会标"待确认"，不会当成不满足。</p>
  <h3>硬条件</h3>
  <div id="mustList"></div>
  <button class="btn ghost" id="addMust">+ 加一条硬条件</button>
  <h3>加分项（权重越大越重要）</h3>
  <div id="niceList"></div>
  <button class="btn ghost" id="addNice">+ 加一条加分项</button>
  <p class="err" id="reqErr"></p>
  <div style="margin-top:18px; display:flex; gap:10px">
    <button class="btn" id="saveReq">保存并重新打分</button>
    <button class="btn ghost" id="cancelReq">取消</button>
  </div>
</div>
<script>
let DATA = {req:null, spec:null, choices:{fields:[],ops:[]}, rows:[], facets:{cities:[],degrees:[]}};
let FILTER = 'all', CUR = null, CITY = '', DEG = '', FULL = false, DEGS = [];
const esc = s => (s ?? '').toString().replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const flag = r => !r.passed_must ? ['未过','t-bad'] : (r.pending.length ? ['待确认','t-warn'] : ['通过','t-ok']);

// 未知值不隐藏：筛选只排除"明确不符合"的人
const cityOk = c => !CITY || !(c.expect_city||[]).length || c.expect_city.includes(CITY);
const degreeOk = c => !DEG || !c.degree || (DEGS.indexOf(c.degree) >= 0 && DEGS.indexOf(c.degree) <= DEGS.indexOf(DEG));

function render() {
  const rows = DATA.rows.filter(r => {
    const base = FILTER === 'all' ? true
      : FILTER === 'pass' ? (r.passed_must && r.total >= DATA.req.threshold)
      : FILTER === 'pending' ? (r.passed_must && r.pending.length)
      : !r.passed_must;
    return base && cityOk(r.cand) && degreeOk(r.cand) && (!FULL || r.coverage >= 1);
  });
  document.getElementById('rows').innerHTML = rows.map(r => {
    const [txt, cls] = flag(r);
    return `<tr class="row" data-uid="${esc(r.uid)}">
      <td class="score" style="${r.passed_must ? '' : 'color:var(--dim)'}">${r.total.toFixed(1)}${r.passed_must ? '' : '*'}</td>
      <td class="cov">${Math.round(r.coverage*100)}%</td>
      <td><span class="tag ${cls}">${txt}</span></td>
      <td>${esc(r.name || r.uid)}</td>
      <td class="reason">${esc(r.reason)}</td></tr>`;
  }).join('');
  document.querySelectorAll('tr.row').forEach(tr =>
    tr.onclick = () => open(tr.dataset.uid));
  const pass = DATA.rows.filter(r => r.passed_must && r.total >= DATA.req.threshold).length;
  const shown = rows.length === DATA.rows.length ? '' : ` · 当前显示 ${rows.length} 人`;
  document.getElementById('stat').textContent =
    `共 ${DATA.rows.length} 人 · 达到阈值 ${pass} 人${shown}`;
}

function open(uid) {
  CUR = DATA.rows.find(r => r.uid === uid);
  const c = CUR.cand, s = document.getElementById('side');
  const [txt, cls] = flag(CUR);
  s.innerHTML = `<h2>${esc(c.name || c.uid)}</h2>
    <span class="tag ${cls}">${txt}</span>
    <dl class="kv">
      <dt>分数</dt><dd>${CUR.total.toFixed(1)} / 阈值 ${DATA.req.threshold}</dd>
      <dt>完整度</dt><dd>${Math.round(CUR.coverage*100)}%</dd>
      <dt>当前</dt><dd>${esc(c.current_title || '未知')} ${esc(c.current_company || '')}</dd>
      <dt>经验</dt><dd>${c.work_years ? c.work_years + ' 年' : '未知'}</dd>
      <dt>学历</dt><dd>${esc(c.degree || '未知')}</dd>
      <dt>期望</dt><dd>${esc((c.expect_city||[]).join('、') || '未知')} · ${esc(c.expect_salary || '未知')}</dd>
      <dt>技能</dt><dd>${esc((c.skills||[]).join('、') || '未知')}</dd>
      <dt>命中</dt><dd>${esc(CUR.hits.join('；') || '无')}</dd>
      <dt>待确认</dt><dd>${esc(CUR.pending.join('；') || '无')}</dd>
      <dt>不满足</dt><dd>${esc(CUR.misses.join('；') || '无')}</dd>
    </dl>
    <button class="btn" onclick="draft('${esc(c.uid)}')">生成招呼语草稿</button>
    <div id="draftBox"></div>`;
  s.classList.add('on');
}

async function draft(uid) {
  const res = await fetch('/api/draft', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({uid})});
  const {text} = await res.json();
  const box = document.getElementById('draftBox');
  box.innerHTML = `<textarea id="dt"></textarea>
    <button class="btn ghost" id="cp">复制</button>
    <p class="hint">只生成文本。发不发、发给谁，由你在 BOSS 里手动决定。</p>`;
  document.getElementById('dt').value = text;
  document.getElementById('cp').onclick = async () => {
    await navigator.clipboard.writeText(text);
    document.getElementById('cp').textContent = '已复制';
  };
}

document.querySelectorAll('#filters button').forEach(b => b.onclick = () => {
  FILTER = b.dataset.f;
  document.querySelectorAll('#filters button').forEach(x => x.classList.toggle('on', x === b));
  render();
});
document.getElementById('city').onchange = e => { CITY = e.target.value; render(); };
document.getElementById('deg').onchange = e => { DEG = e.target.value; render(); };
document.getElementById('fullonly').onchange = e => { FULL = e.target.checked; render(); };

function reqDraft() {
  const rowOf = (el, nice) => {
    const [fs, os] = el.querySelectorAll('select');
    const inp = el.querySelector('input[type=text]');
    const w = el.querySelector('input[type=number]');
    const o = {field: fs.value, op: os.value, value: inp.value.trim()};
    if (nice) o.weight = Number(w.value || 1);
    return o;
  };
  return {
    name: document.getElementById('reqName').value.trim(),
    threshold: Number(document.getElementById('reqThreshold').value || 60),
    must: [...document.querySelectorAll('#mustList .cond')].map(el => rowOf(el, false)),
    nice: [...document.querySelectorAll('#niceList .cond')].map(el => rowOf(el, true)),
  };
}

function condRow(host, item, nice) {
  const el = document.createElement('div');
  el.className = 'cond';
  const fs = document.createElement('select');
  DATA.choices.fields.forEach(([v, t]) => fs.add(new Option(t, v)));
  const os = document.createElement('select');
  DATA.choices.ops.forEach(([v, t]) => os.add(new Option(t, v)));
  const inp = document.createElement('input');
  inp.type = 'text';
  inp.placeholder = '值，多个用、分隔';
  const w = document.createElement('input');
  w.type = 'number'; w.min = '0'; w.step = '1'; w.title = '权重';
  const del = document.createElement('button');
  del.className = 'del'; del.textContent = '×'; del.title = '删除这条';
  del.onclick = () => el.remove();
  if (item) {
    fs.value = item.field; os.value = item.op;
    inp.value = Array.isArray(item.value) ? item.value.join('、') : (item.value ?? '');
    if (nice) w.value = item.weight ?? 1;
  }
  fs.onchange = os.onchange = () => {};
  el.append(fs, os, inp, nice ? w : Object.assign(document.createElement('span'), {textContent: ''}), del);
  host.appendChild(el);
}

function openEditor() {
  document.getElementById('reqName').value = DATA.spec.name;
  document.getElementById('reqThreshold').value = DATA.req.threshold;
  const must = document.getElementById('mustList'), nice = document.getElementById('niceList');
  must.innerHTML = ''; nice.innerHTML = '';
  DATA.spec.must.forEach(it => condRow(must, it, false));
  DATA.spec.nice.forEach(it => condRow(nice, it, true));
  document.getElementById('reqErr').textContent = '';
  document.getElementById('mask').classList.add('on');
  document.getElementById('modal').classList.add('on');
}

function closeEditor() {
  document.getElementById('mask').classList.remove('on');
  document.getElementById('modal').classList.remove('on');
}

async function saveReq() {
  const err = document.getElementById('reqErr');
  err.textContent = '';
  const res = await fetch('/api/requirement', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(reqDraft())});
  const data = await res.json();
  if (!res.ok) { err.textContent = data.error || '保存失败'; return; }
  DATA = data;
  if (data.saved && !data.saved.ok) {
    // 分数已经按新需求重算了，但没写进库——如实说清楚，别让人以为存上了
    err.textContent = '已按新需求重新打分，但没能存进本地库：' + (data.saved.error || '未知原因');
    document.getElementById('req').textContent = data.req.name;
    render();
    return;
  }
  const citySel = document.getElementById('city'), degSel = document.getElementById('deg');
  const keepCity = citySel.value, keepDeg = degSel.value;
  citySel.length = 1; degSel.length = 1;
  DEGS = data.facets.degrees;
  data.facets.cities.forEach(c => citySel.add(new Option(c, c)));
  DEGS.forEach(c => degSel.add(new Option(c + '及以上', c)));
  citySel.value = keepCity; degSel.value = keepDeg;
  CUR = null;
  document.getElementById('side').classList.remove('on');
  document.getElementById('req').textContent = data.req.name;
  render();
  closeEditor();
}

document.getElementById('editReq').onclick = openEditor;
document.getElementById('cancelReq').onclick = closeEditor;
document.getElementById('mask').onclick = closeEditor;
document.getElementById('saveReq').onclick = saveReq;
document.getElementById('addMust').onclick = () => condRow(document.getElementById('mustList'), null, false);
document.getElementById('addNice').onclick = () => condRow(document.getElementById('niceList'), null, true);

fetch('/api/board').then(r => r.json()).then(d => {
  DATA = d;
  DEGS = d.facets.degrees;
  const citySel = document.getElementById('city'), degSel = document.getElementById('deg');
  d.facets.cities.forEach(c => citySel.add(new Option(c, c)));
  DEGS.forEach(c => degSel.add(new Option(c + '及以上', c)));
  document.getElementById('req').textContent = d.req.name;
  render();
});
</script></body></html>
"""


class Board:
    """把一次打分结果挂在内存里，供 HTTP 层取用。"""

    def __init__(
        self,
        results: list[ScoreResult],
        req: Requirement,
        cands: list[Candidate] | None = None,
        on_save=None,
    ) -> None:
        self.req = req
        self.results = results
        self.by_uid = {r.uid: r for r in results}
        self.cands = {c.uid: c for c in (cands or [])}
        self._cand_list = list(cands or [])
        self.on_save = on_save
        self.save_error: str | None = None

    def apply(self, spec: dict) -> dict:
        """看板上改了需求：校验 → 重新打分 → 落库 → 返回新的一页数据。"""
        clean = prepare_spec(spec)
        req = requirement_from_dict(clean)
        results = rank(self._cand_list, req)
        self.req = req
        self.results = results
        self.by_uid = {r.uid: r for r in results}
        self.save_error: str | None = None
        if self.on_save is not None:
            try:
                self.on_save(req, clean)
            except Exception as exc:  # noqa: BLE001 - 页面照常可用，但要如实说没存上
                self.save_error = str(exc) or exc.__class__.__name__
        return self.payload()

    def payload(self) -> dict:
        cities: set[str] = set()
        degrees: set[str] = set()
        for c in self.cands.values():
            cities.update(c.expect_city or [])
            if c.degree:
                degrees.add(c.degree)
        return {
            "req": {
                "name": self.req.name,
                "threshold": self.req.threshold,
            },
            "spec": requirement_to_dict(self.req),
            "choices": {"fields": FIELD_CHOICES, "ops": OP_CHOICES},
            "facets": {
                "cities": sorted(cities),
                "degrees": sorted(degrees, key=lambda d: degree_level(d) or 0, reverse=True),
            },
            "rows": [
                {**r.__dict__, "cand": asdict(self.cands[r.uid]) if r.uid in self.cands else {}}
                for r in self.results
            ],
            "saved": {"ok": self.save_error is None, "error": self.save_error},
        }

    def draft_for(self, uid: str) -> str:
        cand = self.cands.get(uid)
        if cand is None:
            raise KeyError(f"没有这个候选人: {uid}")
        return build_draft(cand, self.by_uid[uid], self.req)


def make_handler(board: Board):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 静音，别刷屏
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/board":
                body = json.dumps(board.payload(), ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            else:
                self._send(404, b'{"error":"not found"}', "application/json")

        def do_POST(self) -> None:
            if self.path == "/api/requirement":
                self._post_requirement()
                return
            if self.path != "/api/draft":
                self._send(404, b'{"error":"not found"}', "application/json")
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(n) or b"{}")
                text = board.draft_for(data["uid"])
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                self._send(400, json.dumps({"error": str(exc)}).encode(), "application/json")
                return
            body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")

        def _post_requirement(self) -> None:
            try:
                n = int(self.headers.get("Content-Length") or 0)
                spec = json.loads(self.rfile.read(n) or b"{}")
                payload = board.apply(spec)
            except ValueError as exc:
                self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode(), "application/json")
                return
            except json.JSONDecodeError:
                self._send(400, json.dumps({"error": "请求不是合法 JSON"}, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")

    return Handler


def serve(
    results: list[ScoreResult],
    req: Requirement,
    cands: list[Candidate] | None = None,
    host: str = "127.0.0.1",
    port: int = 8686,
    on_save=None,
):
    board = Board(results, req, cands, on_save=on_save)
    httpd = ThreadingHTTPServer((host, port), make_handler(board))
    return httpd
