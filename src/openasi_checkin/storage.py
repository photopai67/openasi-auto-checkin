"""Atomic per-user configuration and run history, outside the source tree."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .api import OpenASIError
from .security import protect_password, unprotect_password


def validate_time(value: str) -> str:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise OpenASIError("签到时间应为 HH:MM，例如 08:05。")
    return value


def validate_account(email: str, password: str) -> str:
    email = email.strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise OpenASIError("请输入有效的邮箱地址。")
    if not password:
        raise OpenASIError("请输入密码。")
    return email


def default_data_dir() -> Path:
    if os.name != "nt" or not os.getenv("LOCALAPPDATA"):
        raise OpenASIError("Windows 图形版需要可用的 LOCALAPPDATA 用户目录。")
    return Path(os.environ["LOCALAPPDATA"]) / "OpenASICheckin"


@dataclass(frozen=True)
class Settings:
    email: str = ""
    encrypted_password: str = ""
    at: str = "08:05"


class AppStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else default_data_dir()

    def read_json(self, name: str) -> dict[str, Any]:
        path = self.directory / name
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            raise OpenASIError(f"无法读取 {name}，请检查文件是否损坏或被占用。") from exc
        if not isinstance(value, dict):
            raise OpenASIError(f"{name} 格式错误。")
        return value

    def write_json(self, name: str, value: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / name)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def load_settings(self) -> Settings:
        value = self.read_json("settings.json")
        fields = {name: value.get(name, default) for name, default in (
            ("email", ""), ("encrypted_password", ""), ("at", "08:05"),
        )}
        if not all(isinstance(item, str) for item in fields.values()):
            raise OpenASIError("账号配置格式错误，请重新保存。")
        validate_time(fields["at"])
        return Settings(**fields)

    def save_account(self, email: str, password: str, at: str) -> Settings:
        email = validate_account(email, password)
        at = validate_time(at)
        settings = Settings(email, protect_password(password), at)
        self.write_json("settings.json", {"schema_version": 1, **asdict(settings)})
        return settings

    def credentials(self) -> tuple[str, str]:
        settings = self.load_settings()
        if not settings.email or not settings.encrypted_password:
            raise OpenASIError("请先打开配置窗口，输入邮箱和密码并保存。")
        return settings.email, unprotect_password(settings.encrypted_password)

    def read_log(self) -> str:
        try:
            return (self.directory / "checkin.log").read_text(encoding="utf-8")[-24000:]
        except FileNotFoundError:
            return "尚无运行日志。"
