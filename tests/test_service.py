import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openasi_checkin.api import CheckinResult, OpenASIError
from openasi_checkin.service import run_checkin, test_login
from openasi_checkin.storage import AppStore, validate_time
from openasi_checkin.worker import main as worker_main


class BackgroundTests(unittest.TestCase):
    def test_missing_config_is_recorded_without_any_console_output(self):
        with tempfile.TemporaryDirectory() as directory:
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = worker_main(["--data-dir", directory])
            self.assertEqual(code, 1)
            self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")
            store = AppStore(Path(directory))
            self.assertEqual(store.read_json("last_run.json")["status"], "failed")
            self.assertIn("配置窗口", store.read_log())

    @patch("openasi_checkin.service.OpenASIClient")
    def test_success_and_already_done_are_recorded(self, client_type):
        client = client_type.return_value
        client.token = "fake-token"
        for status in ("success", "already_done"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                client.checkin_result.return_value = CheckinResult(status, "签到正常")
                record = run_checkin(AppStore(Path(directory)), account=("test@example.com", "fake-password"))
                self.assertTrue(record.ok)
                self.assertEqual(record.status, status)

    @patch("openasi_checkin.service.OpenASIClient")
    def test_failure_redacts_credentials_in_status_and_log(self, client_type):
        client = client_type.return_value
        client.token = "fake-token"
        client.checkin_result.side_effect = OpenASIError("bad fake-password test@example.com Bearer fake-token")
        with tempfile.TemporaryDirectory() as directory:
            store = AppStore(Path(directory))
            record = run_checkin(store, account=("test@example.com", "fake-password"))
            self.assertFalse(record.ok)
            combined = json.dumps(store.read_json("last_run.json")) + store.read_log()
            for value in ("fake-password", "test@example.com", "fake-token"):
                self.assertNotIn(value, combined)

    @patch("openasi_checkin.service.OpenASIClient")
    def test_login_test_does_not_submit_checkin(self, client_type):
        client_type.return_value.checkin_result.return_value = CheckinResult("dry_run", "未签到")
        self.assertIn("登录成功", test_login("test@example.com", "fake-password"))
        client_type.return_value.checkin_result.assert_called_once_with(dry_run=True)

    def test_background_import_does_not_load_tkinter(self):
        result = subprocess.run(
            [sys.executable, "-c", "import sys; import openasi_checkin.worker; "
             "assert 'tkinter' not in sys.modules; assert 'openasi_checkin.gui' not in sys.modules"],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_time_is_rejected(self):
        for value in ("24:00", "08:60", "8:5", "08:05; bad"):
            with self.assertRaises(OpenASIError):
                validate_time(value)

    @patch("openasi_checkin.worker.datetime")
    @patch("openasi_checkin.worker.run_checkin")
    def test_logon_catchup_waits_until_daily_time(self, run, clock):
        clock.now.return_value.strftime.return_value = "07:00"
        with tempfile.TemporaryDirectory() as directory:
            store = AppStore(Path(directory))
            store.write_json("settings.json", {"at": "08:05"})
            self.assertEqual(worker_main(["--data-dir", directory, "--scheduled"]), 0)
            run.assert_not_called()

    def test_invalid_background_arguments_are_silent(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(worker_main(["--data-dir"]), 2)
        self.assertEqual(out.getvalue() + err.getvalue(), "")
