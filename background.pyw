"""Source checkout background entry. No GUI or console is created here."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from openasi_checkin.worker import main

if __name__ == "__main__":
    raise SystemExit(main())
