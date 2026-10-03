"""Small dependency-free client for the OpenASI web API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = "https://api.openasi.bitmiracle.cn"


@dataclass(frozen=True)
class CheckinResult:
    status: str
    message: str
    amount: Any = None


class OpenASIError(RuntimeError):
    """An expected API, network, or configuration error."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def _read_json(response: Any) -> dict[str, Any]:
    try:
        value = json.loads(response.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenASIError("服务器返回了无法解析的响应") from exc
    if not isinstance(value, dict):
        raise OpenASIError("服务器返回了异常响应格式")
    return value


def _payload_error(payload: dict[str, Any]) -> OpenASIError | None:
    error = payload.get("error")
    if isinstance(error, dict):
        return OpenASIError(
            str(error.get("message") or "接口请求失败"),
            str(error.get("code")) if error.get("code") is not None else None,
        )

    # Authentication endpoints return {code, message} directly.
    if payload.get("code") or payload.get("message"):
        return OpenASIError(
            str(payload.get("message") or "认证失败"),
            str(payload.get("code")) if payload.get("code") is not None else None,
        )
    return None


class OpenASIClient:
    """Client for login, status lookup, and daily check-in."""

    def __init__(self, token: str | None = None, timeout: float = 30) -> None:
        self.token = token
        self.timeout = timeout

    def _post(self, path: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "openasi-checkin/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = Request(
            f"{API_BASE}{path}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = _read_json(response)
                response_headers = {k.lower(): v for k, v in response.headers.items()}
        except HTTPError as exc:
            try:
                payload = _read_json(exc)
            except OpenASIError:
                payload = {}
            error = _payload_error(payload)
            if error:
                raise error from exc
            raise OpenASIError(f"服务器请求失败（HTTP {exc.code}）") from exc
        except URLError as exc:
            raise OpenASIError(f"无法连接 OpenASI：{exc.reason}") from exc
        except TimeoutError as exc:
            raise OpenASIError("请求 OpenASI 超时") from exc

        error = _payload_error(payload)
        if error:
            raise error
        if response_headers.get("set-auth-token"):
            self.token = response_headers["set-auth-token"]
        return payload, response_headers

    @staticmethod
    def _token_from_response(
        payload: dict[str, Any], headers: dict[str, str]
    ) -> str | None:
        if headers.get("set-auth-token"):
            return headers["set-auth-token"]
        session = payload.get("session")
        candidates = [
            payload.get("token"),
            session.get("token") if isinstance(session, dict) else None,
        ]
        return next((item for item in candidates if isinstance(item, str) and item), None)

    def login(self, email: str, password: str) -> None:
        payload, headers = self._post(
            "/api/auth/sign-in/email",
            {"email": email, "password": password},
        )
        token = self._token_from_response(payload, headers)
        if not token:
            raise OpenASIError("登录成功但服务器没有返回会话令牌")
        self.token = token

    def _api_post(self, name: str) -> Any:
        if not self.token:
            raise OpenASIError("缺少会话令牌")
        payload, _ = self._post(f"/api/{name}", {"data": {}})
        return payload.get("data")

    def checkin_result(self, dry_run: bool = False) -> CheckinResult:
        status = self._api_post("getCheckinStatus")
        if not isinstance(status, dict):
            raise OpenASIError("签到状态响应格式异常")
        if status.get("checkedInToday") is True:
            return CheckinResult("already_done", "今天已经签到，无需重复操作。")
        if status.get("checkedInToday") is not False:
            raise OpenASIError("签到状态缺少有效的 checkedInToday 字段")
        if dry_run:
            return CheckinResult("dry_run", "当前尚未签到（演练模式，未提交签到）。")

        result = self._api_post("checkin")
        if not isinstance(result, dict):
            raise OpenASIError("签到响应格式异常")
        amount = result.get("amount")
        message = "签到成功。" if amount is None else f"签到成功，获得 {amount} 积分。"
        return CheckinResult("success", message, amount)

    def checkin(self, dry_run: bool = False) -> bool:
        """Compatibility method; all display is handled by the caller."""
        return self.checkin_result(dry_run).status == "success"
