"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

from . import transport
from .collector import BudgetExceeded, Collector, RiskDetected, Usage
from .config import load_config, load_selectors, check_selectors
from .models import Candidate
from .parsing import dedupe, from_platform
from .requirement import load_requirement, requirement_to_dict
from .scoring import rank
from .store import Store
from .web import serve

ROOT = Path(__file__).resolve().parents[2]


def _load_mock() -> list[Candidate]:
    raw = json.loads((ROOT / "data" / "mock" / "applicants.json").read_text(encoding="utf-8"))
    return [from_platform(item.get("uid") or f"idx{i}", item) for i, item in enumerate(raw)]


def load_store_candidates(db: str | None = None) -> list[Candidate]:
    path = Path(db or load_config().db_path)
    if not path.exists():
        return []
    store = Store(path)
    try:
        return store.load_candidates()
    finally:
        store.close()


def _print_board(results, req) -> None:
    print(f"\n需求：{req.name}   阈值 {req.threshold:g}\n")
    print(f"{'分数':>6}  {'完整度':>6}  {'硬条件':<6} {'姓名':<10} 理由")
    print("-" * 84)
    for r in results:
        if not r.passed_must:
            flag = "未过"
        elif r.pending:
            flag = "待确认"
        else:
            flag = "通过"
        print(f"{r.total:6.1f}  {r.coverage:6.0%}  {flag:<6} {r.name or r.uid:<10} {r.reason}")
    ok = sum(1 for r in results if r.passed_must and r.total >= req.threshold)
    pending = sum(1 for r in results if r.passed_must and r.pending)
    print("-" * 84)
    print(
        f"合计 {len(results)} 人；达到阈值 {ok} 人；"
        f"其中待确认 {pending} 人；未过硬条件 {sum(1 for r in results if not r.passed_must)} 人\n"
    )


def cmd_demo(args: argparse.Namespace) -> int:
    cands = dedupe(_load_mock())
    req = load_requirement(ROOT / "data" / "mock" / "requirement.json")
    results = rank(cands, req)
    _print_board(results, req)

    cfg = load_config()
    store = Store(args.db or cfg.db_path)
    store.upsert_candidates(cands)
    store.save_scores("demo", results)
    print(f"已写入 {store.path}（{len(cands)} 人 / {len(results)} 条评分）")
    store.close()
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    cands = dedupe([from_platform(x.get("uid") or f"idx{i}", x) for i, x in enumerate(raw)])
    req = load_requirement(args.requirement)
    results = rank(cands, req)
    _print_board(results, req)
    if args.json:
        print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    problems: list[str] = []
    notes: list[str] = []

    if sys.version_info < (3, 11):
        problems.append(f"需要 Python 3.11+，当前 {sys.version.split()[0]}")
    else:
        notes.append(f"Python {sys.version.split()[0]}")

    notes.append(f"工作目录 {ROOT}")

    sel_path = Path(args.selectors) if args.selectors else ROOT / "config" / "selectors.boss.json"
    if not sel_path.exists():
        problems.append(
            f"缺少选择器配置：{sel_path} —— 采集层无法工作。"
            "从 config/selectors.boss.example.json 复制一份。"
        )
    else:
        try:
            sel = load_selectors(sel_path)
            problems.extend(check_selectors(sel))
            if not sel.get("calibrated"):
                problems.append("选择器未校准（calibrated=false）：里面的 TODO 值需要真机确认")
        except json.JSONDecodeError as exc:
            problems.append(f"选择器配置不是合法 JSON：{exc}")

    cfg = load_config()
    notes.append(f"限速 {cfg.throttle_min_seconds}-{cfg.throttle_max_seconds}s，日上限 {cfg.daily_page_limit} 页")

    # --- 浏览器可达性（只读，不点任何东西）----------------------------
    ports = tuple(args.ports) if args.ports else transport.DEFAULT_PORTS
    probe = transport.probe(ports)
    if probe.port is None:
        problems.append(
            f"{ports} 上没有发现开着调试端口的 Chrome。"
            "自己启动一个带 --remote-debugging-port 的 Chrome 并登录招聘端后再来。"
        )
    else:
        notes.append(f"Chrome 已连接（{probe.browser or '版本未知'}）@ 端口 {probe.port}，{probe.page_count} 个标签页")
        for title, url in probe.zhipin_pages[:5]:
            notes.append(f"BOSS 页面：{title or '(无标题)'} — {url[:90]}")
        if probe.recruiter_page:
            notes.append(f"招聘端页面已就绪：{probe.recruiter_page[:90]}")
        else:
            problems.append(probe.blocked_reason)

    print("自检结果：")
    for n in notes:
        print(f"  ok   {n}")
    for p in problems:
        print(f"  问题 {p}")

    if problems:
        print("\n结论：当前状态无法采集真实简历，但 demo / 打分 / 看板链路可用。")
        return 1
    print("\n结论：配置齐全，可以尝试采集（选择器仍需第一次运行时核对）。")
    return 0


