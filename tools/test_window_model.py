# -*- coding: utf-8 -*-
"""窗口互斥模型端到端验证（非 pytest：需要真 QApplication 跑事件循环）。

场景：
  1. 启动 App（不巡检），小窗可见
  2. show_detail() → 小窗应隐藏、详情窗可见
  3. 模拟详情窗退场（requestClose 播完）→ 小窗应恢复
  4. 再开详情后把小窗藏进托盘（hide），再关详情 → 小窗保持隐藏
  5. toggle_widget 在详情在场时应收起详情并显示小窗
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer, QMetaObject  # noqa: E402

from assistant.app import App  # noqa: E402

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


app = App(startup_scan=False)
app.widget.show()

STEPS = []


def step_open():
    app.show_detail()
    QTimer.singleShot(400, step_after_open)


def step_after_open():
    check("开详情后小窗隐藏", not app.widget.isVisible())
    check("详情窗可见", app.detail_win.isVisible())
    QTimer.singleShot(50, step_close)


def step_close():
    QMetaObject.invokeMethod(app.detail_win, "requestClose")
    QTimer.singleShot(400, step_after_close)


def step_after_close():
    check("关详情后小窗恢复", app.widget.isVisible())
    check("详情窗已隐藏", not app.detail_win.isVisible())
    QTimer.singleShot(50, step_tray_hidden)


def step_tray_hidden():
    app.widget.hide()          # 用户把小窗藏进托盘
    app.show_detail()
    QTimer.singleShot(400, step_close_tray)


def step_close_tray():
    check("再开详情后小窗仍隐藏", not app.widget.isVisible())
    QMetaObject.invokeMethod(app.detail_win, "requestClose")
    QTimer.singleShot(400, step_after_close_tray)


def step_after_close_tray():
    check("托盘态关详情不弹小窗", not app.widget.isVisible())
    QTimer.singleShot(50, step_toggle)


def step_toggle():
    app.show_detail()
    QTimer.singleShot(400, step_toggle_2)


def step_toggle_2():
    app.toggle_widget()        # 详情在场时按热键
    QTimer.singleShot(400, step_toggle_3)


def step_toggle_3():
    check("热键在详情在场时=收详情回小窗", app.widget.isVisible()
          and not app.detail_win.isVisible())
    print("RESULT:", "ALL PASS" if not FAILS else f"{len(FAILS)} FAIL")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1 if FAILS else 0)


QTimer.singleShot(1200, step_open)
app.qapp.exec()
