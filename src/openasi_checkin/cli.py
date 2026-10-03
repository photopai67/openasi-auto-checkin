"""Command-line entry point."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from .api import OpenASIClient, OpenASIError
from .config import load_env_file


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenASI 每日签到脚本")
    parser.add_argument("--env-file", help="可选配置文件，例如 .env")
    parser.add_argument("--email", help="OpenASI 邮箱")
    parser.add_argument("--password", help="OpenASI 密码；不建议在命令行传入")
    parser.add_argument("--token", help="已有 Bearer token")
    parser.add_argument("--timeout", type=float, default=30, help="网络超时秒数")
    parser.add_argument("--dry-run", action="store_true", help="只查询状态，不签到")
    parser.add_argument("--interactive", action="store_true", help="缺少密码时安全提示输入")
    parser.add_argument("--loop", action="store_true", help="每天运行一次并持续等待")
    parser.add_argument("--at", default="08:05", help="--loop 的本地时间，格式 HH:MM")
    return parser


def _next_run_seconds(hour: int, minute: int) -> float:
    now = datetime.now().astimezone()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def _run_once(args: argparse.Namespace) -> None:
    if args.env_file:
        load_env_file(Path(args.env_file).expanduser())

    token = args.token or os.getenv("OPENASI_TOKEN")
    client = OpenASIClient(token=token, timeout=args.timeout)
    if not token:
        email = args.email or os.getenv("OPENASI_EMAIL")
        password = args.password or os.getenv("OPENASI_PASSWORD")
        if not email:
            raise OpenASIError("缺少邮箱：请设置 OPENASI_EMAIL 或使用 --email")
        if not password:
            if args.interactive and sys.stdin.isatty():
                password = getpass.getpass("OpenASI 密码：")
            else:
                raise OpenASIError("缺少密码：请设置 OPENASI_PASSWORD；不要把密码写进脚本")
        client.login(email, password)
    print(client.checkin_result(dry_run=args.dry_run).message)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        hour, minute = (int(part) for part in args.at.split(":", 1))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        print("错误：--at 必须是 HH:MM，例如 08:05", file=sys.stderr)
        return 2

    while True:
        try:
            _run_once(args)
        except OpenASIError as exc:
            detail = f"（{exc.code}）" if exc.code else ""
            print(f"失败{detail}：{exc}", file=sys.stderr)
            if not args.loop:
                return 1
        except KeyboardInterrupt:
            print("已停止。")
            return 130
        if not args.loop:
            return 0
        seconds = _next_run_seconds(hour, minute)
        next_run = datetime.now().astimezone() + timedelta(seconds=seconds)
        print(f"下次运行：{next_run:%Y-%m-%d %H:%M:%S %Z}，按 Ctrl+C 停止。")
        try:
            time.sleep(seconds)
        except KeyboardInterrupt:
            print("已停止。")
            return 130
