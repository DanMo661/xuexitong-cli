# -*- coding: utf-8 -*-
"""主悬浮窗：迷你条 ↔ 标准卡片两态（同窗 geometry 动画），方向感知进场。

窗口规格（Class-Widgets 实测组合）：
  FramelessWindowHint | WindowStaysOnTopHint | Tool（不进任务栏/Alt+Tab）
数据由外部注入：set_snapshot(dict)；本地只做倒计时 tick 与呼吸点。
"""
import json
import os

from PySide6.QtCore import QPoint, Qt, QTimer, QPropertyAnimation, QRect
from PySide6.QtGui import QGuiApplication, QMouseEvent, QPainter, QColor
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu,
                               QProgressBar, QVBoxLayout, QWidget)

from ..ui import motion
from ..ui.theme import DUR, palette, qss, with_alpha

MINI = QSize_ = (340, 54)      # 迷你条
FULL = (340, 436)              # 标准卡
POS_FILE_NAME = "widget_geometry.json"


class Breather(QWidget):
    """呼吸进度环：当前节课按进度画弧 + 呼吸光晕；无课时静态灰点。"""

    def __init__(self, p: dict):
        super().__init__()
        self.setFixedSize(16, 16)
        self._p = p
        self._phase = 0.0
        self._active = False
        self._percent = 0
        self._tick = QTimer(self, interval=50, timeout=self._on_tick)
        self._tick.start()

    def set_active(self, on: bool, percent: int = 0) -> None:
        self._active = on
        self._percent = max(0, min(100, percent))

    def _on_tick(self) -> None:
        self._phase = (self._phase + 0.05) % 1.0
        self.update()

    def paintEvent(self, ev) -> None:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPen
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(2, 2, 12, 12)
        if not self._active:
            qp.setBrush(QColor(self._p["fg_weak"]))
            qp.setPen(Qt.NoPen)
            qp.drawEllipse(QRectF(5, 5, 6, 6))
            return
        base = QColor(self._p["accent"])
        track = QColor(base)
        track.setAlpha(60)
        pen = QPen(track, 2.4)
        pen.setCapStyle(Qt.RoundCap)
        qp.setPen(pen)
        qp.drawArc(rect, 0, 360 * 16)
        # 呼吸光晕 + 进度弧
        glow = 0.5 + 0.5 * (0.5 - 0.5 * pow(2 * self._phase - 1, 2))
        pen2 = QPen(QColor(base), 2.4)
        pen2.setCapStyle(Qt.RoundCap)
        c = QColor(base)
        c.setAlphaF(0.55 + 0.45 * glow)
        pen2.setColor(c)
        qp.setPen(pen2)
        span = int(-360 * 16 * self._percent / 100)
        qp.drawArc(rect, 90 * 16, span)


