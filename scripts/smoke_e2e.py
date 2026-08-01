"""
E2E 全链路冒烟脚本 — 6 条主链路真实服务验证

用法:
    python scripts/smoke_e2e.py              # 全链路（含真实 LLM：ingest/chat）
    python scripts/smoke_e2e.py --no-llm     # 跳过真实 LLM 链路（仅接口链路）
    python scripts/smoke_e2e.py --port 8799  # 自定义端口

隔离：启动独立 uvicorn 实例（LLM_WIKI_DATA_DIR=临时目录），不碰生产数据。
链路：
    L0 健康检查 → L1 导入（上传→队列→页面生成）→ L2 浏览（tree→预览→预检）
    → L3 搜索/Lint → L4 图谱 → L5 Chat SSE → L6 管理（设置/日志/前端日志/reset-data）
退出码：0 = 全过；1 = 有失败。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

# Windows GBK 控制台无法打印 emoji，强制 UTF-8 输出
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SMOKE_MD = """---
title: 冒烟测试文档
tags: [smoke]
---

# 冒烟测试

这是 E2E 冒烟测试用的源文档，包含 Python 与 FastAPI 两个概念，
用于验证导入链路与知识图谱生成。
"""


class SmokeReport:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "ok": ok, "detail": detail})
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))

    def summary(self) -> int:
        passed = sum(1 for c in self.checks if c["ok"])
        failed = len(self.checks) - passed
        print(f"\n=== 冒烟结果: {passed}/{len(self.checks)} 通过 ===")
        if failed:
            print("失败项:")
            for c in self.checks:
                if not c["ok"]:
                    print(f"  ❌ {c['name']}: {c['detail']}")
        return 0 if failed == 0 else 1


def wait_health(client: httpx.Client, port: int, timeout: float = 90) -> bool:
    """等待服务健康检查通过"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = client.get(f"http://127.0.0.1:{port}/health", timeout=3)
            if r.status_code == 200 and r.json().get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def run_l0_health(client: httpx.Client, port: int, rep: SmokeReport) -> None:
    """L0 健康检查"""
    r = client.get(f"http://127.0.0.1:{port}/health")
    data = r.json()
    rep.check("L0 健康检查 /health", r.status_code == 200 and data["status"] == "ok",
              f"pages={data.get('total_pages')} graph={data.get('graph_nodes')}")

    r = client.get(f"http://127.0.0.1:{port}/", follow_redirects=False)
    rep.check("L0 根路径重定向 / → /wiki", r.status_code in (302, 307),
              f"status={r.status_code} location={r.headers.get('location', '')}")


def run_l1_ingest(client: httpx.Client, port: int, rep: SmokeReport, data_dir: str, no_llm: bool) -> None:
    """L1 导入链路：上传 → 入队 → worker 消费 → 页面生成"""
    sources = Path(data_dir) / "raw" / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    (sources / "smoke.md").write_text(SMOKE_MD, encoding="utf-8", newline="\n")

    # 上传（新文件 → 入队）
    r = client.post(f"http://127.0.0.1:{port}/v1/ingest/upload",
                    files={"f0": ("smoke.md", SMOKE_MD.encode("utf-8"), "text/markdown")})
    data = r.json()
    rep.check("L1.1 上传入队 /v1/ingest/upload",
              r.status_code == 200 and data.get("saved", 0) >= 1 and data.get("enqueued", 0) >= 1,
              f"saved={data.get('saved')} enqueued={data.get('enqueued')}")

    # 队列状态流转：等待 worker 消费（最多 90s；无 LLM 时任务会转 failed，链路状态机仍算通）
    deadline = time.time() + 90
    queue_state = None
    while time.time() < deadline:
        r = client.get(f"http://127.0.0.1:{port}/v1/ingest/queue/status")
        queue_state = r.json()
        done = queue_state.get("done", 0) + queue_state.get("failed", 0) + queue_state.get("cancelled", 0)
        if done >= 1:
            break
        time.sleep(2)
    rep.check("L1.2 队列消费 /v1/ingest/queue/status",
              queue_state is not None and queue_state.get("done", 0) + queue_state.get("failed", 0) >= 1,
              f"state={queue_state}")

    # 页面生成（真实 LLM；无 LLM 模式不要求页面存在）
    r = client.get(f"http://127.0.0.1:{port}/v1/pages")
    pages = r.json().get("pages", [])
    rep.check("L1.3 页面生成 /v1/pages",
              r.status_code == 200 and (len(pages) > 0 or no_llm),
              f"pages={len(pages)}" + ("（no-llm 模式不要求）" if no_llm else ""))


