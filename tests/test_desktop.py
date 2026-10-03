"""Windows-specific protection and quiet process contracts."""

import base64
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openasi_checkin.api import OpenASIError
from openasi_checkin.scheduler import TaskScheduler, _run_powershell
from openasi_checkin.security import protect_password, unprotect_password
from openasi_checkin.storage import AppStore


@unittest.skipUnless(os.name == "nt", "Windows integration")
class WindowsTests(unittest.TestCase):
    def test_user_dpapi_roundtrip_and_non_plaintext_store(self):
        password = "fake-password-中文-$'"
        encrypted = protect_password(password)
        self.assertNotIn(password.encode(), base64.b64decode(encrypted))
        self.assertEqual(unprotect_password(encrypted), password)
        with tempfile.TemporaryDirectory() as directory:
            store = AppStore(Path(directory))
            store.save_account("test@example.com", password, "08:05")
            raw = (store.directory / "settings.json").read_text(encoding="utf-8")
            self.assertNotIn(password, raw)
            self.assertEqual(store.credentials(), ("test@example.com", password))

    def test_corrupt_password_fails(self):
        with self.assertRaises(OpenASIError):
            unprotect_password("not base64!")

    @patch("openasi_checkin.scheduler.subprocess.run")
    def test_helper_cannot_create_a_console(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "OK", "")
        self.assertEqual(_run_powershell("'OK'"), "OK")
        args, kwargs = run.call_args
        self.assertIn("-NonInteractive", args[0])
        self.assertIn("Hidden", args[0])
        self.assertEqual(kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)
        self.assertEqual(kwargs["startupinfo"].wShowWindow, subprocess.SW_HIDE)
        self.assertNotIn("shell", kwargs)

    def test_task_action_is_pythonw_and_not_the_ui(self):
        with tempfile.TemporaryDirectory(prefix="OpenASI 中文 ") as directory:
            scheduler = TaskScheduler(AppStore(Path(directory)))
            executable, arguments, _ = scheduler.launch_action()
            self.assertEqual(Path(executable).name, "pythonw.exe")
            self.assertIn("--scheduled", arguments)
            self.assertNotIn("configure.pyw", arguments)
            self.assertNotIn(".bat", arguments)
            script = scheduler.registration_script("09:30")
            self.assertIn("-LogonType Interactive -RunLevel Limited", script)
            self.assertIn("-StartWhenAvailable", script)
            self.assertIn("-MultipleInstances IgnoreNew", script)

    def test_tk_window_builds_with_private_store(self):
        import tkinter as tk
        from openasi_checkin.gui import ConfigurationWindow

        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                window = ConfigurationWindow(root, AppStore(Path(directory)))
                root.update_idletasks()
                self.assertEqual(window.password_entry.cget("show"), "*")
                self.assertEqual(window.hour.get(), "08")
                self.assertEqual(window.minute.get(), "05")
                self.assertFalse(window.busy)
        finally:
            root.destroy()

    def test_pythonw_background_exits_and_does_not_import_gui(self):
        # Import isolation is also covered cross-platform; this exercises the
        # actual windowless interpreter and source entry on Windows.
        background = Path(__file__).resolve().parents[1] / "background.pyw"
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [str(pythonw), str(background), "--data-dir", directory],
                capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.assertEqual(result.returncode, 1)  # missing config, no network call
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.stderr, b"")
            store = AppStore(Path(directory))
            self.assertEqual(store.read_json("last_run.json")["status"], "failed")
