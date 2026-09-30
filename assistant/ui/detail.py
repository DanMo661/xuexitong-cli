# -*- coding: utf-8 -*-
"""设置存取与开机自启助手（详情窗本体已迁 QML：DetailWindow.qml）。"""
import json
import os
import winreg


from assistant.paths import ROOT
SETTINGS_FILE = os.path.join(ROOT, "settings.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_NAME = "XuexitongAssistant"

DEFAULTS = {"theme": "light", "scan_interval_min": 30,
            "dnd": "23:00-07:30", "toast_enabled": True,
            "email_enabled": False, "autostart": False,
            "smtp_host": "", "smtp_user": "", "smtp_pass": "",
            "smtp_port": 465, "smtp_ssl": True, "email_to": ""}


def load_settings() -> dict:
    d = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            d.update(json.load(f))
    except Exception:
        pass
    return d


def save_settings(d: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, APP_REG_NAME)[0] if \
                winreg.QueryValue(k, APP_REG_NAME) else True
    except OSError:
        return False


def set_autostart(on: bool, exe: str = "") -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            if on:
                # 优先 pythonw 直启：走 bat 会先起 cmd（开机闪黑框，
                # venv 丢失时还会卡住一个带 pause 的黑窗）
                pw = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
                if exe:
                    val = exe
                elif os.path.exists(pw):
                    val = f'"{pw}" "{os.path.join(ROOT, "assistant", "app.py")}"'
                else:
                    val = f'"{os.path.join(ROOT, "学习通小助手.bat")}"'
                winreg.SetValueEx(k, APP_REG_NAME, 0, winreg.REG_SZ, val)
            else:
                try:
                    winreg.DeleteValue(k, APP_REG_NAME)
                except OSError:
                    pass
    except OSError:
        pass
