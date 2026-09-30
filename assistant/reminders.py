# -*- coding: utf-8 -*-
"""DDL 渐进提醒引擎：D-3 首次提及 → D-1 正式提醒 → H-4 升级 → H-1 紧急。

人性化规则（调研共识）：
  已完成/待批阅的作业永不提醒；同一作业每个里程碑只提醒一次（共 4 次上限）；
  免打扰时段（默认 23:00–7:30）不弹横幅，只进时间线；
  上课时段静默（课表反哺）：正在上课时降级为时间线，下课补弹一次。
"""
import logging
from datetime import datetime, timedelta

log = logging.getLogger("remind")

# 里程碑：(key, 距截止的阈值, 文案模板)
MILESTONES = [
    ("D-3", timedelta(days=3), "{course}《{title}》3 天内截止"),
    ("D-1", timedelta(days=1), "{course}《{title}》24 小时内截止，别忘了"),
    ("H-4", timedelta(hours=4), "{course}《{title}》4 小时内截止"),
    ("H-1", timedelta(hours=1), "⚠ {course}《{title}》1 小时内截止！"),
]


def in_class_now(rows: list[dict], now: datetime) -> bool:
    """课表里当前是否正在上课（rows 来自 lesson_rows，含 start/end）。"""
    return any(r["start"] <= now <= r["end"] for r in rows)


def in_dnd(now: datetime, dnd: str) -> bool:
    """免打扰时段判断，格式 "23:00-07:30"，跨零点。空串=关闭。"""
    if not dnd or "-" not in dnd:
        return False
    try:
        a, b = dnd.split("-")
        ah, am = map(int, a.split(":"))
        bh, bm = map(int, b.split(":"))
        cur = now.hour * 60 + now.minute
        s, e = ah * 60 + am, bh * 60 + bm
        return s <= cur < e if s <= e else (cur >= s or cur < e)
    except Exception:
        return False


class ReminderEngine:
    """每轮巡检后跑一次 check()，产出该弹的提醒事件。"""

    def __init__(self, store, settings: dict):
        self.store = store
        self.settings = settings

    def check(self, deadline_overview: dict, rows: list[dict],
              now: datetime | None = None) -> list[dict]:
        """deadline_overview = client.fetch_deadline_overview() 的结果。"""
        now = now or datetime.now()
        dnd = in_dnd(now, self.settings.get("dnd", "23:00-07:30"))
        in_class = in_class_now(rows, now)
        fired: list[dict] = []

        for hw in deadline_overview.get("items", []):
            ddl = hw.get("deadline_dt")   # datetime，由 snapshot 层解析好
            if ddl is None or hw.get("done"):
                continue
            remaining = ddl - now
            if remaining <= timedelta(0):
                continue   # 已过期：逾期归档不提醒
            # 从最紧急档向上匹配：跳级（如直接剩 3 小时）时命中最紧档，
            # 更远的档视为已错过一并标记，防止日后倒回去补弹旧文案
            hit = None
            for key, threshold, tpl in reversed(MILESTONES):
                if remaining <= threshold and not self._already(hw, key):
                    hit = (key, tpl)
                    break
            if hit is None:
                continue
            key, tpl = hit
            self._mark(hw, key)   # 命中档先记上
            # 跳级时把比命档更远的档一并标记（视为已错过，不倒回去补弹）
            hit_threshold = dict((m[0], m[1]) for m in MILESTONES)[key]
            for k2, t2, _ in MILESTONES:
                if t2 > hit_threshold and not self._already(hw, k2):
                    self._mark(hw, k2)
            evt = {"kind": "reminder", "course": hw.get("course", ""),
                   "title": hw.get("title", ""), "detail": "",
                   "tag": "截止", "priority": "high",
                   "reason": key}
            evt["silent"] = dnd or in_class   # 免打扰/上课中 → 只进时间线
            evt["text"] = tpl.format(course=hw.get("course", ""),
                                     title=hw.get("title", ""))
            fired.append(evt)
        return fired

    # ---------- 预备铃（Class Widgets 明星功能：上课前 N 分钟提醒） ----------

    def check_classup(self, rows: list[dict], now: datetime | None = None,
                      ) -> list[dict]:
        """60s 定时器喂当日课程行；进入 lead 窗口的课各提醒一次。

        不同于 DDL 提醒：上课预备铃不受"上课中静默"约束（连堂课正是
        下节要上的提醒最有用的时候）；免打扰时段直接丢弃（补弹无意义）。
        """
        now = now or datetime.now()
        lead = max(1, int(self.settings.get("class_lead_min", 10)))
        dnd = in_dnd(now, self.settings.get("dnd", "23:00-07:30"))
        fired: list[dict] = []
        today_prefix = f"classup:{now:%m-%d}"
        # 顺手清掉非今天的预备铃记录（key 自带日期，旧记录无保留价值）
        self.store.trim_reminders("classup:", today_prefix)
        if dnd:
            return []
        st = self.store.reminder_state()   # 读副本
        for r in rows:
            delta = (r["start"] - now).total_seconds()
            if not (0 < delta <= lead * 60):
                continue
            key = f"{today_prefix}:{r['start']:%H:%M}:{r['name']}"
            if key in st:
                continue
            self.store.set_reminder(key, now.isoformat(timespec="seconds"))
            loc = r.get("location") or ""
            evt = {"kind": "classup", "course": r.get("name", ""),
                   "title": f"将在 {r['start']:%H:%M} 开始",
                   "detail": loc, "tag": "上课", "priority": "high",
                   "text": f"{lead} 分钟后上《{r.get('name', '')}》"
                           + (f" · {loc}" if loc else "")}
            fired.append(evt)
        return fired

    # ---------- 状态 ----------

    def _state(self) -> dict:
        return self.store.reminder_state()

    def _already(self, hw: dict, key: str) -> bool:
        st = self._state().get(self._hw_id(hw), [])
        return key in st

    def _mark(self, hw: dict, key: str) -> None:
        self.store.mark_reminder(self._hw_id(hw), key)

    @staticmethod
    def _hw_id(hw: dict) -> str:
        return f"{hw.get('course', '')}|{hw.get('title', '')}"