def _uid_from_url(url: str) -> str:
    tail = urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return urllib.parse.unquote(tail).removesuffix(".html") or url


def cmd_collect(args: argparse.Namespace) -> int:
    sel_path = Path(args.selectors) if args.selectors else ROOT / "config" / "selectors.boss.json"
    if not sel_path.exists():
        print(f"缺少选择器配置 {sel_path}；从 config/selectors.boss.example.json 复制一份。")
        return 1
    sel = load_selectors(sel_path)
    problems = check_selectors(sel)
    if problems:
        for p in problems:
            print(f"配置问题：{p}")
        return 1
    if not sel.get("calibrated") and not args.force:
        print(
            "选择器未校准（calibrated=false），拒绝采集。\n"
            "先用 tests/fixtures/ 里的样例跑一遍：\n"
            "  bosscreen collect --fixture\n"
            "真机上确认过每个选择器之后，把 calibrated 改成 true（或用 --force）。"
        )
        return 1

    port = args.port or transport.find_port(tuple(args.ports) if args.ports else transport.DEFAULT_PORTS)
    if port is None:
        print("没找到开着调试端口的 Chrome。先自己启动一个：\n"
              "  chrome.exe --remote-debugging-port=9222")
        return 1

    cfg = load_config()
    if args.fixture:
        list_url = (ROOT / "tests" / "fixtures" / "list.html").as_uri()
        delay = (0.0, 0.0)
    else:
        list_url = args.list_url or sel.get("conversation_list", {}).get("url")
        if not list_url:
            print("没有列表页 URL：用 --list-url 指定，或在选择器配置里写 conversation_list.url")
            return 1
        delay = (cfg.throttle_min_seconds, cfg.throttle_max_seconds)

    usage = Usage(Path(args.usage) if args.usage else ROOT / "data" / "usage.json")
    col = Collector(
        port=port,
        list_spec=sel["conversation_list"],
        detail_spec=sel["resume_detail"],
        risk_markers=sel.get("risk_markers", {}),
        usage=usage,
        daily_limit=args.daily_limit or cfg.daily_page_limit,
        delay=delay,
    )

    try:
        rows = col.list_page(list_url)
        urls = [urllib.parse.urljoin(list_url, r["href"]) for r in rows if r.get("href")]
        print(f"列表页 {len(rows)} 条，其中 {len(urls)} 条有详情链接")
        details = col.collect(urls, limit=args.limit)
    except (RiskDetected, BudgetExceeded) as exc:
        print(f"中止：{exc}")
        for line in col.log:
            print(f"  · {line}")
        return 2

    cands = dedupe([from_platform(_uid_from_url(d.get("_href", "")), d) for d in details])
    req = load_requirement(args.requirement)
    results = rank(cands, req)
    _print_board(results, req)

    store = Store(args.db or cfg.db_path)
    store.upsert_candidates(cands)
    store.save_scores(req.name, results)
    store.close()
    print(f"已写入 {args.db or cfg.db_path}（{len(cands)} 人）；今天已读 {usage.pages} 页")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    cands = dedupe(_load_mock()) if args.mock else load_store_candidates(args.db)
    if not cands:
        print("本地库里没有候选人。先跑 `bosscreen demo`，或用 --mock 打开示例数据。")
        return 1
    req = load_requirement(args.requirement)
    results = rank(cands, req)
    db_path = args.db or load_config().db_path

    def _save(req_obj, spec) -> None:
        """看板上改了需求就落库。失败时抛出去，让页面知道没存上。"""
        store = Store(db_path)
        try:
            store.save_requirement(req_obj.name, req_obj.name, spec)
            store.save_scores(req_obj.name, rank(cands, req_obj))
        finally:
            store.close()
        # 用户自己的需求文件跟着改；示例数据不动
        req_file = Path(args.requirement)
        if req_file.exists() and req_file.parent.name != "mock":
            try:
                req_file.write_text(
                    json.dumps(requirement_to_dict(req_obj), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                print(f"（需求文件没能回写：{exc}）", flush=True)
        print(f"需求已保存：{req_obj.name}", flush=True)

    httpd = serve(results, req, cands, host=args.host, port=args.port, on_save=_save)
    url = f"http://{args.host}:{args.port}/"
    print(f"看板已启动：{url}  （Ctrl+C 停止）")
    print(f"数据来源：{'mock 示例' if args.mock else args.db or load_config().db_path}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bosscreen", description="只读的招聘端简历筛选工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_demo = sub.add_parser("demo", help="用内置 mock 数据跑通完整链路")
    p_demo.add_argument("--db", default=None)
    p_demo.set_defaults(func=cmd_demo)

    p_score = sub.add_parser("score", help="对一份候选人 JSON 打分")
    p_score.add_argument("--candidates", required=True)
    p_score.add_argument("--requirement", required=True)
    p_score.add_argument("--json", action="store_true", help="同时输出 JSON")
    p_score.set_defaults(func=cmd_score)

    p_doc = sub.add_parser("doctor", help="自检：配置、依赖、浏览器与选择器")
    p_doc.add_argument("--ports", type=int, nargs="*", help="要探测的 Chrome 调试端口")
    p_doc.add_argument("--selectors", default=None, help="选择器配置路径")
    p_doc.set_defaults(func=cmd_doctor)

    p_col = sub.add_parser("collect", help="从浏览器读取投递列表（只读，不发送）")
    p_col.add_argument("--fixture", action="store_true", help="用 tests/fixtures 的样例页面验证链路")
    p_col.add_argument("--selectors", default=None, help="选择器配置路径")
    p_col.add_argument("--list-url", default=None, help="投递列表页 URL")
    p_col.add_argument("--port", type=int, default=None, help="Chrome 调试端口（默认自动找）")
    p_col.add_argument("--ports", type=int, nargs="*", default=None)
    p_col.add_argument("--limit", type=int, default=10, help="最多读几个人的在线简历")
    p_col.add_argument("--daily-limit", type=int, default=None, help="当天页面预算")
    p_col.add_argument("--usage", default=None, help="当日用量文件路径")
    p_col.add_argument("--force", action="store_true", help="允许用未校准的选择器")
    p_col.add_argument("--db", default=None)
    p_col.add_argument("--requirement", default=str(ROOT / "data" / "mock" / "requirement.json"))
    p_col.set_defaults(func=cmd_collect)

    p_serve = sub.add_parser("serve", help="启动本地看板（只读）")
    p_serve.add_argument("--mock", action="store_true", help="用内置示例数据")
    p_serve.add_argument("--db", default=None)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8686)
    p_serve.add_argument(
        "--requirement",
        default=str(ROOT / "data" / "mock" / "requirement.json"),
    )
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
