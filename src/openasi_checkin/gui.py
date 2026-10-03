"""Tkinter configuration UI. Only an explicit user launch loads this module."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from dataclasses import asdict
from tkinter import ttk
from typing import Any, Callable

from . import __version__
from .api import OpenASIError
from .scheduler import TaskScheduler, pythonw_path
from .service import RunRecord, friendly_error, run_checkin, test_login
from .storage import AppStore, validate_account, validate_time


class ConfigurationWindow:
    def __init__(self, root: tk.Tk, store: AppStore | None = None) -> None:
        self.root = root
        self.store = store or AppStore()
        self.scheduler = TaskScheduler(self.store)
        self.busy = False
        self.messages: queue.Queue[tuple[bool, Any]] = queue.Queue()
        self.on_success: Callable[[Any], None] | None = None
        self.controls: list[ttk.Widget] = []
        self.readonly_controls: list[ttk.Widget] = []
        self.email = tk.StringVar()
        self.password = tk.StringVar()
        self.show_password = tk.BooleanVar(value=False)
        self.hour = tk.StringVar(value="08")
        self.minute = tk.StringVar(value="05")
        self.schedule_text = tk.StringVar(value="正在读取自动签到状态…")
        self.next_run_text = tk.StringVar(value="")
        self.last_run_text = tk.StringVar(value="尚未运行")
        self.feedback = tk.StringVar(value="输入账号后，先测试登录，再启用每日签到。")
        self.saved_hint = tk.StringVar(value="密码使用当前 Windows 用户的密钥加密保存。")
        self._build()
        self._load()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._poll)
        self.root.after(150, self.refresh)

    def _build(self) -> None:
        self.root.title(f"OpenASI 自动签到 · {__version__}")
        self.root.geometry("760x700")
        self.root.minsize(680, 670)
        self.root.configure(background="#f3f5f8")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f5f8")
        style.configure("TLabel", background="#f3f5f8", foreground="#182537", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("Sub.TLabel", foreground="#64748b")
        style.configure("Card.TLabelframe", background="white", bordercolor="#dce3ec", relief="solid")
        style.configure("Card.TLabelframe.Label", background="#f3f5f8", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Card.TFrame", background="white")
        style.configure("Card.TLabel", background="white")
        style.configure("Hint.TLabel", background="white", foreground="#64748b", font=("Microsoft YaHei UI", 9))
        style.configure("TEntry", padding=8, font=("Microsoft YaHei UI", 10))
        style.configure("TButton", padding=(12, 8), font=("Microsoft YaHei UI", 10))
        style.configure("Accent.TButton", background="#245de8", foreground="white")
        style.map("Accent.TButton", background=[("active", "#1745b6"), ("disabled", "#9baed9")])
        style.configure("TCheckbutton", background="white", font=("Microsoft YaHei UI", 9))

        # A scrollable page also accommodates small screens and larger DPI fonts.
        canvas = tk.Canvas(self.root, background="#f3f5f8", highlightthickness=0)
        scroll = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        outer = ttk.Frame(canvas, padding=24)
        page = canvas.create_window((0, 0), window=outer, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(page, width=event.width))
        outer.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        self.root.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
        outer.columnconfigure(0, weight=1)
        ttk.Label(outer, text="OpenASI 自动签到", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text="一次配置，每日静默执行。关闭此窗口后，定时任务继续运行。",
                  style="Sub.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 20))

        account = ttk.LabelFrame(outer, text="账号设置", padding=16, style="Card.TLabelframe")
        account.grid(row=2, column=0, sticky="ew")
        account.columnconfigure(1, weight=1)
        ttk.Label(account, text="邮箱", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 16))
        email_entry = ttk.Entry(account, textvariable=self.email)
        email_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(account, text="密码", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 16))
        self.password_entry = ttk.Entry(account, textvariable=self.password, show="*")
        self.password_entry.grid(row=1, column=1, sticky="ew")
        show = ttk.Checkbutton(account, text="显示", variable=self.show_password, command=self._toggle_password)
        show.grid(row=1, column=2, padx=(10, 0))
        self.controls.extend([email_entry, self.password_entry, show])
        ttk.Label(account, textvariable=self.saved_hint, style="Hint.TLabel", wraplength=580).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(10, 12))
        actions = ttk.Frame(account, style="Card.TFrame")
        actions.grid(row=3, column=0, columnspan=3, sticky="w")
        self._button(actions, "测试登录", self.test_account).pack(side="left")
        self._button(actions, "保存账号", self.save_account).pack(side="left", padx=8)
        self._button(actions, "立即签到", self.checkin_now).pack(side="left")

        schedule = ttk.LabelFrame(outer, text="每日自动签到", padding=16, style="Card.TLabelframe")
        schedule.grid(row=3, column=0, sticky="ew", pady=18)
        time_row = ttk.Frame(schedule, style="Card.TFrame")
        time_row.pack(fill="x")
        ttk.Label(time_row, text="每日时间", style="Card.TLabel").pack(side="left", padx=(0, 16))
        for variable, values in ((self.hour, range(24)), (self.minute, range(60))):
            combo = ttk.Combobox(time_row, textvariable=variable, width=4, state="readonly",
                                 values=[f"{number:02d}" for number in values])
            combo.pack(side="left", padx=(0, 6))
            self.readonly_controls.append(combo)
            ttk.Label(time_row, text="时" if variable is self.hour else "分", style="Card.TLabel").pack(
                side="left", padx=(0, 10))
        ttk.Label(time_row, text="本机时间", style="Hint.TLabel").pack(side="left")
        schedule_actions = ttk.Frame(schedule, style="Card.TFrame")
        schedule_actions.pack(fill="x", pady=(14, 10))
        self._button(schedule_actions, "启用 / 更新时间", self.enable, accent=True).pack(side="left")
        self._button(schedule_actions, "停用自动签到", self.disable).pack(side="left", padx=8)
        ttk.Label(schedule, textvariable=self.schedule_text, style="Card.TLabel").pack(anchor="w")
        ttk.Label(schedule, textvariable=self.next_run_text, style="Hint.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(schedule, text="自动执行不打开任何窗口、不弹通知、不抢焦点。需电脑开机且当前用户已登录。",
                  style="Hint.TLabel", wraplength=620).pack(anchor="w", pady=(8, 0))

        status = ttk.LabelFrame(outer, text="运行结果", padding=16, style="Card.TLabelframe")
        status.grid(row=4, column=0, sticky="ew")
        ttk.Label(status, textvariable=self.last_run_text, style="Card.TLabel", wraplength=620).pack(anchor="w")
        status_actions = ttk.Frame(status, style="Card.TFrame")
        status_actions.pack(fill="x", pady=(10, 0))
        self._button(status_actions, "刷新状态", self.refresh).pack(side="left")
        self._button(status_actions, "查看日志", self.show_logs).pack(side="left", padx=8)
        self.feedback_label = ttk.Label(outer, textvariable=self.feedback, wraplength=680)
        self.feedback_label.grid(row=5, column=0, sticky="ew", pady=(16, 0))
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.grid(row=6, column=0, sticky="ew", pady=(8, 0))

    def _button(self, parent: ttk.Widget, label: str, command: Callable[[], None],
                *, accent: bool = False) -> ttk.Button:
        button = ttk.Button(parent, text=label, command=command,
                            style="Accent.TButton" if accent else "TButton")
        self.controls.append(button)
        return button

    def _load(self) -> None:
        try:
            settings = self.store.load_settings()
            self.email.set(settings.email)
            self.hour.set(settings.at[:2])
            self.minute.set(settings.at[3:])
            if settings.encrypted_password:
                self.saved_hint.set("密码已安全保存。留空使用原密码；如需修改，输入新密码。")
            self._render_last_run()
        except Exception as exc:
            self._feedback(friendly_error(exc), error=True)

    def _toggle_password(self) -> None:
        self.password_entry.configure(show="" if self.show_password.get() else "*")

    def _snapshot(self) -> tuple[str, str, str]:
        email, password = self.email.get().strip(), self.password.get()
        if not password:
            settings = self.store.load_settings()
            if email != settings.email:
                raise OpenASIError("更换邮箱后，请重新输入密码。")
            _, password = self.store.credentials()
        email = validate_account(email, password)
        return email, password, validate_time(f"{self.hour.get()}:{self.minute.get()}")

    def _account_job(self, label: str, operation: Callable[[str, str, str], Any],
                     finished: Callable[[Any], None]) -> None:
        try:
            email, password, at = self._snapshot()
        except Exception as exc:
            self._feedback(friendly_error(exc), error=True)
            return
        self._job(label, lambda: operation(email, password, at), finished, secrets=(email, password))

    def _job(self, label: str, operation: Callable[[], Any], finished: Callable[[Any], None],
             *, secrets: tuple[str, ...] = ()) -> None:
        if self.busy:
            return
        self.busy = True
        self.on_success = finished
        for control in self.controls + self.readonly_controls:
            control.configure(state="disabled")
        self._feedback(label)
        self.progress.start(12)

        def execute() -> None:
            try:
                self.messages.put((True, operation()))
            except Exception as exc:
                self.messages.put((False, friendly_error(exc, *secrets)))

        threading.Thread(target=execute, daemon=True).start()

    def _poll(self) -> None:
        try:
            success, result = self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.progress.stop()
            for control in self.controls:
                control.configure(state="normal")
            for control in self.readonly_controls:
                control.configure(state="readonly")
            if success and self.on_success:
                try:
                    self.on_success(result)
                except Exception as exc:
                    self._feedback(friendly_error(exc), error=True)
            else:
                self._feedback(str(result), error=True)
        self.root.after(100, self._poll)

    def _feedback(self, message: str, *, error: bool = False) -> None:
        self.feedback.set(message)
        self.feedback_label.configure(foreground="#b42318" if error else "#245de8")

    def test_account(self) -> None:
        self._account_job("正在测试登录…", lambda email, password, at: test_login(email, password), self._feedback)

    def save_account(self) -> None:
        def save(email: str, password: str, at: str) -> None:
            # Save credentials only; a running task keeps its registered time.
            previous = self.store.load_settings()
            self.store.save_account(email, password, previous.at)
        self._account_job("正在安全保存账号…", save, lambda result: self._saved())

    def _saved(self) -> None:
        self.password.set("")
        self.saved_hint.set("密码已安全保存。留空使用原密码；如需修改，输入新密码。")
        self._feedback("账号已保存。点击“启用 / 更新时间”应用当前选择的签到时间。")

    def checkin_now(self) -> None:
        self._account_job(
            "正在签到…", lambda email, password, at: run_checkin(self.store, source="manual", account=(email, password)),
            self._checkin_finished,
        )

    def _checkin_finished(self, result: RunRecord) -> None:
        self._render_last_run()
        self._feedback(result.message, error=not result.ok)

    def enable(self) -> None:
        def enable_task(email: str, password: str, at: str) -> str:
            pythonw_path()
            test_login(email, password)
            previous = self.store.load_settings()
            self.store.save_account(email, password, at)
            try:
                self.scheduler.enable(at)
            except Exception:
                self.store.write_json("settings.json", {"schema_version": 1, **asdict(previous)})
                raise
            return at

        def done(at: str) -> None:
            self._saved()
            self.schedule_text.set(f"已启用 · 每天 {at} 静默签到")
            self.next_run_text.set("关闭配置窗口后继续生效；修改或移动源码后请重新启用。")
            self._feedback("每日签到已启用，可以关闭配置窗口。")
        self._account_job("正在验证账号并设置每日任务…", enable_task, done)

    def disable(self) -> None:
        def done(result: Any) -> None:
            self.schedule_text.set("自动签到已停用")
            self.next_run_text.set("")
            self._feedback("已停用后续的自动签到任务。")
        self._job("正在停用自动签到…", self.scheduler.disable, done)

    def refresh(self) -> None:
        self._job("正在读取状态…", self.scheduler.status, self._render_schedule)

    def _render_schedule(self, status: dict[str, Any]) -> None:
        if not status.get("exists"):
            self.schedule_text.set("尚未启用自动签到")
        elif status.get("state") == "Disabled":
            self.schedule_text.set("自动签到已停用")
        else:
            running = " · 正在后台运行" if status.get("state") == "Running" else ""
            self.schedule_text.set(f"已启用 · 每天 {status.get('at', '--:--')} 静默签到{running}")
        next_run = status.get("next_run") if status.get("state") != "Disabled" else None
        self.next_run_text.set(f"下次计划：{next_run}" if next_run else "")
        self._render_last_run()
        self._feedback("状态已更新。")

    def _render_last_run(self) -> None:
        record = self.store.read_json("last_run.json")
        if record:
            when = str(record.get("finished_at", "")).replace("T", " ")
            self.last_run_text.set(f"{when}\n{record.get('message', '')}")
        else:
            self.last_run_text.set("尚未运行。可以先点击“测试登录”或“立即签到”。")

    def show_logs(self) -> None:
        try:
            content = self.store.read_log()
        except Exception as exc:
            self._feedback(friendly_error(exc), error=True)
            return
        window = tk.Toplevel(self.root)
        window.title("OpenASI 运行日志")
        window.geometry("740x450")
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="word", font=("Microsoft YaHei UI", 10))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        text.insert("1.0", content)
        text.configure(state="disabled")
        text.see("end")

    def close(self) -> None:
        if self.busy:
            self._feedback("操作正在执行，请完成后关闭窗口。")
            return
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    if os.name != "nt":
        root.destroy()
        raise OpenASIError("图形配置版仅支持 Windows。")
    ConfigurationWindow(root)
    root.deiconify()
    root.mainloop()
    return 0
