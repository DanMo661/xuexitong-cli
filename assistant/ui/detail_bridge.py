# -*- coding: utf-8 -*-
"""详情窗 QML 桥：时间线/作业看板/设置 读写。

设置保存走 app 注入的回调（校验+落盘+生效链在 python 侧），
QML 只收集字段。
"""
from PySide6.QtCore import QObject, Property, Signal, Slot


class DetailBridge(QObject):
    timelineChanged = Signal()
    hwChanged = Signal()
    examsChanged = Signal()           # 考试看板（含任务点进度区）
    noticesChanged = Signal()         # 通知中心列表
    tabRequested = Signal(int)        # python → QML：打开时落到指定页
    settingsApplied = Signal(str)     # python → QML：保存结果提示文案
    refreshingChanged = Signal()      # 手动刷新进行中（⟳ 旋转反馈）
    hwOpenRequested = Signal(str, str, str)   # url, course, title → app
    hwIgnoreRequested = Signal(str, str, str)  # course, title, url → app
    unignoreRequested = Signal()              # 清空忽略名单 → app
    icsRequested = Signal()                   # 导出课表 .ics → app
    ignoredChanged = Signal()

    def __init__(self, parent=None, settings=None, save_cb=None,
                 refresh_hw_cb=None, refresh_extra_cb=None,
                 notice_read_cb=None):
        super().__init__(parent)
        self._settings = dict(settings or {})
        self._save_cb = save_cb or (lambda d: None)
        self._refresh_hw_cb = refresh_hw_cb or (lambda: None)
        self._refresh_extra_cb = refresh_extra_cb or (lambda k: None)
        self._notice_read_cb = notice_read_cb or (lambda k: None)
        self._timeline: list = []
        self._hw: list = []
        self._hw_failed = False
        self._exams: list = []
        self._notices: list = []
        self._progress = {"rows": [], "otherRows": [], "totalLeft": 0,
                          "coursesLeft": 0, "hasData": False, "date": ""}
        self._refreshing = False
        self._ignored_hw = 0

    # ---------- 数据注入（app 线程） ----------

    def set_timeline(self, events: list) -> None:
        from assistant.snapshot import course_color
        rows = []
        for e in events[:60]:
            cbg, cfg = course_color(e.get("course", ""))
            rows.append({
                "course": e.get("course", ""),
                "title": e.get("title", ""),
                "detail": (e.get("detail", "") or "")[:120],
                "tag": e.get("tag", ""),
                "priority": e.get("priority", "low"),
                "time": (e.get("time", "") or "")[5:16].replace("T", " "),
                "cbg": cbg, "cfg": cfg,
            })
        if rows != self._timeline:
            self._timeline = rows
            self.timelineChanged.emit()

    def set_hw(self, items) -> None:
        """items：ddl_view 行列表；None=获取失败。"""
        if items is None:
            self._hw_failed = True
            self._hw = []
        else:
            self._hw_failed = False
            self._hw = items
        self.hwChanged.emit()

    def set_exams(self, rows: list) -> None:
        if rows != self._exams:
            self._exams = rows
            self.examsChanged.emit()

    def set_notices(self, rows: list) -> None:
        if rows != self._notices:
            self._notices = rows
            self.noticesChanged.emit()

    def set_progress(self, d: dict) -> None:
        if d != self._progress:
            self._progress = d
            self.examsChanged.emit()   # 任务点区挂在考试页，共用一个通知

    def set_refreshing(self, on: bool) -> None:
        if on != self._refreshing:
            self._refreshing = on
            self.refreshingChanged.emit()

    def set_hw_ignored(self, n: int) -> None:
        if n != self._ignored_hw:
            self._ignored_hw = n
            self.ignoredChanged.emit()

    # ---------- QML 属性 ----------

    @Property("QVariantList", notify=timelineChanged)
    def timeline(self): return self._timeline

    @Property("QVariantList", notify=hwChanged)
    def hw(self): return self._hw

    @Property(bool, notify=hwChanged)
    def hwFailed(self): return self._hw_failed

    @Property("QVariantList", notify=examsChanged)
    def exams(self): return self._exams

    @Property("QVariantList", notify=noticesChanged)
    def notices(self): return self._notices

    @Property("QVariantMap", notify=examsChanged)
    def progress(self): return self._progress

    @Property(bool, notify=refreshingChanged)
    def refreshing(self): return self._refreshing

    @Property(int, notify=ignoredChanged)
    def hwIgnored(self): return self._ignored_hw

    @Property("QVariantMap", constant=True)
    def settings(self): return self._settings

    # ---------- QML → Python ----------

    @Slot("QVariantMap")
    def saveSettings(self, vals) -> None:
        merged = dict(self._settings)
        merged.update({k: vals.get(k) for k in (
            "theme", "scan_interval_min", "toast_enabled", "dnd",
            "autostart", "email_enabled", "email_to", "smtp_host",
            "smtp_user", "smtp_pass") if k in vals})
        ok, msg = self._save_cb(merged)
        self._settings = merged
        self.settingsApplied.emit(msg or ("已保存" if ok else "保存失败"))

    @Slot()
    def refreshHw(self) -> None:
        self._refresh_hw_cb()

    @Slot(str)
    def refreshExtra(self, kind: str) -> None:
        """kind: exams / exams_progress / notices / progress（worker 取数）。"""
        self.set_refreshing(True)
        self._refresh_extra_cb(str(kind))

    @Slot(str)
    def markNoticeRead(self, key: str) -> None:
        self._notice_read_cb(str(key))

    @Slot(str, str, str)
    def openHw(self, url: str, course: str, title: str) -> None:
        self.hwOpenRequested.emit(url, course, title)

    @Slot(str, str)
    def ignoreHw(self, course: str, title: str) -> None:
        self.hwIgnoreRequested.emit(course, title)

    @Slot()
    def unignoreAll(self) -> None:
        self.unignoreRequested.emit()

    @Slot()
    def exportIcs(self) -> None:
        self.icsRequested.emit()

    @Slot(int)
    def gotoTab(self, tab: int) -> None:
        self.tabRequested.emit(int(tab))
