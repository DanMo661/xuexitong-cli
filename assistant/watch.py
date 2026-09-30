# -*- coding: utf-8 -*-
"""巡检 CLI：python -m assistant.watch [--once] [--full] [--interval N] [--quiet]

headless 模式：不依赖 GUI，打印每轮事件，供测试与手动触发。
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# 兼容从仓库根直接运行（python -m assistant.watch）
from assistant.paths import ROOT  # noqa: E402
sys.path.insert(0, str(ROOT))

from assistant.notify import Notifier          # noqa: E402
from assistant.store import Store              # noqa: E402
from assistant.watcher import Watcher          # noqa: E402
from xuexitong_mcp.client import ChaoxingClient  # noqa: E402


def load_settings() -> dict:
    p = ROOT / "settings.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def fmt_evt(e: dict) -> str:
    star = {"high": "‼", "medium": "·", "low": " "}[e.get("priority", "low")]
    return f"{star} [{e.get('tag')}] {e.get('course')} | {e.get('title')}"


def main() -> int:
    ap = argparse.ArgumentParser(description="学习通巡检（headless）")
    ap.add_argument("--once", action="store_true", help="只跑一轮")
    ap.add_argument("--full", action="store_true", help="全量基线扫")
    ap.add_argument("--interval", type=int, default=30, help="循环间隔分钟")
    ap.add_argument("--quiet", action="store_true", help="不弹 Toast")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    settings = load_settings()
    if args.quiet:
        settings["toast_enabled"] = False
    store = Store(str(ROOT / "store.json"))
    client = ChaoxingClient()
    notifier = Notifier(settings)
    w = Watcher(client, store)

    def on_events(events):
        if not args.quiet:
            notifier.notify_events(events)
        for e in events:
            print(fmt_evt(e), flush=True)

    w.on_events = on_events

    while True:
        print(f"— 巡检开始（{'全量' if args.full else '常规'}）", flush=True)
        try:
            events = w.scan_once(full=args.full)
        except Exception as e:
            print(f"— 巡检失败：{e}（网络抖动可重试）", flush=True)
            events = []
        print(f"— 本轮事件 {len(events)} 条；last_scan={store.last_scan}", flush=True)
        store.save()
        if args.once:
            return 0
        time.sleep(max(5, args.interval) * 60)


if __name__ == "__main__":
    raise SystemExit(main())
