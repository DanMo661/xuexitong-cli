# -*- coding: utf-8 -*-
"""动效工具：统一封装 QPropertyAnimation，全局时长/曲线查 theme 表。

用法：animate(widget, b"windowOpacity", 0.0, 1.0, "enter_fade")
"""
from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QObject,
                            QParallelAnimationGroup, QPropertyAnimation)

from .theme import CURVE, DUR


def anim(target: QObject, prop: bytes, start, end, key: str,
         on_finished=None) -> QPropertyAnimation:
    """单属性动画。key 查 theme.DUR/CURVE 表。"""
    a = QPropertyAnimation(target, prop)
    a.setDuration(DUR[key])
    a.setStartValue(start)
    a.setEndValue(end)
    a.setEasingCurve(CURVE[key])
    if on_finished:
        a.finished.connect(on_finished)
    return a


def group(*anims) -> QParallelAnimationGroup:
    g = QParallelAnimationGroup()
    for a in anims:
        g.addAnimation(a)
    return g


def fade_out_and(target: QObject, key: str, done) -> None:
    """淡出后回调（常用于退场后 hide/close）。"""
    a = anim(target, b"windowOpacity", target.windowOpacity(), 0.0, key, done)
    a.start(QAbstractAnimation.DeleteWhenStopped)


def keep_ref(animation) -> None:
    """防动画对象被 GC（PySide6 常见坑：局部变量动画闪没）。"""
    setattr(animation, "_self_ref", animation)
