# -*- coding: utf-8 -*-
"""统一的数据目录定位：XXT_HOME 环境变量 > PyInstaller exe 目录 > 源码仓库根。"""
import os
import sys
from pathlib import Path


def find_root() -> Path:
    env = os.environ.get("XXT_HOME")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):   # PyInstaller 打包形态
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = find_root()