def run_l2_browse(client: httpx.Client, port: int, rep: SmokeReport) -> None:
    """L2 浏览链路：tree 前缀契约 → file-content 预览 → check-changed 预检"""
    r = client.get(f"http://127.0.0.1:{port}/v1/sources/tree")
    tree = r.json().get("tree", [])
    paths = []

    def walk(items):
        for item in items:
            paths.append(item["path"])
            walk(item.get("children", []))

    walk(tree)
    rep.check("L2.1 文件树前缀契约 /v1/sources/tree",
              r.status_code == 200 and any(p.startswith("raw/sources/") for p in paths),
              f"files={len(paths)}")

    r = client.get(f"http://127.0.0.1:{port}/v1/file-content", params={"path": "raw/sources/smoke.md"})
    data = r.json()
    rep.check("L2.2 文件预览 /v1/file-content",
              r.status_code == 200 and "冒烟测试" in data.get("content", ""),
              f"size={data.get('size')}")

    r = client.get(f"http://127.0.0.1:{port}/v1/sources/check-changed", params={"path": "raw/sources/smoke.md"})
    rep.check("L2.3 提取预检 /v1/sources/check-changed",
              r.status_code == 200 and "changed" in r.json(),
              f"changed={r.json().get('changed')}")

    r = client.get(f"http://127.0.0.1:{port}/v1/sources")
    rep.check("L2.4 资料源分页 /v1/sources", r.status_code == 200, f"total={r.json().get('total')}")


def run_l3_search(client: httpx.Client, port: int, rep: SmokeReport) -> None:
    """L3 搜索 + Lint"""
    r = client.post(f"http://127.0.0.1:{port}/v1/search",
                    json={"query": "Python", "k": 5, "method": "bm25"})
    data = r.json()
    rep.check("L3.1 BM25 搜索 /v1/search",
              r.status_code == 200 and isinstance(data.get("results"), list),
              f"results={len(data.get('results', []))} method={data.get('method')}")

    r = client.get(f"http://127.0.0.1:{port}/v1/lint?semantic=false")
    rep.check("L3.2 知识库体检 /v1/lint", r.status_code == 200,
              f"health_score={r.json().get('health_score')}")


def run_l4_graph(client: httpx.Client, port: int, rep: SmokeReport) -> None:
    """L4 图谱链路"""
    r = client.get(f"http://127.0.0.1:{port}/v1/graph")
    data = r.json()
    rep.check("L4.1 图谱数据 /v1/graph", r.status_code == 200,
              f"nodes={len(data.get('nodes', []))} edges={len(data.get('edges', []))}")

    r = client.get(f"http://127.0.0.1:{port}/v1/communities")
    rep.check("L4.2 社区发现 /v1/communities", r.status_code == 200,
              f"communities={len(r.json().get('communities', {}))}")

    r = client.get(f"http://127.0.0.1:{port}/v1/insights")
    rep.check("L4.3 洞察 /v1/insights", r.status_code == 200,
              f"surprising={len(r.json().get('surprising', []))} gaps={len(r.json().get('gaps', []))}")


def run_l5_chat(client: httpx.Client, port: int, rep: SmokeReport, no_llm: bool) -> None:
    """L5 Chat SSE 链路（真实 LLM；no-llm 模式仅验证接口可用性）"""
    r = client.get(f"http://127.0.0.1:{port}/v1/agent/models")
    rep.check("L5.1 模型列表 /v1/agent/models", r.status_code == 200,
              f"models={len(r.json().get('models', []))}")

    thread_id = str(uuid.uuid4())
    question = "你好，请用一句话介绍你自己。" if not no_llm else "ping"
    with client.stream("POST", f"http://127.0.0.1:{port}/v1/agent/chat/session",
                       json={"content": question, "thread_id": thread_id}) as resp:
        if no_llm:
            rep.check("L5.2 Chat 会话接口可达", resp.status_code in (200, 400, 422),
                      f"status={resp.status_code}")
            return
        events = []
        try:
            for line in resp.iter_lines():
                if line:
                    events.append(line)
        except Exception as exc:
            rep.check(f"L5.2 Chat SSE 流（异常）", False, str(exc))
            return
        has_data = any("data:" in e or "event:" in e for e in events)
        rep.check("L5.2 Chat SSE 流式对话 /v1/agent/chat/session",
                  resp.status_code == 200 and has_data,
                  f"status={resp.status_code} events={len(events)}")


