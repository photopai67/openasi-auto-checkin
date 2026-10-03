"""Short-lived scheduled entry point. Intentionally never imports Tkinter."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .service import RunRecord, friendly_error, record_result, run_checkin
from .storage import AppStore


def main(argv: list[str] | None = None) -> int:
    # No argparse console output, including for malformed scheduled arguments.
    try:
        parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
        parser.add_argument("--data-dir", type=Path)
        parser.add_argument("--scheduled", action="store_true")
        args, unknown = parser.parse_known_args(argv)
        if unknown:
            return 2
        store = AppStore(args.data_dir)
    except (Exception, SystemExit):
        return 2
    try:
        # A logon trigger catches a missed daily run, but not before today's time.
        if args.scheduled:
            settings = store.load_settings()
            if datetime.now().strftime("%H:%M") < settings.at:
                return 0
        record = run_checkin(store)
        return 0 if record.ok else 1
    except Exception as exc:
        try:
            record_result(store, RunRecord(
                "failed", friendly_error(exc),
                datetime.now().astimezone().isoformat(timespec="seconds"), "automatic",
            ))
        except Exception:
            pass  # A full/read-only disk must not cause a window or traceback.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
