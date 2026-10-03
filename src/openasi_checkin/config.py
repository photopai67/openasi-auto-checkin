"""Configuration helpers."""

from __future__ import annotations

import os
from pathlib import Path

from .api import OpenASIError


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs without overwriting real environment vars."""

    if not path.is_file():
        raise OpenASIError(f"环境文件不存在：{path}")
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise OpenASIError(f"环境文件第 {line_number} 行不是 KEY=VALUE 格式")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "\'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)

