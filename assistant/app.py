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
import sys
import traceback
from datetime import datetime
from pathlib import Path

from assistant.paths import ROOT

sys.path.insert(0, str(ROOT))

from PySide6.QtCore import (Qt, QMetaObject, QThread, QTimer, QUrl,  # noqa: E402
                            Signal, QObject)
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import (QApplication, QMenu,  # noqa: E402
                               QSystemTrayIcon)

from assistant.notify import Notifier  # noqa: E402
from assistant.reminders import ReminderEngine, in_class_now, in_dnd  # noqa: E402
from assistant.snapshot import (active_course_names,  # noqa: E402
                                build_snapshot, deadline_items,
                                ddl_view, week_grid)
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
    snapshot_ready = Signal(dict, bool)      # snap, ddl_force
    scan_done = Signal(int, str)          # 事件数, 时间文本
    scan_state = Signal(bool)             # worker → UI：扫描中（小窗同步图标转）
    toast_request = Signal(str, str)      # 标题, 正文（Toast 回 UI 线程发）

    def __init__(self, client, store, notifier, settings):
        super().__init__()
        self.client = client
        self.store = store
        self.notifier = notifier
        self.settings = settings
        self.watcher = Watcher(client, store)
        self.engine = ReminderEngine(store, settings)
        self._busy = False
        self.stopping = False            # 退出旗标：扫描循环尽快收尾
        # 跨线程信号连接：moveToThread 后这些槽在 worker 线程执行
        self.trigger.connect(self._on_trigger)
        self.hw_request.connect(self._on_hw_request)

    def _on_trigger(self, full: bool) -> None:
        self.do_scan(full)

    def _on_hw_request(self) -> None:
        try:
            items = deadline_items(
                self.client, horizon_days=30,
                only_courses=active_course_names(self.store) or None)
        except Exception:
            items = None   # None=获取失败：详情窗显示错误态而不是"没有作业"
        self.hw_ready.emit(items)

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
            body = "\n".join(f"【{e.get('tag')}】{e.get('course')} "
                             f"{e.get('title')}" for e in highs[:4])
            self.toast_request.emit(title, body)
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
                self.store.set_deadlines(dl_items)
            dl = {"items": dl_items or []}
            # 提醒聚合一条发，别连弹 N 个横幅（Windows 同源通知有限流）
            remind_msgs = []
            for r in self.engine.check(dl, rows):
                self.store.append_timeline(r)
                if r.get("silent"):
                    self.store.push_pending(r)
                else:
                    remind_msgs.append(r.get("text", ""))
            if remind_msgs:
                self.toast_request.emit("截止提醒",
                                        "\n".join(remind_msgs[:4]))
            if not still_silent:
                pending = self.store.pop_pending()
                if pending:
                    body = "\n".join(p.get("text", "") for p in pending[:4])
                    self.toast_request.emit("刚刚下课，补个提醒", body)
        except Exception:
            log.debug("提醒引擎跳过：%s", traceback.format_exc())

        snap = build_snapshot(self.client, self.store, refresh=False)
        self.snapshot_ready.emit(snap, True)   # bool=ddl_force
        self.store.save()

    def _today_rows(self) -> list[dict]:
        try:
            sched = self.client.fetch_schedule_full(refresh=False)
            from assistant.snapshot import week_lessons, week_of
            from xuexitong_mcp.widget import lesson_rows
            today = datetime.now().date()
            wk = week_of(sched, today)
            return lesson_rows(week_lessons(sched, wk),
                               sched.get("curriculum", {}), wk, today)
        except Exception:
            return []


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
            refresh_hw_cb=lambda: self.worker.hw_request.emit())
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
        self.worker_thread = QThread()
        self.worker = ScanWorker(self.client, self.store, self.notifier,
                                 self.settings)
        self.worker.moveToThread(self.worker_thread)

        self._build_tray()
        self._wire()
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

    # ---------- 动作 ----------

    def scan_now(self) -> None:
        self.worker.trigger.emit(False)   # 反馈=小窗同步图标旋转，不发托盘气泡

    def show_detail(self, tab: str = "") -> None:
        idx = {"动态": 0, "作业": 1, "设置": 2}.get(tab, 0)
        if tab:
            self.detail_bridge.gotoTab(idx)
        self.detail_win.show()
        self.detail_win.raise_()
        self.detail_win.requestActivate()
        self.worker.hw_request.emit()   # 打开即拉最新作业
        self.detail_bridge.set_timeline(self.store.timeline(limit=60))

    def toggle_widget(self) -> None:
        self.widget.setVisible(not self.widget.isVisible())

    def _on_toast(self, title: str, body: str) -> None:
        self.notifier.toast_text(title, body)

    def _on_hw_ready(self, items) -> None:
        """worker 的作业结果（已按本学期课过滤）→ 详情窗看板。"""
        if items is None:
            self.detail_bridge.set_hw(None)
            return
        rows = [dict(r) for r in items]
        self.detail_bridge.set_hw(ddl_view(rows))

    def _save_detail_settings(self, merged: dict):
        """详情窗保存：校验→落盘→生效，返回 (ok, 提示)。"""
        try:
            merged["scan_interval_min"] = max(5, min(240,
                int(merged.get("scan_interval_min", 30))))
            dnd = str(merged.get("dnd", "")).strip()
            if dnd and ("-" not in dnd or len(dnd.split("-")) != 2):
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
        self.bridge.set_ddl(ddl_view(self.store.get_deadlines()),
                            force=ddl_force)
        self._push_grid()

    def run(self) -> int:
        code = self.qapp.exec()
        self.store.save()
        return code

    def quit(self) -> None:
        self.store.save()
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


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if "--screenshot" in sys.argv:
        return _screenshot_mode()
    if already_running():
        print("学习通小助手已在运行（托盘可见）")
        return 0
    app = App()
    server = QLocalServer()
    server.listen(LOCK_NAME)
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
            app.quit()   # 走 App.quit：收 worker 线程+存盘，防析构竞态
            return
        app.bridge.set_tab(i)
        QTimer.singleShot(500, lambda: (shoot(f"{base}_t{i}.png"), step(i + 1)))

    def first():
        shoot(base + "_mini.png")
        QMetaObject.invokeMethod(app.widget, "toggleMode")
        QTimer.singleShot(500, lambda: step(0))

    QTimer.singleShot(6000, first)   # 等快照数据到位
    return app.qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
