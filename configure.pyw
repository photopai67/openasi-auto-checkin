"""Double-click source launcher for the configuration window."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

if __name__ == "__main__":
    try:
        from openasi_checkin.gui import main
        raise SystemExit(main())
    except Exception:
        # Only the user-opened configuration launcher may display a startup error.
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, "配置界面启动失败。请检查完整源码和 Python 的 Tcl/Tk 组件。\n"
            "可以运行 python configure.pyw 查看诊断信息。", "OpenASI 自动签到", 0x10,
        )
        if sys.stderr is not None:
            import traceback
            traceback.print_exc()
        raise SystemExit(1)