def run_l6_admin(client: httpx.Client, port: int, rep: SmokeReport) -> None:
    """L6 管理链路：设置 / 日志 / 前端日志 / reset-data"""
    r = client.get(f"http://127.0.0.1:{port}/v1/settings")
    rep.check("L6.1 系统设置 /v1/settings", r.status_code == 200,
              f"provider={r.json().get('llm_provider')}")

    r = client.get(f"http://127.0.0.1:{port}/v1/logs/tail", params={"source": "backend", "lines": 100})
    rep.check("L6.2 后端日志 /v1/logs/tail", r.status_code == 200 and len(r.json().get("content", "")) > 0,
              f"chars={len(r.json().get('content', ''))}")

    r = client.post(f"http://127.0.0.1:{port}/v1/frontend/logs",
                    json={"entries": [{"level": "info", "source": "smoke", "message": "冒烟测试上报", "ts": 0}]})
    rep.check("L6.3 前端日志上报 /v1/frontend/logs",
              r.status_code == 200 and r.json().get("written", 0) == 1)

    r = client.get(f"http://127.0.0.1:{port}/v1/logs/tail", params={"source": "frontend", "lines": 50})
    rep.check("L6.4 前端日志回读", r.status_code == 200 and "冒烟测试上报" in r.json().get("content", ""))

    # reset-data：隔离目录，安全执行；清空后验证数据归零
    r = client.post(f"http://127.0.0.1:{port}/v1/system/reset-data")
    rep.check("L6.5 数据重置 /v1/system/reset-data", r.status_code == 200,
              r.json().get("message", ""))

    r = client.get(f"http://127.0.0.1:{port}/v1/pages")
    pages = r.json().get("pages", [])
    rep.check("L6.6 重置后数据清空 /v1/pages", r.status_code == 200 and len(pages) == 0,
              f"pages={len(pages)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM Wiki E2E 冒烟")
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--no-llm", action="store_true", help="跳过真实 LLM 链路")
    parser.add_argument("--keep", action="store_true", help="保留隔离数据目录与进程（调试）")
    args = parser.parse_args()

    data_dir = tempfile.mkdtemp(prefix="llm-wiki-smoke-")
    print(f"隔离数据目录: {data_dir}")
    print(f"端口: {args.port} | LLM 链路: {'跳过' if args.no_llm else '真实执行'}")

    # LOG_FILE 默认覆盖：.env 的 LOG_FILE=logs/wiki.log 是相对 CWD 的，
    # 在隔离数据目录下必须指向 data_dir/logs/wiki.log（否则日志写项目根）
    env = {
        **os.environ,
        "LLM_WIKI_DATA_DIR": data_dir,
        "LOG_FILE": os.path.join(data_dir, "logs", "wiki.log"),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.main:app", "--port", str(args.port), "--log-level", "warning"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    rep = SmokeReport()
    try:
        with httpx.Client(timeout=30) as client:
            if not wait_health(client, args.port):
                print("❌ 服务启动超时（90s），冒烟终止")
                proc.terminate()
                return 1

            run_l0_health(client, args.port, rep)
            run_l1_ingest(client, args.port, rep, data_dir, args.no_llm)
            run_l2_browse(client, args.port, rep)
            run_l3_search(client, args.port, rep)
            run_l4_graph(client, args.port, rep)
            run_l5_chat(client, args.port, rep, args.no_llm)
            run_l6_admin(client, args.port, rep)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    if not args.keep:
        import shutil
        shutil.rmtree(data_dir, ignore_errors=True)

    # 落盘结果 JSON（供报告引用）
    report_path = Path("docs/testing/reports/phase-4-e2e-results.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(
        {"no_llm": args.no_llm, "checks": rep.checks,
         "passed": sum(1 for c in rep.checks if c["ok"]),
         "total": len(rep.checks)},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已落盘: {report_path}")

    return rep.summary()


if __name__ == "__main__":
    sys.exit(main())
