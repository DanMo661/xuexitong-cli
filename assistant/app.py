# -*- coding: utf-8 -*-
"""桌面助手主程序：托盘常驻 + 巡检 worker + 悬浮小窗 + 详情窗。

装配关系：
  QApplication（单实例锁 QLocalServer）
   ├─ MainWidget（迷你条/标准卡悬浮窗）
   ├─ DetailWindow（动态/作业/设置）
   ├─ QSystemTrayIcon（菜单：立即巡检/详情/隐藏小窗/退出）
   ├─ ScanWorker（QThread 跑 Watcher + 提醒引擎 + 快照组装）
   └─ QTimer（周期触发 + 启动补跑：距 last_scan 超周期立即扫）
"""
import json
import logging
import os
import re
import sys
import time
import traceback
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

# 自举包路径：开机自启/直接 pythonw app.py 时 sys.path[0] 是 assistant/
# 而不是仓库根，没有这行 from assistant.paths 直接 ModuleNotFoundError
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.paths import ROOT

sys.path.insert(0, str(ROOT))

from PySide6.QtCore import (QAbstractNativeEventFilter, Qt, QMetaObject,  # noqa: E402
                            QThread, QTimer, QUrl, Signal, QObject)
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import (QApplication, QMenu,  # noqa: E402
                               QSystemTrayIcon)

from assistant.notify import Notifier  # noqa: E402
from assistant.reminders import ReminderEngine, in_class_now, in_dnd  # noqa: E402
from assistant.snapshot import (active_course_names,  # noqa: E402
                                build_snapshot, deadline_items,
                                ddl_view, exam_summary, exams_view,
                                notices_view, parse_exam_rows,
                                progress_view, week_grid)
from assistant.store import Store  # noqa: E402
from assistant.watcher import Watcher  # noqa: E402
from assistant.ui.bridge import Bridge  # noqa: E402
from assistant.ui.detail import load_settings, save_settings  # noqa: E402
from assistant.ui.detail_bridge import DetailBridge  # noqa: E402
from xuexitong_mcp.client import ChaoxingClient  # noqa: E402

log = logging.getLogger("app")
LOCK_NAME = "xuexitong-assistant-singleton"
QML_DIR = ROOT / "assistant" / "ui" / "qml"

FULL_SCAN_HOURS = 20   # 每天最多 1 次全量基线重扫（距上次 >20h 才做）

# 全局热键：Alt+Shift+C 唤起/隐藏小窗（RegisterHotKey + 原生消息过滤）
WM_HOTKEY = 0x0312
MOD_ALT, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0004, 0x4000


class _HotkeyFilter(QAbstractNativeEventFilter):
    """WM_HOTKEY 只在本进程窗口的消息队列里，Qt 事件循环线程回调（安全）。"""

    def __init__(self, cb):
        super().__init__()
        self._cb = cb

    def nativeEventFilter(self, event_type, message):
        try:
            if event_type == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    self._cb(int(msg.wParam))
        except Exception:
            pass
        return False


