"""Windows Task Scheduler integration with hidden, non-interactive helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .api import OpenASIError
from .storage import AppStore, validate_time


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def pythonw_path() -> Path:
    # Keep the virtual environment's interpreter rather than resolving its link.
    path = Path(sys.executable).absolute().with_name("pythonw.exe")
    if not path.is_file():
        raise OpenASIError("没有找到 pythonw.exe，请安装包含 Tkinter 的 Windows Python。")
    return path


def _run_powershell(script: str) -> str:
    if os.name != "nt":
        raise OpenASIError("Windows 自动签到仅支持 Windows。")
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / (
        "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    prefix = ("$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
              "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); ")
    # Catch in the helper to avoid CLIXML diagnostics leaking into the UI.
    wrapped = prefix + "try { " + script + " } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }"
    encoded = base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    try:
        result = subprocess.run(
            [str(executable), "-NoLogo", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-OutputFormat", "Text", "-EncodedCommand", encoded],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", timeout=45, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OpenASIError("无法连接 Windows 任务计划服务，请稍后重试。") from exc
    if result.returncode:
        # Helpers do not receive any account credentials. Keep errors compact.
        detail = result.stderr.strip().splitlines()
        reason = detail[0][:240] if detail else f"退出码 {result.returncode}"
        raise OpenASIError(f"计划任务操作失败：{reason}")
    return result.stdout.strip()


class TaskScheduler:
    def __init__(self, store: AppStore) -> None:
        self.store = store
        identity = str(store.directory.resolve()).casefold().encode("utf-8")
        self.task_name = "OpenASI-Checkin-" + hashlib.sha256(identity).hexdigest()[:12]

    def _task_lookup(self) -> str:
        name = _ps_literal(self.task_name)
        return (
            f"$name={name}; "
            "$task=Get-ScheduledTask -TaskPath '\\' -ErrorAction Stop | "
            "Where-Object {$_.TaskName -eq $name} | Select-Object -First 1; "
        )

    def launch_action(self) -> tuple[str, str, str]:
        """Only pythonw + the background entry; never the GUI, cmd, or a bat."""
        executable = pythonw_path()
        source_root = Path(__file__).resolve().parents[2]
        background = source_root / "background.pyw"
        if background.is_file():
            arguments = [str(background), "--data-dir", str(self.store.directory.resolve()), "--scheduled"]
            working = source_root
        else:
            arguments = ["-m", "openasi_checkin.worker", "--data-dir",
                         str(self.store.directory.resolve()), "--scheduled"]
            working = self.store.directory.resolve()
        return str(executable), subprocess.list2cmdline(arguments), str(working)

    def registration_script(self, at: str) -> str:
        at = validate_time(at)
        executable, arguments, working = self.launch_action()
        return (
            f"$name={_ps_literal(self.task_name)}; "
            "$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
            f"$action=New-ScheduledTaskAction -Execute {_ps_literal(executable)} "
            f"-Argument {_ps_literal(arguments)} -WorkingDirectory {_ps_literal(working)}; "
            f"$daily=New-ScheduledTaskTrigger -Daily -At {_ps_literal(at)}; "
            "$logon=New-ScheduledTaskTrigger -AtLogOn -User $sid; "
            "$principal=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited; "
            "$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable "
            "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
            "-ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew "
            "-RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15); "
            "Register-ScheduledTask -TaskName $name -TaskPath '\\' -Action $action "
            "-Trigger @($daily,$logon) -Principal $principal -Settings $settings "
            "-Description 'OpenASI daily check-in (pythonw, no windows or notifications)' "
            "-Force | Out-Null; 'OK'"
        )

    def enable(self, at: str) -> None:
        if _run_powershell(self.registration_script(at)) != "OK":
            raise OpenASIError("任务未成功启用，请重新尝试。")

    def disable(self) -> None:
        _run_powershell(self._task_lookup() + (
            "if($task){$task | Disable-ScheduledTask | Out-Null}; 'OK'"
        ))

    def status(self) -> dict[str, Any]:
        output = _run_powershell(self._task_lookup() + (
            "if(-not $task){@{exists=$false} | ConvertTo-Json -Compress; exit}; "
            "$info=$task | Get-ScheduledTaskInfo; "
            "$daily=$task.Triggers | Where-Object {$_.CimClass.CimClassName -eq 'MSFT_TaskDailyTrigger'} "
            "| Select-Object -First 1; "
            "@{exists=$true; state=[string]$task.State; "
            "at=if($daily){([datetime]$daily.StartBoundary).ToString('HH:mm')}else{''}; "
            "next_run=if($info.NextRunTime.Year -gt 2000){$info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss')}else{''}; "
            "last_result=$info.LastTaskResult} | ConvertTo-Json -Compress"
        ))
        try:
            value = json.loads(output)
        except ValueError as exc:
            raise OpenASIError("无法读取计划任务状态。") from exc
        if not isinstance(value, dict):
            raise OpenASIError("计划任务状态格式异常。")
        return value
