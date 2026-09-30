# -*- coding: utf-8 -*-
"""R2 视觉验证：作业右键菜单 / 忽略恢复条 / 设置页导出按钮。

store.json 用前备份用后恢复——合成数据绝不留在真实状态库里。
"""
import ctypes
import shutil
import sys
from datetime import datetime, timedelta

sys.path.insert(0, r"D:\Work_Project\ZCodeProject\Xuexitong-mcp")

from PySide6.QtCore import QTimer, QMetaObject  # noqa: E402

from assistant.app import App  # noqa: E402

ROOT = r"D:\Work_Project\ZCodeProject\Xuexitong-mcp"
NOW = datetime.now()


def synth(store):
    store.set_deadlines([
        {"course": "数字图像处理", "title": "实验四 整体调试实验报告",
         "status": "未交", "url": "https://mooc1.chaoxing.com/work/fake1",
         "courseUrl": "", "deadline": None,
         "deadline_dt": NOW + timedelta(days=2)},
        {"course": "机器学习综合设计", "title": "第三周编程作业",
         "status": "未交", "url": "", "courseUrl": "",
         "deadline": None, "deadline_dt": NOW + timedelta(hours=20)},
        {"course": "已线下交的课", "title": "课堂练习（已交纸质版）",
         "status": "未交", "url": "", "courseUrl": "",
         "deadline": None, "deadline_dt": NOW + timedelta(days=5)},
    ])
    store.ignore_hw("已线下交的课", "课堂练习（已交纸质版）")


def main() -> int:
    shutil.copy(ROOT + r"\store.json", ROOT + r"\store.json.r2bak")
    try:
        return _run()
    finally:
        shutil.move(ROOT + r"\store.json.r2bak", ROOT + r"\store.json")
        print("store.json restored")


def _run() -> int:
    app = App(startup_scan=False)
    synth(app.store)
    app._push_all()
    app._refresh_ddl()
    app.widget.show()
    app.qapp.processEvents()

    user32 = ctypes.windll.user32

    def grab_widget(path):
        w = app.widget
        img = w.screen().grabWindow(0, int(w.x()), int(w.y()),
                                    int(w.width()), int(w.height()))
        img.save(path)
        print("saved:", path)

    def grab_detail(path):
        w = app.detail_win
        w.raise_()
        w.requestActivate()
        app.qapp.processEvents()
        m = w.frameMargins()
        img = w.screen().grabWindow(0, int(w.x() - m.left()),
                                    int(w.y() - m.top()),
                                    int(w.width() + m.left() + m.right()),
                                    int(w.height() + m.top() + m.bottom()))
        img.save(path)
        print("saved:", path)

    def rclick(win, lx, ly):
        dpr = win.screen().devicePixelRatio()
        user32.SetCursorPos(int((win.x() + lx) * dpr), int((win.y() + ly) * dpr))
        QTimer.singleShot(150, lambda: user32.mouse_event(0x0008, 0, 0, 0, 0))
        QTimer.singleShot(230, lambda: user32.mouse_event(0x0010, 0, 0, 0, 0))

    step = {"i": 0}

    def next_step():
        i = step["i"]
        step["i"] += 1
        if i == 0:
            QMetaObject.invokeMethod(app.widget, "toggleMode")
            QTimer.singleShot(400, next_step)
        elif i == 1:
            app.bridge.set_tab(2)                    # 小窗作业页
            QTimer.singleShot(500, next_step)
        elif i == 2:
            grab_widget("_r2_mini_hw.png")
            rclick(app.widget, 180, 190)             # 右键第一张作业卡
            QTimer.singleShot(700, next_step)
        elif i == 3:
            grab_widget("_r2_mini_hw_menu.png")
            # 点菜单外关掉
            rclick_off = lambda: (user32.SetCursorPos(20, 500),)
            QTimer.singleShot(80, lambda: user32.mouse_event(0x0002, 0, 0, 0, 0))
            QTimer.singleShot(160, lambda: user32.mouse_event(0x0004, 0, 0, 0, 0))
            QTimer.singleShot(400, next_step)
        elif i == 4:
            app.detail_bridge.gotoTab(1)             # 详情作业页
            app.detail_win.show()
            app.detail_win.raise_()
            QTimer.singleShot(600, next_step)
        elif i == 5:
            grab_detail("_r2_det_hw.png")
            app.detail_bridge.gotoTab(4)             # 设置页
            QTimer.singleShot(500, next_step)
        else:
            grab_detail("_r2_det_set.png")
            QTimer.singleShot(300, app.quit)

    QTimer.singleShot(2500, next_step)
    return app.qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
