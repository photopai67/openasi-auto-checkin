"""Backward-compatible source checkout entry point.

For an installed package, prefer: ``python -m openasi_checkin``.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from openasi_checkin.cli import main  # noqa: E402

raise SystemExit(main())