def tray_icon(color: str = "#0969DA") -> QIcon:
    """程序化生成托盘图标：圆底白字"学"。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing)
    qp.setBrush(QColor(color))
    qp.setPen(Qt.NoPen)
    qp.drawEllipse(4, 4, 56, 56)
    qp.setPen(QColor("white"))
    f = qp.font()
    f.setPixelSize(34)
    f.setBold(True)
    qp.setFont(f)
    qp.drawText(pm.rect(), Qt.AlignCenter, "学")
    qp.end()
    return QIcon(pm)


class ScanWorker(QObject):
    """巡检线程：所有网络 IO 在这，绝不阻塞 UI。

    触发方式：UI 线程 emit trigger 信号 → 槽在本对象所属线程（worker 线程）
    执行。绝不能直接调 do_scan()——直接调用永远在调用者线程跑，会把网络
    IO 拉回 UI 线程（nitpick P0 实锤过）。
    """

    trigger = Signal(bool)               # UI → worker：开始巡检（full）
    hw_request = Signal()                # UI → worker：取作业看板数据
    hw_ready = Signal(list)              # worker → UI：作业看板数据
    extras_request = Signal(str)         # UI → worker：exams/notices/progress
    extras_ready = Signal(str, bool)     # worker → UI：kind, 是否成功
    snapshot_ready = Signal(dict, bool)      # snap, ddl_force
    scan_done = Signal(int, str)          # 事件数, 时间文本
    scan_state = Signal(bool)             # worker → UI：扫描中（小窗同步图标转）
    toast_request = Signal(str, str, str)  # 标题, 正文, 点击跳转tab（空=不可点）

    def __init__(self, client, store, notifier, settings):
        super().__init__()
        self.client = client
        self.store = store
        self.notifier = notifier
        self.settings = settings
        self.watcher = Watcher(client, store)
        self.engine = ReminderEngine(store, settings)
        self._busy = False
        self._extra_busy: set[str] = set()   # 手动刷新去重：连点不叠加扫描
        self.stopping = False            # 退出旗标：扫描循环尽快收尾
        # 跨线程信号连接：moveToThread 后这些槽在 worker 线程执行
        self.trigger.connect(self._on_trigger)
        self.hw_request.connect(self._on_hw_request)
        self.extras_request.connect(self._on_extras_request)

    def _on_trigger(self, full: bool) -> None:
        self.do_scan(full)

    def _on_hw_request(self) -> None:
        try:
            items = deadline_items(
                self.client, horizon_days=30,
                only_courses=active_course_names(self.store) or None)
        except Exception:
            items = None   # None=获取失败：详情窗显示错误态而不是"没有作业"
        if items:
            self._enrich_course_links(items)
        self.hw_ready.emit(items)

    def _enrich_course_links(self, items: list[dict]) -> None:
        """给作业行补课程页 URL（作业自身无链接时的兜底直达）。
        fetch_courses 有 5 分钟缓存，worker 线程里调安全。"""
        try:
            courses = {c["name"]: c for c in self.client.fetch_courses()}
        except Exception:
            return
        for r in items:
            c = courses.get(r.get("course", ""))
            if c:
                r["courseUrl"] = (
                    "https://mooc1.chaoxing.com/visit/stucoursemiddle"
                    f"?courseid={c['courseid']}&clazzid={c['clazzid']}"
                    f"&cpi={c['cpi']}&ismooc2=1&v=2")

    def _on_extras_request(self, kind: str) -> None:
        """详情窗手动刷新：worker 线程拉数写缓存，完成后回 UI 重推。

        同类请求在跑时直接忽略（任务点逐课查询要十几秒，连点会叠加）。
        """
        if kind in self._extra_busy:
            return
        self._extra_busy.add(kind)
        ok = True
        try:
            if kind == "exams" or kind == "exams_progress":
                self.store.set_exams(parse_exam_rows(self.client.fetch_exams()))
            elif kind == "notices":
                items = self.client.fetch_notices(limit=30)
                self.store.set_notices(items if isinstance(items, list) else [])
            elif kind == "progress":
                self.watcher.refresh_progress(
                    stop_check=lambda: self.stopping)
        except Exception:
            log.debug("extras 拉取失败 %s：%s", kind, traceback.format_exc())
            ok = False
        finally:
            self._extra_busy.discard(kind)
        self.extras_ready.emit(kind, ok)

    def do_scan(self, full: bool = False) -> None:
        if self._busy:
            log.info("上一轮还没跑完，跳过本次触发")
            return
        self._busy = True
        try:
            self._scan(full)
        except Exception:
            log.error("巡检异常：%s", traceback.format_exc())
        finally:
            self._busy = False

    def _scan(self, full: bool) -> None:
        self.scan_state.emit(True)
        try:
            self._scan_inner(full)
        finally:
            self.scan_state.emit(False)

    def _scan_inner(self, full: bool) -> None:
        # 快照先行：只用缓存（落盘+进程内），秒出，绝不碰网络
        try:
            self.snapshot_ready.emit(build_snapshot(self.client, self.store,
                                                    refresh=False))
        except Exception:
            log.debug("首帧快照失败：%s", traceback.format_exc())

        events = self.watcher.scan_once(
            full=full, stop_check=lambda: self.stopping)
        highs = [e for e in events if e.get("priority") == "high"
                 and not e.get("silent")]
        if highs:
            n = len(highs)
            title = f"学习通有 {n} 条新动态" if n > 1 else "学习通新动态"
            body = "\n".join(
                f"【{e.get('tag')}】{e.get('course')} {e.get('title')}"
                + (f" · {e['detail']}" if e.get("detail")
                   and e.get("kind") == "hwscore" else "")
                for e in highs[:4])
            self.toast_request.emit(title, body, "动态")
            if self.settings.get("email_enabled"):
                self.notifier.send_email(highs)

        # 渐进 DDL 提醒（silent 的入补弹队列，下课/出免打扰时段补弹）
        try:
            rows = self._today_rows()
            now = datetime.now()
            from assistant.reminders import in_class_now, in_dnd
            still_silent = in_class_now(rows, now) or in_dnd(
                now, self.settings.get("dnd", "23:00-07:30"))
            dl_items = deadline_items(
                self.client, horizon_days=30,
                only_courses=active_course_names(self.store) or None)
            # None=拉取失败保旧缓存；[] 是真空（本学期全交完），照实清
            if dl_items is not None:
                self._enrich_course_links(dl_items)
                self.store.set_deadlines(dl_items)
            # 忽略要挡提醒引擎（"不再提醒"是承诺）：喂引擎前先滤掉
            ig = set(self.store.hw_ignores())
            from assistant.store import Store

            def _ignored(r: dict) -> bool:
                c, t = r.get("course", ""), r.get("title", "")
                u = r.get("url", "")
                return (Store.hw_key(c, t, u) in ig
                        or Store.hw_key(c, t) in ig)

            dl = {"items": [r for r in (dl_items or []) if not _ignored(r)]}
            # 提醒聚合一条发，别连弹 N 个横幅（Windows 同源通知有限流）
            remind_msgs = []
            for r in self.engine.check(dl, rows):
                self.store.append_timeline(r)
                if r.get("silent"):
                    self.store.push_pending(r)
                else:
                    remind_msgs.append(r.get("text", ""))
            if remind_msgs:
                self.toast_request.emit("截止提醒", "\n".join(remind_msgs[:4]),
                                        "作业")
            if not still_silent:
                pending = self.store.pop_pending()
                if pending:
                    body = "\n".join(
                        p.get("text", "") for p in pending[:4]
                        if not _ignored(p))
                    if body:
                        self.toast_request.emit("刚刚下课，补个提醒", body, "作业")
        except Exception:
            log.debug("提醒引擎跳过：%s", traceback.format_exc())

        snap = build_snapshot(self.client, self.store, refresh=False)
        self.snapshot_ready.emit(snap, True)   # bool=ddl_force
        self.store.save()

    def _today_rows(self) -> list[dict]:
        try:
            sched = self.client.fetch_schedule_full(refresh=False)
            from assistant.snapshot import (course_colors, set_course_colors,
                                            week_lessons, week_of)
            from xuexitong_mcp.widget import lesson_rows
            set_course_colors(course_colors(sched.get("lessons", [])))
            today = datetime.now().date()
            wk = week_of(sched, today)
            return lesson_rows(week_lessons(sched, wk),
                               sched.get("curriculum", {}), wk, today)
        except Exception:
            return []


class _ToastRelay(QObject):
    """Toast 点击回调（windows-toasts 监听线程）→ Qt 信号 → UI 线程。"""
    triggered = Signal(str)


class App:
    def __init__(self, **kwargs):
        self.settings = load_settings()
        self.store = Store(str(ROOT / "store.json"))
        self.client = ChaoxingClient()
        self.notifier = Notifier(self.settings)

        self.qapp = QApplication(sys.argv)
        self.qapp.setQuitOnLastWindowClosed(False)
        self.qapp.setApplicationName("学习通小助手")

        # 两个 QML 窗：悬浮小窗(Main) + 详情窗(DetailWindow)，同引擎同 Theme
        self.bridge = Bridge(get_position=self._load_pos,
                             save_pos=self._save_pos)
        self.detail_bridge = DetailBridge(
            settings=self.settings,
            save_cb=self._save_detail_settings,
            refresh_hw_cb=lambda: self.worker.hw_request.emit(),
            refresh_extra_cb=lambda k: self.worker.extras_request.emit(k),
            notice_read_cb=self._on_notice_read)
        self.engine = QQmlApplicationEngine()
        self.engine.addImportPath(str(QML_DIR))
        self.engine.rootContext().setContextProperty("Bridge", self.bridge)
        self.engine.rootContext().setContextProperty("DBridge",
                                                     self.detail_bridge)
        # 注意：engine.load(list) 在 PySide6 有 qt_isinstance 泛型 bug，逐个加载
        self.engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
        self.engine.load(QUrl.fromLocalFile(str(QML_DIR / "DetailWindow.qml")))
        if len(self.engine.rootObjects()) < 2:
            raise RuntimeError("QML 加载失败（看上方 stderr 的 qml 警告）")
        self.widget = self.engine.rootObjects()[0]
        self.detail_win = self.engine.rootObjects()[1]
        self.bridge.actionTriggered.connect(self.on_widget_action)
        # Toast 点击跳转：回调在外部线程，信号转发回 UI 线程
        self._toast_relay = _ToastRelay()
        self._toast_relay.triggered.connect(lambda tab: self.show_detail(tab))
        self.bridge.hwOpenRequested.connect(self._on_open_hw)
        self.bridge.hwIgnoreRequested.connect(self._on_ignore_hw)
        self.detail_bridge.hwOpenRequested.connect(self._on_open_hw)
        self.detail_bridge.hwIgnoreRequested.connect(self._on_ignore_hw)
        self.detail_bridge.unignoreRequested.connect(self._on_unignore_all)
        self.detail_bridge.icsRequested.connect(self._on_export_ics)
        self.worker_thread = QThread()
        self.worker = ScanWorker(self.client, self.store, self.notifier,
                                 self.settings)
        self.worker.moveToThread(self.worker_thread)

        self._build_tray()
        self._wire()
        self._register_hotkey()
        self._schedule(startup_scan=kwargs.get("startup_scan", True))
        self._week_offset = 0
        # 首帧数据（纯缓存）+ 60s 心跳：状态翻牌/预备铃/下课补弹
        self._push_all()
        self.classup_engine = ReminderEngine(self.store, self.settings)
        self.tick_timer = QTimer(interval=60000, timeout=self._on_tick)
        self.tick_timer.start()

    # ---------- 数据推送（UI 线程，纯缓存计算） ----------

    def _push_all(self) -> None:
        try:
            self._on_snapshot(build_snapshot(self.client, self.store,
                                             refresh=False))
        except Exception:
            log.debug("首帧推送失败：%s", traceback.format_exc())

    def _push_grid(self) -> None:
        try:
            self.bridge.set_grid(week_grid(self.store, self._week_offset))
        except Exception:
            log.debug("周网格失败：%s", traceback.format_exc())

    def _push_extras(self) -> None:
        """考试/通知/任务点（纯缓存计算）→ 小窗摘要 + 详情窗列表。"""
        try:
            view = exams_view(self.store.get_exams())
            text, sub, cnt, ongoing = exam_summary(view)
            pv = progress_view(self.store.get_progress(),
                               active_course_names(self.store) or None)
            pv["date"] = self.store.progress_date
            self.bridge.set_extras(text, sub, cnt, ongoing,
                                   pv["totalLeft"], pv["coursesLeft"])
            self.detail_bridge.set_exams(view)
            self.detail_bridge.set_progress(pv)
            self.detail_bridge.set_notices(notices_view(self.store.get_notices()))
        except Exception:
            log.debug("extras 推送失败：%s", traceback.format_exc())

    def _on_tick(self) -> None:
        """每分钟：刷新课程状态（进行中→已结束翻牌）+ 预备铃 + 补弹。"""
        now = datetime.now()
        # 跨零点：周次进位，翻周浏览态重置回本周（别无声跳一周）
        if now.date() != getattr(self, "_tick_date", None):
            self._tick_date = now.date()
            self._week_offset = 0
        snap = build_snapshot(self.client, self.store, now, refresh=False)
        self._on_snapshot(snap)
        rows = snap.get("rows", [])
        wrote = False
        try:
            for e in self.classup_engine.check_classup(rows, now):
                self.store.append_timeline(e)
                self.notifier.toast_text("上课提醒", e.get("text", ""))
                self.bridge.set_events(self.store.timeline(20))
                wrote = True
        except Exception:
            log.debug("预备铃跳过：%s", traceback.format_exc())
        # 下课补弹（免打扰时段继续静默）
        if rows and not in_class_now(rows, now) \
                and not in_dnd(now, self.settings.get("dnd", "23:00-07:30")):
            pending = self.store.pop_pending()
            if pending:
                body = "\n".join(p.get("text", "") for p in pending[:4])
                self.notifier.toast_text("刚刚下课，补个提醒", body)
                wrote = True
        if wrote:
            self.store.save()   # 两次扫描之间的写尽快落盘（崩溃不丢）

    def _on_week_requested(self, offset: int) -> None:
        # clamp 到学期范围（与 week_grid 内部钳制一致，点边不白点）
        sched = self.store.get_schedule()
        from assistant.snapshot import week_of
        cur_wk = week_of(sched, datetime.now().date())
        maxw = int(sched.get("curriculum", {}).get("maxWeek") or 0)
        lo, hi = 1 - cur_wk, (maxw - cur_wk if maxw else 30)
        self._week_offset = max(lo, min(hi, int(offset)))
        self._push_grid()

    # ---------- 位置持久化 ----------

    def _load_pos(self):
        try:
            with open(ROOT / "widget_geometry.json", encoding="utf-8") as f:
                d = json.load(f)
            return (int(d["x"]), int(d["y"]))
        except Exception:
            return None

    def _save_pos(self, x: int, y: int) -> None:
        try:
            with open(ROOT / "widget_geometry.json", "w", encoding="utf-8") as f:
                json.dump({"x": x, "y": y}, f)
        except Exception:
            pass

    # ---------- 装配 ----------

    def _wire(self) -> None:
        self.worker.snapshot_ready.connect(self._on_snapshot)
        # 成员方法槽：接收者上下文在 UI 线程，自动队列连接；
        # 裸 lambda 是直连，会在 worker 线程里碰 GUI 对象
        self.worker.toast_request.connect(self._on_toast)
        self.worker.scan_done.connect(self._on_scan_done)
        self.worker.scan_state.connect(self.bridge.set_scanning)
        self.bridge.weekRequested.connect(self._on_week_requested)
        # 详情窗作业页：刷新走 worker 线程，结果回 UI 渲染
        self.worker.hw_ready.connect(self._on_hw_ready)
        self.worker.extras_ready.connect(self._on_extras_ready)

    def _on_extras_ready(self, kind: str, ok: bool) -> None:
        self.detail_bridge.set_refreshing(False)
        self._push_extras()
        self.detail_bridge.settingsApplied.emit(
            "已刷新" if ok else "刷新失败，稍后再试")

    def _on_notice_read(self, key: str) -> None:
        self.store.mark_notice_read(key)
        self.store.save()
        self._push_extras()

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(tray_icon())
        self.tray.setToolTip("学习通小助手")
        m = QMenu()
        m.addAction("检查新动态", self.scan_now)
        m.addAction("打开详情", self.show_detail)
        m.addAction("显示/隐藏小窗", self.toggle_widget)
        m.addSeparator()
        m.addAction("退出", self.quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(
            lambda reason: self.toggle_widget()
            if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def _schedule(self, startup_scan: bool = True) -> None:
        """周期 + 补跑：启动时距 last_scan 超一个周期立即扫。"""
        self.worker_thread.start()
        interval = max(5, self.settings.get("scan_interval_min", 30)) * 60 * 1000
        self.timer = QTimer(interval=interval, timeout=self.scan_now)
        self.timer.start()
        if not startup_scan:
            return

        from datetime import datetime as _dt
        last = self.store.last_full_scan
        need_full = True
        if last:
            try:
                need_full = (_dt.now() - _dt.fromisoformat(last)).total_seconds() \
                    > FULL_SCAN_HOURS * 3600
            except ValueError:
                pass
        # 启动补跑（延迟 3s 等 UI 稳定；emit 信号让网络 IO 落在 worker 线程）
        QTimer.singleShot(3000, lambda: self.worker.trigger.emit(need_full))
        log.info("调度就绪：常规 %d 分钟一轮；本次启动将做%s",
                 interval // 60000, "全量扫" if need_full else "常规扫")

    # ---------- 全局热键 ----------

    def _register_hotkey(self) -> None:
        """Alt+Shift+C 全局唤起/隐藏小窗（被占用则静默跳过，托盘仍可用）。"""
        import ctypes
        try:
            hwnd = int(self.widget.winId())
            ok = ctypes.windll.user32.RegisterHotKey(
                None if hwnd == 0 else hwnd, 1,
                MOD_ALT | MOD_SHIFT | MOD_NOREPEAT, ord("C"))
            if not ok:
                log.warning("热键注册失败（可能被其他程序占用）：Alt+Shift+C")
                return
            self._hotkey_hwnd = hwnd
            self._last_hotkey = 0.0
            self._hotkey_filter = _HotkeyFilter(
                lambda _id: self._on_hotkey())
            self.qapp.installNativeEventFilter(self._hotkey_filter)
            log.info("全局热键就绪：Alt+Shift+C 唤起小窗")
        except Exception:
            log.debug("热键不可用：%s", traceback.format_exc())

    def _on_hotkey(self) -> None:
        """防抖：系统偶发重发一次按压产生两条 WM_HOTKEY，连切两次等于没切。
        MOD_NOREPEAT 已挡按住狂闪，这里只需盖住双发。"""
        import time
        now = time.monotonic()
        if now - self._last_hotkey < 0.15:
            return
        self._last_hotkey = now
        self.toggle_widget()

    def _unregister_hotkey(self) -> None:
        try:
            import ctypes
            if getattr(self, "_hotkey_hwnd", None) is not None:
                ctypes.windll.user32.UnregisterHotKey(self._hotkey_hwnd, 1)
        except Exception:
            pass

    # ---------- 动作 ----------

    def scan_now(self) -> None:
        self.worker.trigger.emit(False)   # 反馈=小窗同步图标旋转，不发托盘气泡

    def show_detail(self, tab: str = "") -> None:
        idx = {"动态": 0, "作业": 1, "考试": 2, "通知": 3, "设置": 4}.get(tab, 0)
        if tab:
            self.detail_bridge.gotoTab(idx)
        self.detail_win.show()
        self.detail_win.raise_()
        self.detail_win.requestActivate()
        if idx <= 1:   # 只有动态/作业页吃作业数据，从考试/通知进来别白拉
            self.worker.hw_request.emit()
        self.detail_bridge.set_timeline(self.store.timeline(limit=60))
        self._push_extras()

    def toggle_widget(self) -> None:
        self.widget.setVisible(not self.widget.isVisible())

    def _on_toast(self, title: str, body: str, tab: str = "") -> None:
        cb = None
        if tab:
            def cb(t=tab, relay=self._toast_relay):
                relay.triggered.emit(t)
        self.notifier.toast_text(title, body, on_click=cb)

    # ---------- R2：作业直达 / 忽略 / ics 导出 ----------

    def _on_open_hw(self, url: str, course: str, title: str) -> None:
        """在学习通打开作业页（无链接兜底课程页）+ 复制作业名。"""
        from PySide6.QtGui import QDesktopServices
        if title:
            self.qapp.clipboard().setText(title)
        target = url or ""
        if not target:
            # 缓存行里带的课程页兜底（worker 预算好，UI 线程不碰网）
            for r in self.store.get_deadlines():
                if r.get("course") == course and r.get("title") == title:
                    target = r.get("courseUrl", "") or ""
                    break
        if target:
            QDesktopServices.openUrl(QUrl(target))
            self.notifier.toast_text(
                "正在打开学习通",
                f"作业名已复制：{title[:30]}\n首次需在浏览器登录一次学习通")
        else:
            self.notifier.toast_text("暂时打不开这份作业",
                                     "点 ⟳ 刷新作业列表后再试")

    def _on_ignore_hw(self, course: str, title: str, url: str = "") -> None:
        self.store.ignore_hw(course, title, url)
        self.store.save()
        self._refresh_ddl()
        self.notifier.toast_text("已从看板隐藏", "详情窗作业页底部可全部恢复")

    def _on_unignore_all(self) -> None:
        n = self._ignored_count()   # 先算：名单里可能躺着陈年条目
        self.store.unignore_hw_all()
        self.store.save()
        self._refresh_ddl()
        self.detail_bridge.settingsApplied.emit(f"已恢复 {n} 条作业")

    def _on_export_ics(self) -> None:
        """课表缓存 → .ics（手机日历导入；复用协议层 build_ics）。"""
        sched = self.store.get_schedule()
        lessons = sched.get("lessons") or []
        if not lessons:
            self.detail_bridge.settingsApplied.emit("课表还没同步，稍后再导")
            return
        try:
            from xuexitong_mcp.client import build_ics
            text = build_ics(lessons, sched.get("curriculum", {}))
        except Exception as e:
            self.detail_bridge.settingsApplied.emit(f"导出失败：{e}")
            return
        from PySide6.QtWidgets import QFileDialog
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.expanduser("~")
        # parent 必须是 QWidget；detail_win 是 QQuickWindow，传了直接 TypeError
        path, _ = QFileDialog.getSaveFileName(
            None, "导出课表", os.path.join(desktop, "课表.ics"),
            "日历文件 (*.ics)")
        if not path:
            return
        if not path.lower().endswith(".ics"):
            path += ".ics"   # 不自动补后缀，手机日历认不出无后缀文件
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)   # build_ics 已是 CRLF，newline="" 防二次转换
        except OSError as e:
            self.detail_bridge.settingsApplied.emit(f"写入失败：{e}")
            return
        self.detail_bridge.settingsApplied.emit(f"已导出：{os.path.basename(path)}")

    def _ddl_rows(self) -> list[dict]:
        return ddl_view(self.store.get_deadlines(),
                        ignores=self.store.hw_ignores())

    def _ignored_count(self) -> int:
        from assistant.store import Store
        keys = {Store.hw_key(r.get("course", ""), r.get("title", ""),
                             r.get("url", ""))
                for r in self.store.get_deadlines()}
        return sum(1 for k in self.store.hw_ignores() if k in keys)

    def _refresh_ddl(self) -> None:
        rows = self._ddl_rows()
        self.bridge.set_ddl(rows, force=True)
        self.detail_bridge.set_hw(rows)
        n = self._ignored_count()
        self.bridge.set_ignored(n)
        self.detail_bridge.set_hw_ignored(n)

    def _on_hw_ready(self, items) -> None:
        """worker 的作业结果（已按本学期课过滤）→ 落库 + 详情窗看板。
        落库让忽略/恢复操作有同一份最新数据可滤，不会回退到旧缓存。"""
        if items is None:
            self.detail_bridge.set_hw(None)
            return
        self.store.set_deadlines([dict(r) for r in items])
        rows = ddl_view(self.store.get_deadlines(),
                        ignores=self.store.hw_ignores())
        self.detail_bridge.set_hw(rows)
        self.detail_bridge.set_hw_ignored(self._ignored_count())

    def _save_detail_settings(self, merged: dict):
        """详情窗保存：校验→落盘→生效，返回 (ok, 提示)。"""
        try:
            merged["scan_interval_min"] = max(5, min(240,
                int(merged.get("scan_interval_min", 30))))
            dnd = str(merged.get("dnd", "")).strip()
            m2 = re.fullmatch(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", dnd)
            # 形状 + 值域都查：25:99 这种"合法形状非法值"存进去，
            # in_dnd 会静默走错分支，免打扰悄悄失效
            bad = not m2 or any(
                int(g) >= (24 if i % 2 == 0 else 60)
                for i, g in enumerate(m2.groups()))
            if dnd and bad:
                return False, "免打扰时段格式不对，应像 23:00-07:30"
            merged["dnd"] = dnd
            save_settings(merged)
            from assistant.ui.detail import set_autostart
            set_autostart(bool(merged.get("autostart")))
            self.on_settings(merged)
            return True, "已保存"
        except Exception as e:
            log.error("保存设置失败：%s", e)
            return False, f"保存失败：{e}"

    def _on_scan_done(self, n: int, t: str) -> None:
        self.tray.setToolTip(
            f"学习通小助手 — 上次检查 {t}（{n} 条新动态）")

    def on_widget_action(self, name: str) -> None:
        if name == "scan_now":
            self.scan_now()
        elif name == "open_detail":
            self.show_detail()
        elif name == "open_detail_hw":
            self.show_detail(tab="作业")
        elif name == "open_detail_exam":
            self.show_detail(tab="考试")
        elif name == "hw_unignore_all":
            self._on_unignore_all()
        elif name == "mark_read":
            self.store.mark_read()
            self.store.save()
            self._push_all()          # 刷新未读角标
        elif name == "hide":
            self.widget.hide()

    def on_settings(self, new_settings: dict) -> None:
        self.settings = new_settings
        self.worker.settings = new_settings
        self.notifier.settings = new_settings
        interval = max(5, new_settings.get("scan_interval_min", 30)) * 60 * 1000
        self.timer.setInterval(interval)
        self.tray.setToolTip("学习通小助手")

    def _on_snapshot(self, snap: dict, ddl_force: bool = False) -> None:
        self.bridge.set_snapshot(snap)
        self.bridge.set_events(self.store.timeline(limit=20))
        self.detail_bridge.set_timeline(self.store.timeline(limit=60))
        self.bridge.set_ddl(self._ddl_rows(), force=ddl_force)
        self.bridge.set_ignored(self._ignored_count())
        self._push_grid()
        self._push_extras()

    def run(self) -> int:
        code = self.qapp.exec()
        self.store.save()
        try:   # 先收引擎再退出：销毁期 QML 绑定读到 null 刷 TypeError 噪声
            self.engine.deleteLater()
            self.qapp.processEvents()
        except Exception:
            pass
        return code

    def quit(self) -> None:
        self.store.save()
        self._unregister_hotkey()
        self.worker.stopping = True   # 让扫描循环尽快收尾
        self.worker_thread.quit()
        # 一轮扫描分钟级，等满 30s 防 QThread 活着被析构崩溃
        if not self.worker_thread.wait(30000):
            log.warning("worker 线程 30s 未收尾，放弃等待")
        self.qapp.quit()


def already_running() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(LOCK_NAME)
    if sock.waitForConnected(200):
        sock.disconnectFromServer()
        return True
    QLocalServer.removeServer(LOCK_NAME)   # 清理崩溃残留
    return False


# 命名互斥量句柄（必须留在全局引用里，进程退出才释放）
_mutex_handle = None


def _grab_mutex() -> bool:
    """Windows 命名互斥量做单例仲裁。QLocalServer 的具名管道允许多实例
    listen 同名（双冷启动实测两个都返回 True），锁不住。"""
    global _mutex_handle
    import ctypes
    ERROR_ALREADY_EXISTS = 183
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(
        None, False, f"Global\\{LOCK_NAME}")
    return not (_mutex_handle
                and ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if "--screenshot" in sys.argv:
        return _screenshot_mode()
    if already_running():
        print("学习通小助手已在运行（托盘可见）")
        return 0
    if not _grab_mutex():   # 双冷启动竞态：管道探测都失败时靠互斥量兜底
        print("学习通小助手已在运行（互斥锁被占）")
        return 0
    app = App()
    server = QLocalServer()
    if not server.listen(LOCK_NAME):   # 锁没拿到（同名管道被占）必须退出，
        print("学习通小助手已在运行（锁被占用）")  # 否则就双实例双托盘了
        return 0
    app.widget.show()   # 桌面小组件的意义就是开机可见；藏进托盘走"显示/隐藏"
    return app.run()


def _screenshot_mode() -> int:
    """调试模式：启动→等首帧数据→迷你态+四页各截一张 PNG→退出（不进托盘）。

    注意：QQuickWindow 离屏帧在窗口高度动画后不重绘（黑块假象，之前踩过），
    所以每步都等动画跑完再截。
    """
    out = sys.argv[sys.argv.index("--screenshot") + 1] \
        if len(sys.argv) > sys.argv.index("--screenshot") + 1 else "shot.png"
    base = out.replace(".png", "")
    app = App(startup_scan=False)   # 截图模式不跑巡检：防线程析构竞态
    app.widget.show()

    def shoot(path: str):
        app.qapp.processEvents()
        # QQuickWindow 离屏 grab 在高度动画后不重绘（黑块假象），必须截
        # 屏幕合成后的窗口区域
        win = app.widget
        scr = win.screen() if hasattr(win, "screen") else app.qapp.primaryScreen()
        img = scr.grabWindow(0, int(win.x()), int(win.y()),
                             int(win.width()), int(win.height()))
        img.save(path)
        print("saved:", path, img.width(), "x", img.height())

    def step(i: int):
        if i > 3:
            detail_step(0)   # 小窗四页拍完 → 详情窗五页
            return
        app.bridge.set_tab(i)
        QTimer.singleShot(500, lambda: (shoot(f"{base}_t{i}.png"), step(i + 1)))

    def _img_blank(img) -> bool:
        """全图同色 = 离屏帧没重绘（黑块/白块假象，历史坑）。"""
        if img is None or img.isNull():
            return True
        qi = img.toImage() if hasattr(img, "toImage") else img
        s = qi.scaled(24, 24)
        first = s.pixelColor(0, 0)
        return all(s.pixelColor(x, y) == first
                   for y in range(24) for x in range(24))

    def grab_detail_win(path: str) -> None:
        from PySide6.QtCore import Qt
        w = app.detail_win
        # 普通窗口会被任何置顶窗口（视频播放器/终端）盖住，区域截屏
        # 就截到别人了。临时把自己也置顶 → 区域截屏 → 撤销置顶。
        old_flags = w.flags()
        w.setFlags(old_flags | Qt.WindowStaysOnTopHint)
        w.show()   # 换 flags 会重建原生窗口，显式保显示
        w.raise_()
        w.requestActivate()
        app.qapp.processEvents()
        time.sleep(0.15)   # 等窗口管理器重排 z 序
        app.qapp.processEvents()
        m = w.frameMargins()
        img = w.screen().grabWindow(
            0, int(w.x() - m.left()), int(w.y() - m.top()),
            int(w.width() + m.left() + m.right()),
            int(w.height() + m.top() + m.bottom()))
        w.setFlags(old_flags)
        img.save(path)
        print("saved:", path, img.width(), "x", img.height())

    def detail_step(i: int):
        if i > 4:
            # 调试模式专用硬退：App.quit() 会因 worker 线程悬住退不干净
            # （实测残留僵尸进程占着全局热键）。截图模式无状态要保。
            print("screenshot done")
            sys.stdout.flush(); sys.stderr.flush()
            import os
            os._exit(0)
        app.detail_bridge.gotoTab(i)
        app.detail_win.show()
        app.detail_win.raise_()
        QTimer.singleShot(500,
                          lambda: (grab_detail_win(f"{base}_d{i}.png"),
                                   detail_step(i + 1)))

    def first():
        shoot(base + "_mini.png")
        QMetaObject.invokeMethod(app.widget, "toggleMode")
        QTimer.singleShot(500, lambda: step(0))

    QTimer.singleShot(6000, first)   # 等快照数据到位
    return app.qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
