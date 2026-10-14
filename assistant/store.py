# -*- coding: utf-8 -*-
"""本地状态库：巡检增量对比的基线（已见条目）+ 事件时间线。

状态文件 store.json 与 config.json 同目录，结构：
{
  "version": 1,
  "last_scan": "2026-09-24T10:00:00",        # 最近一次巡检（任意范围）
  "last_full_scan": "2026-09-24T06:00:00",    # 最近一次全量基线
  "courses": {                                 # courseid → 该课基线
    "266328552": {
      "name": "数字图像处理",
      "homework_open": true,                   # 该课是否开放作业模块
      "seen_homework": ["HW1 xxx", ...],       # 见过的作业标题
      "seen_materials": [1360610675, ...],     # 见过的资料 data_id
      "active": true                           # 是否活跃课（在巡检范围内）
    }
  },
  "seen_notices": ["xxx", ...],                # 见过的通知 id
  "timeline": [                                # 事件流（新→旧，上限 500）
    {"time": "...", "kind": "homework|material|notice",
     "course": "...", "title": "...", "detail": "...",
     "tag": "作业|资料|通知|考试", "priority": "high|medium|low"}
  ]
}
"""
import json
import os
import threading
from datetime import datetime

TIMELINE_CAP = 500


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    """线程安全的本地状态库（巡检线程写，UI 线程读）。"""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict = {"version": 1, "courses": {},
                            "seen_notices": [], "timeline": []}
        self.load()

    # ---------- 基础 ----------

    def load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    d = json.load(f)
                # 兼容缺字段
                d.setdefault("courses", {})
                d.setdefault("seen_notices", [])
                d.setdefault("timeline", [])
                self._data = d
            except Exception:
                pass  # 状态损坏就从空基线重来，宁可重报不漏报

    def save(self) -> None:
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)

    # ---------- 巡检基线 ----------

    def course_state(self, cid: str, name: str = "") -> dict:
        """取课程基线（无则建空基线并标记为"新发现"，首见不告警）。
        返回副本——改作业开关用 set_homework_open，别戳返回值。"""
        with self._lock:
            cs = self._data["courses"].get(str(cid))
            if cs is None:
                cs = {"name": name, "homework_open": True,
                      "seen_homework": [], "seen_materials": [],
                      "active": True, "fresh": True}
                self._data["courses"][str(cid)] = cs
            elif name and cs.get("name") != name:
                cs["name"] = name
            import copy
            return copy.deepcopy(cs)

    def set_homework_open(self, cid: str, flag: bool) -> None:
        """课程作业模块开关（该课无 workEnc 时记下来跳过）。"""
        with self._lock:
            cs = self._data["courses"].get(str(cid))
            if cs is not None:
                cs["homework_open"] = flag

    def diff_homework(self, cid: str, titles: list[str]) -> list[str]:
        """返回新增的作业标题并更新基线；课程首见（fresh 标记）只建基线不报。"""
        with self._lock:
            cs = self._data["courses"].setdefault(str(cid), {
                "name": "", "homework_open": True, "seen_homework": [],
                "seen_materials": [], "active": True, "fresh": True})
            fresh = cs.get("fresh", False)
            seen = set(cs["seen_homework"])
            added = [t for t in titles if t not in seen]
            cs["seen_homework"] = list(seen | set(titles))[:500]
            return [] if fresh else added

    def diff_materials(self, cid: str, data_ids: list[int]) -> list[int]:
        """返回新增的资料 data_id 并更新基线；课程首见只建基线不报。"""
        with self._lock:
            cs = self._data["courses"].setdefault(str(cid), {
                "name": "", "homework_open": True, "seen_homework": [],
                "seen_materials": [], "active": True, "fresh": True})
            fresh = cs.get("fresh", False)
            seen = set(cs["seen_materials"])
            added = [i for i in data_ids if i not in seen]
            cs["seen_materials"] = list(seen | set(data_ids))[:2000]
            return [] if fresh else added

    def clear_fresh(self, cid: str) -> None:
        """课程基线建完（作业+资料都扫过一轮）后由 watcher 调用。"""
        with self._lock:
            cs = self._data["courses"].get(str(cid))
            if cs:
                cs.pop("fresh", None)

    def diff_notices(self, ids: list[str]) -> list[str]:
        with self._lock:
            seen = set(self._data["seen_notices"])
            fresh = not seen
            added = [i for i in ids if i not in seen]
            self._data["seen_notices"] = list(seen | set(ids))[:1000]
            return [] if fresh else added

    def diff_hw_status(self, cid: str, mapping: dict) -> list[tuple]:
        """作业状态基线：返回 [(title, old, new)]；首见（old=None）不算变化。

        瞬态空状态不入基线（页面解析抖动出空串会把真实状态挡在外面，
        那次出分就永久漏报）——留到下轮拿到真状态再记。
        """
        with self._lock:
            cs = self._data["courses"].setdefault(str(cid), {
                "name": "", "homework_open": True, "seen_homework": [],
                "seen_materials": [], "active": True, "fresh": True})
            st = cs.setdefault("hw_status", {})
            changes = []
            for t, s in mapping.items():
                s = s or ""
                if not s:
                    continue
                old = st.get(t)
                if old is not None and old != s:
                    changes.append((t, old, s))
                st[t] = s
            if len(st) > 500:
                cs["hw_status"] = dict(list(st.items())[-500:])
            return changes

    # ---------- 考试 / 任务点 / 通知缓存（巡检线程写，UI 读） ----------

    def diff_exams(self, keys: list[str]) -> list[str]:
        """新考试 key 列表；首见建基线不报（与通知同款策略）。"""
        with self._lock:
            seen = set(self._data.get("seen_exams", []))
            fresh = not seen
            added = [k for k in keys if k not in seen]
            self._data["seen_exams"] = list(seen | set(keys))[:200]
            return [] if fresh else added

    def set_exams(self, rows: list[dict]) -> None:
        """落库前 datetime → iso 串（json.dump 不认 datetime，直存会炸掉
        整个 store.save()——曾让持久化和退出全断，别再犯）。"""
        out = []
        for r in rows[:60]:
            r = dict(r)
            for k in ("start", "end"):
                v = r.get(k)
                r[k] = v.isoformat(timespec="seconds") if hasattr(v, "isoformat") else v
            out.append(r)
        with self._lock:
            self._data["exams_cache"] = {"rows": out,
                                         "saved_at": _now_iso()}

    def get_exams(self) -> list[dict]:
        with self._lock:
            return list((self._data.get("exams_cache") or {}).get("rows", []))

    def set_progress(self, rows: list[dict]) -> None:
        with self._lock:
            self._data["progress_cache"] = {"rows": rows[:80],
                                            "date": _now_iso()[:10]}

    def get_progress(self) -> list[dict]:
        with self._lock:
            return list((self._data.get("progress_cache") or {}).get("rows", []))

    @property
    def progress_date(self) -> str:
        """任务点缓存的刷新日（空=还没拉过；每天拉一次就够）。"""
        with self._lock:
            return (self._data.get("progress_cache") or {}).get("date", "")

    def set_notices(self, items: list) -> None:
        """通知缓存。真实字段是 sendTime/createrName/isread('0'/'1' 字符串)
        （_explore/notice_list.json 实测），不是直觉的 time/sender。"""
        rows = []
        for n in items[:40]:
            if not isinstance(n, dict):
                continue
            key = f"{n.get('uuid') or n.get('sendTime', '')}|{n.get('title', '')}"
            unread_server = str(n.get("isread", "0")) == "0"
            # sendTime 可能是毫秒时间戳（int）——str 化再切，别让一条
            # 脏数据炸掉整轮巡检的缓存写入
            stime = str(n.get("sendTime", "") or n.get("time", "") or "")
            if stime.isdigit() and len(stime) > 12:
                from datetime import datetime as _d
                stime = _d.fromtimestamp(int(stime) / 1000).strftime(
                    "%Y-%m-%d %H:%M")
            rows.append({
                "key": key,
                "title": n.get("title", ""),
                "sender": n.get("createrName", "") or n.get("sender", ""),
                "time": stime[:16].replace("T", " "),
                # 未读 = 服务端未读 且 本地没点开过（在这看通知不会改服务端态）
                "unread": unread_server and key not in self._notice_reads(),
                "content": (n.get("content", "") or "")[:500],
            })
        with self._lock:
            self._data["notices_cache"] = {"rows": rows, "saved_at": _now_iso()}

    def _notice_reads(self) -> set:
        with self._lock:
            return set(self._data.get("notice_reads", []))

    def mark_notice_read(self, key: str) -> None:
        """本地已读一条通知（点开看过就算，红点即消）。"""
        with self._lock:
            reads = self._data.setdefault("notice_reads", [])
            if key not in reads:
                reads.append(key)
            del reads[:-400]
            cache = self._data.get("notices_cache") or {}
            for r in cache.get("rows", []):
                if r.get("key") == key:
                    r["unread"] = False

    def get_notices(self) -> list[dict]:
        with self._lock:
            return list((self._data.get("notices_cache") or {}).get("rows", []))

    def mark_scan(self, full: bool) -> None:
        with self._lock:
            self._data["last_scan"] = _now_iso()
            if full:
                self._data["last_full_scan"] = _now_iso()

    @property
    def last_scan(self) -> str:
        with self._lock:
            return self._data.get("last_scan", "")

    @property
    def last_full_scan(self) -> str:
        with self._lock:
            return self._data.get("last_full_scan", "")

    def reminder_state(self) -> dict:
        """提醒状态读副本（UI 线程与巡检线程都会读，别给活字典）。"""
        with self._lock:
            import copy
            return copy.deepcopy(self._data.get("reminder_state", {}))

    def mark_reminder(self, sid: str, milestone: str) -> None:
        """记里程碑（锁内写；重复记幂等）。"""
        with self._lock:
            st = self._data.setdefault("reminder_state", {})
            lst = st.setdefault(sid, [])
            if milestone not in lst:
                lst.append(milestone)
            if len(lst) > 8:
                st[sid] = lst[-8:]

    def set_reminder(self, key: str, val) -> None:
        with self._lock:
            self._data.setdefault("reminder_state", {})[key] = val

    def trim_reminders(self, prefix: str, keep_prefix: str) -> None:
        """清掉 prefix 开头但不是 keep_prefix 的旧记录（跨线程安全）。"""
        with self._lock:
            st = self._data.get("reminder_state", {})
            for k in [k for k in st
                      if k.startswith(prefix) and not k.startswith(keep_prefix)]:
                st.pop(k)

    # ---------- 已读状态（未读角标） ----------

    def mark_read(self) -> None:
        """用户看了动态 → 此前的高优事件全部算已读。"""
        with self._lock:
            self._data["last_read"] = _now_iso()

    def unread_count(self) -> int:
        with self._lock:
            last_read = self._data.get("last_read", "")
            # 只统计巡检发现的新东西；自家产生的提醒/预备铃不算"新动态"
            # （否则不看动态页时角标会被系统自己持续抬高，Judge B #2）
            return sum(1 for e in self._data["timeline"]
                       if e.get("priority") == "high"
                       and e.get("kind") not in ("reminder", "classup")
                       and (not last_read or (e.get("time", "") > last_read)))

    def set_active(self, active_courseids: set[str]) -> None:
        """按当前学期课表标记活跃课程（入参为纯 courseid 集合）。

        store 键是 courseid|clazzid 复合键，这里按前缀匹配：
        课表里出现的课程全部标活跃；历史课退出巡检范围。
        """
        with self._lock:
            for cid_key, cs in self._data["courses"].items():
                cs["active"] = cid_key.split("|")[0] in active_courseids

    def active_courses(self) -> list[tuple[str, dict]]:
        with self._lock:
            return [(cid, dict(cs)) for cid, cs in self._data["courses"].items()
                    if cs.get("active")]


    # ---------- 课表持久缓存（启动秒开，后台巡检时刷新） ----------

    def get_schedule(self) -> dict:
        with self._lock:
            return self._data.get("schedule_cache") or {}

    def set_schedule(self, sched: dict) -> None:
        with self._lock:
            self._data["schedule_cache"] = {
                "curriculum": sched.get("curriculum", {}),
                "lessons": sched.get("lessons", []),
                "saved_at": _now_iso(),
            }

    # ---------- DDL 持久缓存（巡检线程写，小窗作业页读） ----------

    def set_deadlines(self, items: list[dict]) -> None:
        rows = []
        for r in items[:60]:
            dt_ = r.get("deadline_dt")
            rows.append({"course": r.get("course", ""),
                         "title": r.get("title", ""),
                         "status": r.get("status", ""),
                         "url": r.get("url", "") or "",
                         "courseUrl": r.get("courseUrl", "") or "",
                         "deadline": r.get("deadline"),
                         "deadline_iso": dt_.isoformat() if dt_ else None})
        with self._lock:
            self._data["deadlines_cache"] = {"items": rows,
                                             "saved_at": _now_iso()}

    def get_deadlines(self) -> list[dict]:
        with self._lock:
            cache = self._data.get("deadlines_cache") or {}
        return list(cache.get("items", []))

    # ---------- 作业忽略（"已线下交/不打算交"的手动排除） ----------

    @staticmethod
    def hw_key(course: str, title: str, url: str = "") -> str:
        """忽略键含作业 url：同课同名作业不连坐（url 空退化到标题）。"""
        return f"{course}|{url}|{title}"

    def ignore_hw(self, course: str, title: str, url: str = "") -> None:
        with self._lock:
            ig = self._data.setdefault("hw_ignores", [])
            k = self.hw_key(course, title, url)
            if k not in ig:
                ig.append(k)
            del ig[:-200]

    def unignore_hw_all(self) -> int:
        """清空忽略名单，返回清掉几条。"""
        with self._lock:
            n = len(self._data.get("hw_ignores", []))
            self._data["hw_ignores"] = []
            return n

    def hw_ignores(self) -> list[str]:
        with self._lock:
            return list(self._data.get("hw_ignores", []))

    # ---------- 时间线与补弹队列 ----------

    def append_timeline(self, evt: dict) -> None:
        evt = dict(evt)
        evt.setdefault("time", _now_iso())
        with self._lock:
            tl = self._data["timeline"]
            # 去重：同 kind+course+title 一天内不重复入线（不含 course 时
            # 两门课同日传同名文件，第二条会被吞）
            if any(e.get("kind") == evt.get("kind") and
                   e.get("course") == evt.get("course") and
                   e.get("title") == evt.get("title") and
                   e.get("time", "")[:10] == evt["time"][:10] for e in tl[:50]):
                return
            tl.insert(0, evt)
            del tl[TIMELINE_CAP:]
            self._data["timeline"] = tl

    def push_pending(self, evt: dict) -> None:
        """上课/免打扰期间静默的提醒入补弹队列（下课补弹）。"""
        with self._lock:
            q = self._data.setdefault("pending_silent", [])
            if len(q) < 20:
                q.append(dict(evt))

    def pop_pending(self) -> list[dict]:
        """取走全部待补弹事件（调用方负责在合适时机 Toast）。"""
        with self._lock:
            q = self._data.get("pending_silent", [])
            self._data["pending_silent"] = []
            return q

    def timeline(self, limit: int = 100) -> list[dict]:
        # 按事件自身时间倒排（通知事件带 sendTime 后，插入序≠时间序）。
        # 归一化分隔符再比：老条目是 isoformat 的 "T"、新条目是空格，
        # 裸字符串比较同一天会因 T>空格 错序
        def _key(e):
            return str(e.get("time", "")).replace("T", " ")
        with self._lock:
            tl = sorted(self._data["timeline"], key=_key, reverse=True)
            return tl[:limit]
