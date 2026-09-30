# -*- coding: utf-8 -*-
"""详情窗 QML 桥：时间线/作业看板/设置 读写。

设置保存走 app 注入的回调（校验+落盘+生效链在 python 侧），
QML 只收集字段。
"""
from PySide6.QtCore import QObject, Property, Signal, Slot


class DetailBridge(QObject):
    timelineChanged = Signal()
    hwChanged = Signal()
    tabRequested = Signal(int)        # python → QML：打开时落到指定页
    settingsApplied = Signal(str)     # python → QML：保存结果提示文案

    def __init__(self, parent=None, settings=None, save_cb=None,
                 refresh_hw_cb=None):
        super().__init__(parent)
        self._settings = dict(settings or {})
        self._save_cb = save_cb or (lambda d: None)
        self._refresh_hw_cb = refresh_hw_cb or (lambda: None)
        self._timeline: list = []
        self._hw: list = []
        self._hw_failed = False

    # ---------- 数据注入（app 线程） ----------

    def set_timeline(self, events: list) -> None:
        from assistant.snapshot import course_color
        rows = []
        for e in events[:60]:
            cbg, cfg = course_color(e.get("course", ""))
            rows.append({
                "course": e.get("course", ""),
                "title": e.get("title", ""),
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

    # ---------- QML 属性 ----------

    @Property("QVariantList", notify=timelineChanged)
    def timeline(self): return self._timeline

    @Property("QVariantList", notify=hwChanged)
    def hw(self): return self._hw

    @Property(bool, notify=hwChanged)
    def hwFailed(self): return self._hw_failed

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

    @Slot(int)
    def gotoTab(self, tab: int) -> None:
        self.tabRequested.emit(int(tab))
