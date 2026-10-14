# -*- coding: utf-8 -*-
"""一次性清洗 store.json 时间线：09-30 首轮通知扫描把接口返回的
"最近100条"（含 6/7 月旧学期通知）全灌进了动态页，且时间戳全是
扫描时刻 2026-09-30T12:23:16。watcher 已修（sendTime + 14 天窗口），
这里把存量脏数据删掉。备份 → store.json.pre_clean_1014.bak
用法：python tools/clean_timeline_1014.py
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "store.json"
BAD_BATCH = "2026-09-30T12:23"   # 污染批次签名（kind=notice + 该时间戳）


def main() -> None:
    data = json.loads(STORE.read_text(encoding="utf-8"))
    tl = data.get("timeline", [])
    before = len(tl)
    kept = [e for e in tl
            if not (e.get("kind") == "notice"
                    and str(e.get("time", "")).startswith(BAD_BATCH))]
    dropped = before - len(kept)
    if dropped:
        shutil.copy2(STORE, STORE.with_suffix(".json.pre_clean_1014.bak"))
        data["timeline"] = kept
        STORE.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    print(f"timeline: {before} -> {len(kept)}（删除旧学期通知事件 {dropped} 条）")
    for e in kept[:10]:
        print("  保留:", e.get("kind"), e.get("time"), str(e.get("title"))[:30])


if __name__ == "__main__":
    main()
