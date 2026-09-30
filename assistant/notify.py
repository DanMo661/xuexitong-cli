# -*- coding: utf-8 -*-
"""通知通道：Windows Toast（windows-toasts 优先，winotify 回退）+ 可选邮件。

优先级路由：
  high   → Toast 横幅（进通知中心）+ 应用内未读
  medium → 应用内未读（不弹横幅）
  low    → 只进时间线
"""
import logging
import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText

log = logging.getLogger("notify")

APP_ID = "XuexitongAssistant.WyuStudent"   # 固定 AUMID，打包挪位置也不变


def ensure_aumid_registered() -> None:
    """Toast 横幅挂在开始菜单注册过的 AUMID 上，归属才可靠。

    用 WScript.Shell 建 .lnk + propsys 写 System.AppUserModel.ID
    （pywin32 正规姿势）。已注册过则直接返回；失败静默降级——
    windows-toasts 自带兜底 AUMID，只是归属显示不完美。
    """
    lnk_dir = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs")
    lnk = os.path.join(lnk_dir, "学习通小助手.lnk")
    if os.path.exists(lnk):
        return
    try:
        import pythoncom
        from win32com.propsys import propsys
        from win32com.shell import shell, shellcon
        target = os.path.abspath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "学习通小助手.bat"))
        if not os.path.exists(target):
            return
        os.makedirs(lnk_dir, exist_ok=True)
        pythoncom.CoInitialize()
        try:
            from win32com.shell import shell as _sh
            # 建 .lnk（IShellLink + IPersistFile）
            ws = pythoncom.CoCreateInstance(
                _sh.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                _sh.IID_IShellLink)
            persist = ws.QueryInterface(pythoncom.IID_IPersistFile)
            ws.SetPath(target)
            ws.SetDescription("学习通桌面助手")
            persist.Save(lnk, True)
            # 对 .lnk 路径取 IShellItem → property store 写 System.AppUserModel.ID
            item = _sh.SHCreateItemFromParsingName(lnk, None,
                                                   _sh.IID_IShellItem)
            ps2 = item.BindToHandler(None, _sh.BHID_PropertyStore,
                                     propsys.IID_IPropertyStore)
            pkey = propsys.PSGetPropertyKeyFromName("System.AppUserModel.ID")
            ps2.SetValue(pkey, propsys.PROPVARIANTType(APP_ID, 31))  # 31=VT_LPWSTR
            ps2.Commit()
        finally:
            pythoncom.CoUninitialize()
        log.info("AUMID 已注册：%s", lnk)
    except Exception as e:
        log.debug("AUMID 注册降级（Toast 仍可用）：%s", e)


class Notifier:
    def __init__(self, settings: dict):
        self.settings = settings or {}
        self._toasts = None          # WindowsToaster（不可点击，轻）
        self._itoasts = None         # InteractableWindowsToaster（带回调，重）

    # ---------- 路由 ----------

    def notify_events(self, events: list) -> None:
        highs = [e for e in events if e.get("priority") == "high"]
        if not highs:
            return
        self.toast_summary(highs)
        if self.settings.get("email_enabled"):
            self.send_email(highs)

    # ---------- Windows Toast（双后端） ----------

    def _plain_toast(self, title: str, body: str) -> bool:
        """无按钮横幅。windows-toasts 1.3 的 API：Toast.text_fields 列表
        （0.x 的 ToastText2 类已移除，别再 import）。"""
        try:
            from windows_toasts import Toast, WindowsToaster
            if self._toasts is None:
                self._toasts = WindowsToaster(APP_ID)
            t = Toast()
            t.text_fields = [title, body.replace("\n", "  ")]
            self._toasts.show_toast(t)
            return True
        except Exception as e:
            log.debug("windows-toasts 失败：%s", e)
            return False

    def _clickable_toast(self, title: str, body: str,
                         on_click, click_arg: str) -> bool:
        """带「查看」按钮的横幅；点正文或按钮都触发 on_click(click_arg)。

        回调在 windows-toasts 的监听线程里跑，on_click 必须线程安全
        （调用方用 Qt 信号转发回 UI 线程）。"""
        try:
            from windows_toasts import (InteractableWindowsToaster, Toast,
                                        ToastButton)
            if self._itoasts is None:
                # 1.3.x：直接构造即用（2.x 才有 context manager，别乱加）。
                # notifierAUMID 必须显式给：默认落在 cmd.exe 上，
                # 通知中心和横幅的归属会显示成 Windows Command Processor
                self._itoasts = InteractableWindowsToaster(APP_ID,
                                                           notifierAUMID=APP_ID)
            t = Toast()
            t.text_fields = [title, body.replace("\n", "  ")]

            def _activated(args, cb=on_click, arg=click_arg):
                try:
                    cb(arg)
                except Exception:
                    log.debug("Toast 点击回调失败", exc_info=True)

            t.on_activated = _activated
            t.AddAction(ToastButton(content="查看", arguments="view"))
            self._itoasts.show_toast(t)
            return True
        except Exception as e:
            log.debug("可点击 Toast 失败（退普通横幅）：%s", e)
            return False

    def _toast_winotify(self, title: str, body: str) -> bool:
        try:
            from winotify import Notification, audio
            t = Notification(app_id="学习通小助手", title=title, msg=body,
                             duration="short")
            t.set_audio(audio.Default, loop=False)
            t.show()
            return True
        except Exception as e:
            log.debug("winotify 失败：%s", e)
            return False

    def toast_summary(self, events: list) -> None:
        if not self.settings.get("toast_enabled", True):
            return
        ensure_aumid_registered()
        n = len(events)
        title = f"学习通有 {n} 条新动态" if n > 1 else "学习通新动态"
        lines = [f"【{e.get('tag', '')}】{e.get('course', '')} {e.get('title', '')}"
                 for e in events[:4]]
        body = "\n".join(lines) + ("…" if n > 4 else "")
        if not self._toast_windows_toasts(title, body):
            self._toast_winotify(title, body)

    def toast_text(self, title: str, body: str,
                   on_click=None, click_arg: str = "") -> None:
        if not self.settings.get("toast_enabled", True):
            return
        ensure_aumid_registered()
        if on_click is not None and self._clickable_toast(
                title, body, on_click, click_arg):
            return
        if not self._plain_toast(title, body):
            self._toast_winotify(title, body)

    # 兼容旧调用名（watch CLI 等处）
    _toast_windows_toasts = _plain_toast

    # ---------- 邮件（可选） ----------

    def send_email(self, events: list) -> None:
        cfg = self.settings
        host = cfg.get("smtp_host", "")
        user = cfg.get("smtp_user", "")
        pwd = cfg.get("smtp_pass", "")
        to = cfg.get("email_to", "")
        if not all([host, user, pwd, to]):
            log.info("邮件未配置完整，跳过")
            return
        lines = [f"【{e.get('tag')}】{e.get('course')} — {e.get('title')}"
                 + (f"\n  {e.get('detail')}" if e.get("detail") else "")
                 for e in events]
        msg = MIMEText("\n\n".join(lines), "plain", "utf-8")
        msg["Subject"] = Header(f"学习通提醒：{len(events)} 条新动态", "utf-8")
        msg["From"] = user
        msg["To"] = to
        cls = smtplib.SMTP_SSL if cfg.get("smtp_ssl", True) else smtplib.SMTP
        try:
            with cls(host, cfg.get("smtp_port", 465), timeout=15) as s:
                s.login(user, pwd)
                s.sendmail(user, [to], msg.as_string())
            log.info("提醒邮件已发 %s", to)
        except Exception as e:
            log.warning("邮件发送失败：%s", e)