class _MiniBar(QWidget):
    """当前节进度条：细圆轨道 + 填充，自绘保证可见。"""

    def __init__(self, percent: int, bar_color: str = "#FFFFFF"):
        super().__init__()
        self.percent = max(0, min(100, percent))
        self.bar_color = bar_color
        self.setFixedSize(64, 6)

    def paintEvent(self, ev) -> None:
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        track = QColor(self.bar_color)
        track.setAlpha(70)
        qp.setBrush(track)
        qp.setPen(Qt.NoPen)
        qp.drawRoundedRect(0, 1, self.width(), 4, 2, 2)
        qp.setBrush(QColor(self.bar_color))
        qp.drawRoundedRect(0, 1, max(4, self.width() * self.percent // 100), 4, 2, 2)


class MainWidget(QWidget):
    """迷你条/标准卡两态主窗。"""

    def __init__(self, settings: dict, on_action=None):
        super().__init__()
        self.settings = settings
        self.on_action = on_action           # callable(str) → app 层动作分发
        self.mode = "mini"
        self._drag = None
        self._pos = None

        self.p = palette(settings.get("theme", "auto"))
        self.setWindowTitle("学习通小助手")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(qss(self.p, radius=10))

        self._build_body()
        self._place_initial()
        self._enter_from_edge()

    # ---------- 布局 ----------

    def _build_body(self) -> None:
        self.root = QFrame(objectName="card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.addWidget(self.root)

        outer = QVBoxLayout(self.root)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        # -- 头部（两态共用）--
        head = QHBoxLayout()
        self.dot = Breather(self.p)
        self.lbl_title = QLabel("学习通小助手", objectName="strong")
        self.lbl_countdown = QLabel("", objectName="weak")
        self.lbl_countdown.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        head.addWidget(self.dot)
        head.addSpacing(6)
        head.addWidget(self.lbl_title)
        head.addStretch(1)
        head.addWidget(self.lbl_countdown)
        outer.addLayout(head)

        # -- 展开态内容 --
        self.lbl_date = QLabel("", objectName="weak")
        outer.addWidget(self.lbl_date)

        self.lesson_box = QVBoxLayout()
        self.lesson_box.setSpacing(4)
        outer.addLayout(self.lesson_box)

        self.sep = QFrame(frameShape=QFrame.HLine)
        self.sep.setStyleSheet(f"color:{self.p['border']};max-height:1px;")
        outer.addWidget(self.sep)

        self.lbl_events_title = QLabel("最新动态", objectName="weak")
        outer.addWidget(self.lbl_events_title)
        self.event_rows: list[QLabel] = []
        for _ in range(3):
            l = QLabel("", objectName="weak", wordWrap=True)
            self.event_rows.append(l)
            outer.addWidget(l)
        self.lbl_sync = QLabel("", objectName="weak")
        self.lbl_sync.setStyleSheet(f"font-size:10px;color:{self.p['fg_weak']};")
        outer.addWidget(self.lbl_sync)
        self._set_full_visible(False)

    def _set_full_visible(self, on: bool) -> None:
        for w in ([self.lbl_date, self.sep, self.lbl_events_title, self.lbl_sync]
                  + self.event_rows):
            w.setVisible(on)
        # 迷你态课程列表整体隐藏（只留头部一行）
        for i in range(self.lesson_box.count()):
            it = self.lesson_box.itemAt(i)
            if it.widget():
                it.widget().setVisible(on)

    # ---------- 几何 ----------

    def _place_initial(self) -> None:
        scr = QGuiApplication.primaryScreen().availableGeometry()
        pos = self._load_pos()
        if pos is None or not scr.contains(QPoint(*pos)):
            pos = (scr.right() - FULL[0] - 24, scr.top() + 90)
        self._pos = list(pos)
        self.setGeometry(pos[0], pos[1], *MINI)

    def _cfg_path(self) -> str:
        from assistant.paths import ROOT
        return str(ROOT / POS_FILE_NAME)

    def _load_pos(self):
        try:
            with open(self._cfg_path(), encoding="utf-8") as f:
                d = json.load(f)
            return (int(d["x"]), int(d["y"]))
        except Exception:
            return None

    def save_geometry(self) -> None:
        try:
            with open(self._cfg_path(), "w", encoding="utf-8") as f:
                json.dump({"x": self._pos[0], "y": self._pos[1]}, f)
        except Exception:
            pass

    def _enter_from_edge(self) -> None:
        """方向感知进场：上半屏从上滑入，下半屏从下滑入 + 淡入。"""
        scr = QGuiApplication.primaryScreen().availableGeometry()
        from_top = self._pos[1] < scr.center().y()
        start_y = (scr.top() - FULL[1] - 20 if from_top
                   else scr.bottom() + 20)
        self.setWindowOpacity(0.0)
        geo = QPropertyAnimation(self, b"geometry")
        geo.setDuration(DUR["enter_slide"])
        geo.setStartValue(QRect(self._pos[0], start_y, *MINI))
        geo.setEndValue(QRect(self._pos[0], self._pos[1], *MINI))
        from ..ui.theme import CURVE
        geo.setEasingCurve(CURVE["enter_slide"])
        fade = motion.anim(self, b"windowOpacity", 0.0, 1.0, "enter_fade")
        g = motion.group(geo, fade)
        motion.keep_ref(g)
        g.start()

    # ---------- 数据注入 ----------

    def set_snapshot(self, snap: dict) -> None:
        """app 层巡检/课表数据到位后调用。"""
        self.lbl_date.setText(snap.get("date_label", ""))
        cur = snap.get("current")
        if cur:
            self.lbl_title.setText(cur.get("name", ""))
            self.lbl_countdown.setText(f"剩 {snap.get('countdown', '')}")
            self.dot.set_active(True, snap.get("current_progress", 0))
        else:
            self.lbl_title.setText(snap.get("next_label", "今天没有课了 ✓"))
            self.lbl_countdown.setText("")
            self.dot.set_active(False)
        # 课程行
        while self.lesson_box.count():
            it = self.lesson_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for row in snap.get("rows", [])[:6]:
            self.lesson_box.addWidget(self._lesson_row(row))
        # 动态行（占位只在一条真实动态都没有时显示）
        evs = snap.get("events", [])[:3]
        for i, l in enumerate(self.event_rows):
            e = evs[i] if i < len(evs) else None
            if e:
                # 红色只留给 high；medium 用主题蓝标点，low 中性灰
                mark_color = {"high": self.p["red"],
                              "medium": self.p["accent"],
                              "low": self.p["fg_weak"]}[e.get("priority", "low")]
                l.setStyleSheet(f"font-size:11px;color:{self.p['fg']};")
                l.setText(f"<span style='color:{mark_color}'>●</span> "
                          f"{e.get('course', '')}  {e.get('title', '')}")
            elif i == 0 and not evs:
                l.setStyleSheet(f"font-size:11px;color:{self.p['fg_sub']};")
                l.setText("· 暂无新动态")
            else:
                l.setStyleSheet(f"font-size:11px;color:{self.p['fg']};")
                l.setText("")
        self.lbl_sync.setText(f"上次同步 {snap.get('last_sync', '—')}")
        self._set_full_visible(self.mode == "full")   # 重建行后恢复当前形态

    def _lesson_row(self, row: dict) -> QWidget:
        cur = row.get("state") == "current"
        par = row.get("state") == "parallel"
        w = QFrame()
        if cur:
            # 当前节：饱和品牌蓝底 + 白字（rgba 保留透明度，name() 会丢 alpha）
            c = with_alpha(self.p["accent"], 235)
            w.setStyleSheet(
                f"background:rgba({c.red()},{c.green()},{c.blue()},0.92);"
                f"border-radius:6px;")
            fg, sub = "#FFFFFF", "rgba(255,255,255,0.85)"
        elif par:
            # 并行课（同时段另一门）：弱蓝左边条提示"这门也在上课"
            w.setStyleSheet(
                f"background:{self.p['card']};border-left:3px solid "
                f"{with_alpha(self.p['accent'], 120).name()};border-radius:4px;")
            fg, sub = self.p["fg"], self.p["fg_sub"]
        else:
            w.setStyleSheet("background:transparent;border-radius:6px;")
            if row.get("state") == "done":
                fg, sub = self.p["fg_weak"], self.p["fg_weak"]
            else:
                fg, sub = self.p["fg"], self.p["fg_sub"]
        h = QHBoxLayout(w)
        h.setContentsMargins(8, 4, 8, 4)
        name = QLabel(row.get("name", ""))
        name.setStyleSheet(f"font-size:12px;font-weight:600;color:{fg};")
        t0, t1 = row.get("start"), row.get("end")
        time_lbl = (f"{t0:%H:%M}-{t1:%H:%M}" if t0 and t1 else "")
        subl = QLabel(f"{time_lbl}  {row.get('location', '')}")
        subl.setStyleSheet(f"font-size:10px;color:{sub};")
        box = QVBoxLayout()
        box.setSpacing(0)
        box.addWidget(name)
        box.addWidget(subl)
        h.addLayout(box, 1)
        if cur:
            h.addWidget(_MiniBar(int(row.get("progress", 0)),
                                 bar_color="#FFFFFF"))
        elif row.get("state") == "done":
            t = QLabel("✓")
            t.setStyleSheet(f"color:{self.p['green']};")
            h.addWidget(t)
        return w

    # ---------- 交互 ----------

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            self._drag = {"g": e.globalPosition().toPoint(),
                          "w": QPoint(self._pos[0], self._pos[1]),
                          "moved": False}

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if not self._drag:
            return
        d = e.globalPosition().toPoint() - self._drag["g"]
        if d.manhattanLength() > 4:
            self._drag["moved"] = True
        if self._drag["moved"]:
            self._pos = [self._drag["w"].x() + d.x(), self._drag["w"].y() + d.y()]
            self.move(*self._pos)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton and self._drag:
            if not self._drag["moved"]:
                self.toggle_mode()
            else:
                self.save_geometry()
            self._drag = None

    def contextMenuEvent(self, e) -> None:
        m = QMenu(self)
        m.setStyleSheet(qss(self.p, radius=12))
        m.addAction("立即巡检", lambda: self._act("scan_now"))
        m.addAction("打开详情", lambda: self._act("open_detail"))
        m.addSeparator()
        m.addAction("隐藏到托盘", lambda: self._act("hide"))
        m.exec(e.globalPos())

    def toggle_mode(self) -> None:
        """迷你 ↔ 标准 同窗动画（geometry 完整构造防跳位）。"""
        target = FULL if self.mode == "mini" else MINI
        key = "expand" if self.mode == "mini" else "collapse"
        self.mode = "full" if self.mode == "mini" else "mini"
        self._set_full_visible(self.mode == "full")
        geo = QPropertyAnimation(self, b"geometry")
        from ..ui.theme import CURVE
        geo.setDuration(DUR[key])
        geo.setStartValue(QRect(self._pos[0], self._pos[1], self.width(), self.height()))
        geo.setEndValue(QRect(self._pos[0], self._pos[1], *target))
        geo.setEasingCurve(CURVE[key])
        motion.keep_ref(geo)
        geo.start()

    def _act(self, name: str) -> None:
        if self.on_action:
            self.on_action(name)
