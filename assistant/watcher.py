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


def _parse_send_time(raw) -> float:
    """通知 sendTime（"2026-09-20 10:49:46" 或毫秒时间戳，含数字字符串）→ epoch 秒，失败 0。"""
    try:
        if isinstance(raw, (int, float)) and raw > 1e12:
            return raw / 1000.0
        s = str(raw or "").strip().replace("T", " ")
        if not s:
            return 0.0
        if s.isdigit() and len(s) > 12:   # 字符串形式的毫秒时间戳
            return int(s) / 1000.0
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                import datetime as _dt
                return _dt.datetime.strptime(s[:19], fmt).timestamp()
            except ValueError:
                continue
    except Exception:
        pass
    return 0.0


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
        self._record_events = True    # 全量扫往年课时置 False：只建基线不入线

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

        # 课表活跃课程集合（顺带刷新课表缓存，UI 也能用）。
        # 判定以课名为准：服务端 lesson.courseId 有 6/11 门是空串（真实
        # 缓存实锤），按 id 匹配会把毛概/电磁场整批踢出巡检范围
        sched_names: set[str] = set()
        active_cids: set[str] = set()
        try:
            sched = self.client.fetch_schedule_full(refresh=False)
            if hasattr(self.store, "set_schedule") and sched.get("lessons"):
                self.store.set_schedule(sched)   # 回写落盘缓存供下次秒开
            for ls in sched.get("lessons", []):
                n = (ls.get("name") or "").strip()
                if n:
                    sched_names.add(n)
                cid = str(ls.get("courseid") or ls.get("courseId") or "")
                if cid:
                    active_cids.add(cid)
        except Exception as e:
            log.warning("课表获取失败，本轮按已存活跃集扫：%s", e)

        courses = self.client.fetch_courses()
        if sched_names:
            def _name_active(c: dict) -> bool:
                n = (c.get("name") or "").strip()
                return any(n == k or (k in n or n in k) for k in sched_names)
            # 名字对上但课表没给 id 的课，用课程列表里的真实 id 补进活跃集
            active_cids |= {str(c["courseid"]) for c in courses
                            if _name_active(c)}
        if active_cids:
            self.store.set_active(active_cids)

        if full:
            targets = courses
        else:
            targets = [c for c in courses
                       if str(c["courseid"]) in active_cids][:self.max_courses]

        for c in targets:
            if stop_check and stop_check():
                log.info("收到退出请求，本轮扫描提前收尾")
                break
            try:
                # 全量扫的目的是给往年课建基线；非本学期课的事件只会
                # 污染动态页和未读角标（"模拟电子技术基础"实锤）。
                # 活跃集为空=课表没拉到，不过滤兜底
                inactive = (full and active_cids
                            and str(c["courseid"]) not in active_cids)
                self._record_events = not inactive
                events += self._scan_course(c)
            except Exception as e:
                msg = str(e)
                if HOMEWORK_CLOSED_MARK in msg:
                    self.store.set_homework_open(self._cid(c), False)
                    continue
                log.warning("课程 %s 扫描失败：%s", c.get("name"), msg)
            finally:
                self._record_events = True
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
            # 事件时间用通知自己的 sendTime（全用扫描时刻会让动态页
            # 一整页同一个时间戳）；接口拉的是"最近100条"，会混进
            # 上学期的旧通知——超过 14 天的不算新动态（已标记已读）
            sent = _parse_send_time(n.get("sendTime", ""))
            if sent and ((time.time() - sent) > 14 * 86400
                         or (sent - time.time()) > 86400):
                continue   # 超 14 天的旧通知/预发到 1 天后的通知都不算新动态
            sender = n.get("createrName", "") or n.get("sender", "")
            verdict = classify_notice(n.get("title", ""), sender,
                                      n.get("content", ""))
            extra = {}
            if sent:
                extra["time"] = time.strftime("%Y-%m-%d %H:%M:%S",
                                              time.localtime(sent))
            events.append(self._evt("notice", sender,
                                    n.get("title", key), verdict,
                                    detail=(n.get("content", "") or "")[:160],
                                    **extra))
        return events

    # ---------- 考试表 / 任务点 ----------

    def _scan_exams(self) -> list[Event]:
        """考试安排：每轮 1 个请求；新考试进事件（首见建基线不报）。

        只留本学期的——考试表混着往年记录（图论/蓝桥杯/上学期期末），
        全放进来用户看到的就是"八年前的考试"列表。"""
        try:
            parsed = parse_exam_rows(self.client.fetch_exams())
        except Exception as e:
            log.warning("考试表拉取失败：%s", e)
            return []
        term_start = self._term_start()
        if term_start:
            parsed = [r for r in parsed if r["start"].date() >= term_start]
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

    def _term_start(self):
        """本学期第 1 周周一（课表锚点）；拿不到返回 None（不过滤兜底）。"""
        try:
            from xuexitong_mcp.client import ms_to_date
            cur = self.store.get_schedule().get("curriculum", {})
            fw = cur.get("firstWeekDate") or cur.get("firstWeekDateReal")
            return ms_to_date(int(fw)) if fw else None
        except Exception:
            return None

    def refresh_progress(self, stop_check=None, courses=None) -> bool:
        """任务点总览：逐课查询重（每课 1-2 请求），限速 0.4s/课。

        只在每日全量扫或用户手动刷新时跑；只扫本学期课表内的课
        （往年课不扫不报）。中断（退出程序）时不写缓存——半份数据
        会把"今天已刷"记死，整天不再重试。返回是否完整写入。
        """
        from datetime import datetime as _dt
        if self.store.progress_date == _dt.now().strftime("%Y-%m-%d"):
            return True
        if courses is None:
            courses = self.client.fetch_courses()
        # 用户规矩：任务点以本学期为主——往年课（马原/高数/上学期网课）
        # 不再扫不再喊"没上完"。课表锚点拿不到时保底全扫
        active_ids = {k.split("|")[0] for k, _ in self.store.active_courses()}
        if active_ids:
            courses = [c for c in courses
                       if str(c["courseid"]) in active_ids]
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
        if self._record_events:   # 往年课全量扫：只建基线，不污染时间线/角标
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
