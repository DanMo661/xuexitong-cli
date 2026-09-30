# -*- coding: utf-8 -*-
"""R1 视觉验证：合成考试/通知/任务点数据 → 小窗 t0 + 详情窗 t2/t3 截图。"""
import sys
from datetime import datetime, timedelta

sys.path.insert(0, r"D:\Work_Project\ZCodeProject\Xuexitong-mcp")

from PySide6.QtCore import QTimer, QMetaObject, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from assistant.app import App  # noqa: E402
from assistant.snapshot import parse_exam_rows  # noqa: E402

NOW = datetime.now()
FMT = "%Y-%m-%d %H:%M"


def synth(store):
    raw = [
        ["x", "数字图像处理期末考试",
         (NOW + timedelta(days=2)).strftime(FMT) + " 至 "
         + (NOW + timedelta(days=2, hours=2)).strftime(FMT),
         "120", "未开始", "未交", "---", "学习通", "x"],
        ["x", "机器学习综合设计验收",
         (NOW + timedelta(days=12)).strftime(FMT) + " 至 "
         + (NOW + timedelta(days=12, hours=1)).strftime(FMT),
         "60", "未开始", "未交", "---", "未设置终端", "x"],
        ["x", "马克思主义基本原理模拟测试",
         "2026-06-22 14:39 至 2026-06-22 15:39",
         "60", "已结束", "未交", "---", "未设置终端", "x"],
    ]
    store.set_exams(parse_exam_rows(raw))
    store.set_notices([
        {"title": "关于2026年国庆节放假安排的通知", "sender": "教务处",
         "time": "2026-09-28 16:20", "isread": 0,
         "content": "根据国务院办公厅通知精神，结合学校实际，现将国庆节放假安排通知如下……"},
        {"title": "实验四报告提交提醒", "sender": "黄一桂",
         "time": "2026-09-27 09:10", "isread": 0,
         "content": "请各位同学于本周日前提交实验四整体调试实验报告。"},
        {"title": "课堂签到统计", "sender": "学习通知",
         "time": "2026-09-25 10:00", "isread": 1, "content": "已完成签到。"},
    ])
    store.set_progress([
        {"course": "数字图像处理", "done": 8, "total": 10, "error": None},
        {"course": "机器学习综合设计", "done": 3, "total": 9, "error": None},
        # 课名必须落在真实学期课表里（progress_view 会按活跃课过滤）
        {"course": "数字信号处理", "done": 10, "total": 10, "error": None},
        {"course": "毛泽东思想", "done": None, "total": None, "error": "无进度数据"},
    ])
    store.set_deadlines([
        {"course": "数字图像处理", "title": "实验四 整体调试实验报告",
         "status": "未交",
         "deadline": (NOW + timedelta(days=2)).strftime("%m-%d %H:%M"),
         "deadline_dt": NOW + timedelta(days=2)},
    ])


def main() -> int:
    app = App(startup_scan=False)
    synth(app.store)
    app._push_all()
    app._push_extras()
    app.widget.show()

    qapp = app.qapp
    app.detail_win.setPosition(260, 160)
    # 置顶保证屏幕合成抓取不被桌面其他窗口盖住
    app.detail_win.setFlags(app.detail_win.flags() | Qt.WindowStaysOnTopHint)
    app.detail_win.show()
    app.detail_win.raise_()
    app.detail_win.requestActivate()
    qapp.processEvents()

    def grab_widget(path):
        w = app.widget
        img = w.screen().grabWindow(0, int(w.x()), int(w.y()),
                                    int(w.width()), int(w.height()))
        img.save(path)
        print("saved:", path)

    def grab_detail(path):
        w = app.detail_win
        # 屏幕合成抓取（离屏 grabWindow 在 QML 页面下会拿到空帧）；
        # 抓前 raise+activate 保证不被桌面其他窗口（如 EDA）盖住
        w.raise_()
        w.requestActivate()
        qapp.processEvents()
        m = w.frameMargins() if hasattr(w, "frameMargins") else None
        l, t = (m.left(), m.top()) if m else (0, 31)
        r, b = (m.right(), m.bottom()) if m else (7, 7)
        img = w.screen().grabWindow(0, int(w.x() - l), int(w.y() - t),
                                    int(w.width() + l + r),
                                    int(w.height() + t + b))
        img.save(path)
        print("saved:", path)

    def step(i):
        if i == 0:
            QMetaObject.invokeMethod(app.widget, "toggleMode")
            QTimer.singleShot(400, lambda: step(1))
        elif i == 1:
            app.bridge.set_tab(0)
            QTimer.singleShot(400, lambda: (grab_widget("_r1_mini_t0.png"), step(2)))
        elif i == 2:
            app.detail_bridge.gotoTab(2)   # 考试页
            QTimer.singleShot(400, lambda: (grab_detail("_r1_det_t2.png"), step(3)))
        elif i == 3:
            app.detail_bridge.gotoTab(3)   # 通知页
            QTimer.singleShot(400, lambda: (grab_detail("_r1_det_t3.png"), step(4)))
        else:
            app.quit()
            return

    QTimer.singleShot(2500, lambda: step(0))
    return qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
