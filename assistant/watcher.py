# -*- coding: utf-8 -*-
"""巡检引擎：定时扫学习通 → 增量对比 → 分级事件。

扫描范围策略（控请求量，做温和人类）：
  全量基线扫：所有课程（建基线用，每天最多 1 次）
  常规轮巡：只扫"活跃课程"= 当前学期课表里的课 ∪ 通知中心
  每课每轮请求：作业列表 1 次 + 资料区递归 1~3 次
调度由上层（app.py 的 QTimer 或 CLI while）驱动，本模块只做一轮。
"""
import logging
import time

from .classify import (classify_exam, classify_homework, classify_hw_status,
                       classify_material, classify_notice,
                       material_is_homeworkish, probe_dir)
from .snapshot import parse_exam_rows
from .store import Store

log = logging.getLogger("watcher")

def pretty_name(raw: str) -> str:
    """清理学习通文件名的 URL 编码残留（+ 和 %2B 等）。"""
    import urllib.parse
    n = raw.replace("+", " ")
    try:
        n = urllib.parse.unquote(n)
    except Exception:
        pass
    return " ".join(n.split())


HOMEWORK_CLOSED_MARK = "作业签名"   # fetch_homework 对未开放课程的报错特征


class Event(dict):
    """巡检产物：一条值得用户知道的变化。"""

    @property
    def high(self) -> bool:
        return self.get("priority") == "high"


