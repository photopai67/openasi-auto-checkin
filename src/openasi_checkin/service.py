"""Shared foreground/background operations; no UI imports or print calls."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler

from .api import OpenASIClient, OpenASIError
from .storage import AppStore, validate_account


ERROR_MESSAGES = {
    "INVALID_EMAIL_OR_PASSWORD": "邮箱或密码错误，请重新输入。",
    "EMAIL_NOT_VERIFIED": "邮箱尚未验证，请先完成 OpenASI 邮箱验证。",
    "UNAUTHORIZED": "登录认证失效，请检查账号密码并重新测试登录。",
    "TOO_MANY_ATTEMPTS": "登录尝试过于频繁，请稍后重试。",
    "NETWORK_ERROR": "服务器暂时无法响应，请稍后重试。",
}


def safe_message(message: str, *secrets: str) -> str:
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        message = message.replace(secret, "[已隐藏]")
    message = re.sub(r"(?i)bearer\s+\S+", "Bearer [已隐藏]", message)
    message = re.sub(r"[^\s@]+@[^\s@]+\.[^\s@]+", "[邮箱已隐藏]", message)
    return message.replace("\r", " ").replace("\n", " ")[:500]


def friendly_error(exc: Exception, *secrets: str) -> str:
    if isinstance(exc, OpenASIError):
        message = ERROR_MESSAGES.get(exc.code, str(exc))
    elif isinstance(exc, OSError):
        message = "本地文件访问失败，请检查用户目录的权限或文件占用。"
    else:
        message = f"运行异常（{type(exc).__name__}），请重新打开配置窗口重试。"
    return safe_message(message, *secrets)


@dataclass(frozen=True)
class RunRecord:
    status: str
    message: str
    finished_at: str
    source: str

    @property
    def ok(self) -> bool:
        return self.status != "failed"


def record_result(store: AppStore, record: RunRecord) -> None:
    store.write_json("last_run.json", asdict(record))
    handler = RotatingFileHandler(
        store.directory / "checkin.log", maxBytes=256_000, backupCount=2, encoding="utf-8",
    )
    try:
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger = logging.Logger("openasi-checkin", level=logging.INFO)
        logger.addHandler(handler)
        logger.info("[%s] %s: %s", record.source, record.status, record.message)
    finally:
        handler.close()


def test_login(email: str, password: str) -> str:
    email = validate_account(email, password)
    client = OpenASIClient()
    client.login(email, password)
    # Queries status as well, to validate access without submitting a check-in.
    result = client.checkin_result(dry_run=True)
    return f"登录成功。{result.message}"


def run_checkin(
    store: AppStore, *, source: str = "automatic", account: tuple[str, str] | None = None,
) -> RunRecord:
    email = password = ""
    client = OpenASIClient()
    try:
        email, password = account if account is not None else store.credentials()
        email = validate_account(email, password)
        client.login(email, password)
        result = client.checkin_result()
        status, message = result.status, safe_message(result.message, email, password, client.token or "")
    except Exception as exc:
        status = "failed"
        message = friendly_error(exc, email, password, client.token or "")
    record = RunRecord(status, message, datetime.now().astimezone().isoformat(timespec="seconds"), source)
    record_result(store, record)
    return record
