"""Opt-in real Windows task test using only a unique temporary task and store."""

import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from openasi_checkin.scheduler import TaskScheduler, _ps_literal, _run_powershell
from openasi_checkin.storage import AppStore


@unittest.skipUnless(os.name == "nt" and os.getenv("OPENASI_TEST_TASKS") == "1",
                     "Opt-in Windows task integration")
class TaskIntegrationTests(unittest.TestCase):
    def test_task_executes_background_without_credentials(self):
        with tempfile.TemporaryDirectory(prefix="OpenASI-test-中文-") as directory:
            store = AppStore(Path(directory))
            store.write_json("settings.json", {"at": "00:00"})
            scheduler = TaskScheduler(store)
            scheduler.task_name = "OpenASI-Checkin-Test-" + uuid.uuid4().hex[:12]
            name = _ps_literal(scheduler.task_name)
            try:
                scheduler.enable("00:00")
                self.assertTrue(scheduler.status()["exists"])
                _run_powershell(f"Start-ScheduledTask -TaskPath '\\' -TaskName {name}")
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    status = scheduler.status()
                    if store.read_json("last_run.json") and status["state"] != "Running":
                        break
                    time.sleep(0.5)
                self.assertEqual(store.read_json("last_run.json")["status"], "failed")
                self.assertEqual(scheduler.status()["last_result"], 1)
                scheduler.disable()
                self.assertEqual(scheduler.status()["state"], "Disabled")
            finally:
                _run_powershell(
                    f"$task=Get-ScheduledTask -TaskPath '\\' -TaskName {name} -ErrorAction SilentlyContinue; "
                    "if($task){$task | Unregister-ScheduledTask -Confirm:$false}; 'OK'"
                )