class Watcher:
    """一轮巡检 = scan_once()；事件通过 on_events 回调送出。"""

    def __init__(self, client, store: Store, probe_download: bool = True,
                 max_courses_per_scan: int = 40):
        self.client = client          # xuexitong_mcp.client.ChaoxingClient
        self.store = store
        self.probe_download = probe_download   # medium 资料是否下载读内容确认
        self.max_courses = max_courses_per_scan
        self.on_events = None         # callable(list[Event])，UI/CLI 注入

    # ---------- 主流程 ----------

    def scan_once(self, full: bool = False,
                  stop_check=None) -> list[Event]:
        """跑一轮。full=True 扫全部课程（建基线/每日重扫），False 只扫活跃课。

        stop_check() 返回 True 时尽快收尾退出（用户退出程序时用）。
        """
        events: list[Event] = []
        try:
            self.client.ensure_login()
        except Exception as e:
            log.warning("登录保持失败：%s", e)
            return events

        # 课表活跃课程集合（顺带刷新课表缓存，UI 也能用）
        active_cids: set[str] = set()
        try:
            sched = self.client.fetch_schedule_full(refresh=False)
            if hasattr(self.store, "set_schedule") and sched.get("lessons"):
                self.store.set_schedule(sched)   # 回写落盘缓存供下次秒开
            for ls in sched.get("lessons", []):
                active_cids.add(str(ls.get("courseid") or ls.get("courseId") or ""))
        except Exception as e:
            log.warning("课表获取失败，本轮按已存活跃集扫：%s", e)
        active_cids.discard("")
        if active_cids:
            self.store.set_active(active_cids)

        courses = self.client.fetch_courses()
        if full:
            targets = courses
        else:
            active_keys = {k for k, _ in self.store.active_courses()}
            targets = [c for c in courses
                       if any(k.split("|")[0] == str(c["courseid"])
                              for k in active_keys)][:self.max_courses]

        for c in targets:
            if stop_check and stop_check():
                log.info("收到退出请求，本轮扫描提前收尾")
                break
            try:
                events += self._scan_course(c)
            except Exception as e:
                msg = str(e)
                if HOMEWORK_CLOSED_MARK in msg:
                    self.store.set_homework_open(self._cid(c), False)
                    continue
                log.warning("课程 %s 扫描失败：%s", c.get("name"), msg)
            time.sleep(0.8)   # 课间小歇，别像机器

        events += self._scan_exams()
        events += self._scan_notices()
        # 任务点总览只在每日全量基线扫时做（逐课查询重），常规轮巡不碰
        if full:
            self.refresh_progress(stop_check, courses)
        self.store.mark_scan(full=full)
        if events and self.on_events:
            try:
                self.on_events(events)
            except Exception as e:
                log.warning("事件回调失败：%s", e)
        return events

    @staticmethod
    def _cid(c: dict) -> str:
        """store 主键：courseid|clazzid（同一课程两个班各自独立基线）。"""
        return f"{c.get('courseid', '')}|{c.get('clazzid', '')}"

    # ---------- 单课扫描 ----------

    def _scan_course(self, c: dict) -> list[Event]:
        events: list[Event] = []
        cid, cname = self._cid(c), c.get("name", "")

        # 1) 作业列表 diff（新增 + 状态变化→出分/打回）
        hw_state = self.store.course_state(cid, cname)
        if hw_state.get("homework_open", True):
            try:
                hw = self.client.fetch_homework(c)
                items = hw.get("items", [])
                titles = [it.get("title", "") for it in items]
                for t in self.store.diff_homework(cid, titles):
                    if not t:
                        continue
                    verdict = classify_homework(t, "")
                    events.append(self._evt("homework", cname, t, verdict))
                for title, old, new in self.store.diff_hw_status(
                        cid, {it.get("title", ""): it.get("status", "")
                              for it in items}):
                    verdict = classify_hw_status(old, new)
                    if not verdict:
                        continue
                    detail = f"{old} → {new}"
                    if verdict["tag"] == "出分":
                        detail = self._score_detail(c, hw, title) or detail
                    events.append(self._evt("hwscore", cname, title, verdict,
                                            detail=detail))
            except Exception as e:
                if HOMEWORK_CLOSED_MARK in str(e):
                    self.store.set_homework_open(cid, False)
                    hw_state["homework_open"] = False
                else:
                    raise

        # 2) 资料区 diff（depth 2 递归，空关键词=全量）
        mats: list[dict] = []
        mats_ok = True
        try:
            mats = self.client.fetch_materials_recursive(c, "", max_depth=2)
        except Exception as e:
            mats_ok = False
            log.warning("资料区读取失败 %s：%s", cname, e)
        by_id = {m["data_id"]: m for m in mats}
        added_ids = self.store.diff_materials(cid, [m["data_id"] for m in mats])
        for did in added_ids:
            m = by_id.get(did, {})
            name = pretty_name(m.get("path") or m.get("name") or f"新文件#{did}")
            verdict = classify_material(name, cname)
            events.append(self._evt("material", cname, name, verdict,
                                    data_id=did, course_obj=c))
        # 首见课基线只在作业+资料两处都真正读到后才清，首轮网络抖动不清，
        # 下轮重试（否则空 seen + 已清 fresh = 下轮全部文件误报）
        if mats_ok:
            self.store.clear_fresh(cid)
        return events

    # ---------- 通知中心 ----------

    def _scan_notices(self) -> list[Event]:
        events: list[Event] = []
        try:
            items = self.client.fetch_notices(limit=30)
        except Exception as e:
            log.warning("通知拉取失败：%s", e)
            return events
        if not isinstance(items, list):
            items = items.get("items", []) if isinstance(items, dict) else []
        self.store.set_notices(items)   # 通知 tab 的缓存（读失败保旧）
        by_key: dict[str, dict] = {}
        for n in items:
            # 真实字段 sendTime/createrName（_explore/notice_list.json 实测），
            # time/sender 不存在——用错字段 diff key 会退化成纯标题去重
            key = f"{n.get('uuid') or n.get('sendTime', '')}|{n.get('title', '')}"
            by_key[key] = n
        for key in self.store.diff_notices(list(by_key.keys())):
            n = by_key.get(key, {})
            sender = n.get("createrName", "") or n.get("sender", "")
            verdict = classify_notice(n.get("title", ""), sender,
                                      n.get("content", ""))
            events.append(self._evt("notice", sender,
                                    n.get("title", key), verdict,
                                    detail=(n.get("content", "") or "")[:160]))
        return events

    # ---------- 考试表 / 任务点 ----------

    def _scan_exams(self) -> list[Event]:
        """考试安排：每轮 1 个请求；新考试进事件（首见建基线不报）。"""
        try:
            parsed = parse_exam_rows(self.client.fetch_exams())
        except Exception as e:
            log.warning("考试表拉取失败：%s", e)
            return []
        self.store.set_exams(parsed)
        by_key = {f"{r['name']}|{r['start'].strftime('%Y-%m-%d %H:%M')}": r
                  for r in parsed}
        events: list[Event] = []
        for k in self.store.diff_exams(list(by_key.keys())):
            r = by_key.get(k)
            if not r:
                continue
            # title=考试名（时间线主行）；时间串进 detail，别倒挂
            events.append(self._evt(
                "exam", "考试安排", r["name"], classify_exam(r["name"]),
                detail=f"{r['start'].strftime('%m-%d %H:%M')} 开考 · "
                       f"{r['durationMin']}分钟"))
        return events

    def refresh_progress(self, stop_check=None, courses=None) -> bool:
        """任务点总览：逐课查询重（每课 1-2 请求），限速 0.4s/课。

        只在每日全量扫或用户手动刷新时跑；courses 缺省扫全部历史课
        （网课不在课表里，恰好是任务点最重的）。中断（退出程序）时
        不写缓存——半份数据会把"今天已刷"记死，整天不再重试。
        返回是否完整写入。
        """
        from datetime import datetime as _dt
        if self.store.progress_date == _dt.now().strftime("%Y-%m-%d"):
            return True
        if courses is None:
            courses = self.client.fetch_courses()
        rows: list[dict] = []
        for co in courses:
            if stop_check and stop_check():
                log.info("任务点总览被中断，丢弃半份数据")
                return False
            row = {"course": co["name"], "done": None, "total": None,
                   "error": None}
            try:
                data = self.client.fetch_chapters(co, with_nodes=False)
                if data["progress"]:
                    row["done"], row["total"] = data["progress"]
                else:
                    row["error"] = "无进度数据"
            except Exception as e:
                row["error"] = " ".join(str(e).split())[:60]
            rows.append(row)
            time.sleep(0.4)
        self.store.set_progress(rows)
        return True

    def _score_detail(self, c: dict, hw: dict, title: str) -> str:
        """出分事件富化：尽力拉详情页拿"得分 X / 满分 Y"，失败返回空串。"""
        try:
            for it in hw.get("items", []):
                if it.get("title") == title:
                    d = self.client.fetch_homework_detail(c, it["index"])
                    if d.get("score") is not None:
                        full = d.get("full_score")
                        return f"得分 {d['score']}" + \
                            (f" / 满分 {full}" if full else "")
                    break
        except Exception as e:
            log.debug("出分详情拉取失败：%s", e)
        return ""

    # ---------- 事件构造 ----------

    def _evt(self, kind: str, course: str, title: str, verdict: dict,
             detail: str = "", **extra) -> Event:
        evt = Event(kind=kind, course=course, title=title, detail=detail,
                    tag=verdict["tag"], priority=verdict["priority"],
                    reason=verdict.get("reason", ""))
        evt.update(extra)
        self.store.append_timeline(evt)
        return evt

    # ---------- medium 资料的二次确认（可选，由 UI 闲时调用） ----------

    def probe_material(self, c: dict, data_id: int, filename: str) -> bool:
        """下载 pptx 读正文确认是不是作业。返回 True=是作业（升级 high）。"""
        if not self.probe_download:
            return False
        try:
            res = self.client.download_material(c, data_id, probe_dir(), filename)
            hit = material_is_homeworkish(res["path"])
            import os
            os.remove(res["path"])
            return bool(hit)
        except Exception as e:
            log.warning("资料预读失败 %s：%s", filename, e)
            return False
