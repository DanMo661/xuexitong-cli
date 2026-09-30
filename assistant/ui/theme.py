# -*- coding: utf-8 -*-
"""UI 主题：Fluent 2 配色（亮/暗/跟随系统）+ 全局动效参数表。

动效参数摘自 Class-Widgets 源码实测与 Win11 官方动效规范：
  进场 600ms 方向感知滑入（OutBack）+ 淡入 450ms（OutCubic）
  退场 400ms（InOutQuad），位移退场必须叠淡出
  尺寸切换 450-600ms（InOutCirc 收缩 / OutCubic 展开）
  数字刷新 83ms 交叉淡入
  悬停反馈 167ms
硬规则：退场永远比进场短。
"""
from PySide6.QtCore import QEasingCurve
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

# ---------- 动效参数表（ms + 缓动） ----------
DUR = {
    "enter_slide": 600,     # 悬浮窗进场滑入
    "enter_fade": 450,      # 进场淡入
    "exit": 400,            # 退场（必须 < 进场）
    "expand": 500,          # 展开（迷你↔标准）
    "collapse": 450,        # 收缩
    "num_swap": 83,         # 数字刷新交叉淡入
    "hover": 167,           # 悬停反馈
    "page": 250,            # 页面切换
}
CURVE = {
    "enter_slide": QEasingCurve.OutBack,
    "enter_fade": QEasingCurve.OutCubic,
    "exit": QEasingCurve.InOutQuad,
    "expand": QEasingCurve.OutCubic,
    "collapse": QEasingCurve.InOutCirc,
    "page": QEasingCurve.OutCubic,
    "hover": QEasingCurve.OutCubic,
}

# ---------- 配色（亮=cc-switch 浅色 tokens；暗=cc-switch .dark 分支） ----------
LIGHT = {
    "bg": "#F7F7F8",           # 窗底（cc secondary）
    "card": "#FFFFFF",         # 卡片
    "card_hover": "#FAFAFB",
    "border": "#E4E4E7",       # 1px 边框
    "fg": "#0A0A0B",           # 主文字
    "fg_sub": "#6E6E76",       # 次级文字
    "fg_weak": "#A0A0A6",
    "accent": "#1F8FFF",       # cc-switch light primary（210 100% 56%）
    "green": "#16A34A",
    "red": "#EF4444",
    "orange": "#C97A16",
    "purple": "#7A5FD8",       # 预备/即将截止
    "mask": "#000000",         # 遮罩基色（配合透明度）
    "stripe": "#1F8FFF",       # 品牌色条
}

# cc-switch 源码色板（zinc 灰阶 + 210° 单一蓝强调）
DARK = {
    "bg": "#1D1D21",
    "card": "#29272B",
    "card_hover": "#2E2C30",
    "border": "#3C3A40",
    "fg": "#FAFAFA",
    "fg_sub": "#A1A1AA",
    "fg_weak": "#71717A",
    "accent": "#148AFF",
    "green": "#22C55E",
    "red": "#EF4444",
    "orange": "#EAB308",
    "purple": "#A29BFE",
    "mask": "#000000",
    "stripe": "#148AFF",
}


def system_prefers_dark() -> bool:
    """读注册表判断系统深色模式（Win10 1809+）。"""
    try:
        from PySide6.QtCore import QSettings
        s = QSettings(r"HKEY_CURRENT_USER\Software\Microsoft\Windows"
                      r"\CurrentVersion\Themes\Personalize", QSettings.NativeFormat)
        return int(s.value("AppsUseLightTheme", 1)) == 0
    except Exception:
        return False


def palette(mode: str = "auto") -> dict:
    """mode: light / dark / auto（跟随系统）。"""
    if mode == "auto":
        mode = "dark" if system_prefers_dark() else "light"
    return DARK if mode == "dark" else LIGHT


def qss(p: dict, radius: int = 8) -> str:
    """全局样式表。radius 卡片 8 / 悬浮条 10 / 弹窗 12 三档由调用方传入。"""
    return f"""
    QWidget {{ color: {p['fg']}; font-family: "Microsoft YaHei UI", "Microsoft YaHei"; }}
    QLabel#weak {{ color: {p['fg_sub']}; }}
    QLabel#strong {{ color: {p['fg']}; font-weight: 600; }}
    QFrame#card {{
        background: {p['card']}; border: 1px solid {p['border']};
        border-radius: {radius}px;
    }}
    QFrame#cardHover:hover {{ background: {p['card_hover']}; }}
    QPushButton#ghost {{
        background: transparent; border: none; border-radius: 6px;
        padding: 4px 10px; color: {p['fg_sub']};
    }}
    QPushButton#ghost:hover {{ background: {p['card_hover']}; color: {p['fg']}; }}
    QProgressBar {{
        background: {p['border']}; border: none; border-radius: 2px;
        text-align: center; color: transparent; max-height: 4px;
    }}
    QProgressBar::chunk {{ background: {p['accent']}; border-radius: 2px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: {p['border']}; border-radius: 3px; min-height: 30px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{
        padding: 6px 16px; color: {p['fg_sub']}; background: transparent;
        border: none; border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{ color: {p['fg']}; border-bottom: 2px solid {p['accent']}; }}
    QLineEdit, QSpinBox, QComboBox {{
        background: {p['card']}; border: 1px solid {p['border']};
        border-radius: 6px; padding: 5px 8px; color: {p['fg']};
    }}
    QLineEdit:focus {{ border-color: {p['accent']}; }}
    QCheckBox {{ spacing: 6px; }}
    """


def with_alpha(color_hex: str, alpha: int) -> QColor:
    """#RRGGBB + 透明度（0-255）。"""
    c = QColor(color_hex)
    c.setAlpha(alpha)
    return c
