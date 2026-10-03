"""User-scoped Windows DPAPI, with prompts explicitly forbidden."""

from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes

from .api import OpenASIError


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise OpenASIError("图形版凭据存储仅支持 Windows。")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    input_blob = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = DataBlob()
    try:
        # No LOCAL_MACHINE flag: a different Windows user cannot decrypt this.
        if not function(ctypes.byref(input_blob), None, None, None, None, 1,
                        ctypes.byref(output_blob)):
            code = ctypes.get_last_error()
            raise OpenASIError(f"凭据加密/解密失败（Windows {code}），请在原 Windows 用户下重新保存账号。")
        return ctypes.string_at(output_blob.data, output_blob.size)
    finally:
        ctypes.memset(buffer, 0, len(buffer))
        if output_blob.data:
            ctypes.memset(output_blob.data, 0, output_blob.size)
            kernel32.LocalFree(output_blob.data)


def protect_password(password: str) -> str:
    return base64.b64encode(_crypt(password.encode("utf-8"), decrypt=False)).decode("ascii")


def unprotect_password(value: str) -> str:
    try:
        encrypted = base64.b64decode(value, validate=True)
        return _crypt(encrypted, decrypt=True).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise OpenASIError("保存的凭据已损坏，请重新输入密码并保存。") from exc
