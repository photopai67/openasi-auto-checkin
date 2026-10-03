import json
import unittest
from unittest.mock import patch

from openasi_checkin.api import OpenASIClient, OpenASIError


class FakeResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ApiTests(unittest.TestCase):
    @patch("openasi_checkin.api.urlopen")
    def test_checkin_skips_when_already_done(self, urlopen):
        urlopen.return_value = FakeResponse({"data": {"checkedInToday": True}})
        self.assertFalse(OpenASIClient(token="test").checkin())
        urlopen.assert_called_once()

    @patch("openasi_checkin.api.urlopen")
    def test_login_reads_set_auth_token(self, urlopen):
        urlopen.return_value = FakeResponse(
            {"user": {"emailVerified": True}}, {"set-auth-token": "token"}
        )
        client = OpenASIClient()
        client.login("user@example.com", "password")
        self.assertEqual(client.token, "token")

    @patch("openasi_checkin.api.urlopen")
    def test_api_error_is_not_reported_as_success(self, urlopen):
        urlopen.return_value = FakeResponse(
            {"data": None, "error": {"code": "UNAUTHORIZED", "message": "Not logged in"}}
        )
        with self.assertRaisesRegex(OpenASIError, "Not logged in"):
            OpenASIClient(token="bad").checkin()

    @patch("openasi_checkin.api.urlopen")
    def test_dry_run_never_submits_checkin(self, urlopen):
        urlopen.return_value = FakeResponse({"data": {"checkedInToday": False}})
        result = OpenASIClient(token="test").checkin_result(dry_run=True)
        self.assertEqual(result.status, "dry_run")
        urlopen.assert_called_once()

    @patch("openasi_checkin.api.urlopen")
    def test_missing_status_never_submits_checkin(self, urlopen):
        urlopen.return_value = FakeResponse({"data": {}})
        with self.assertRaises(OpenASIError):
            OpenASIClient(token="test").checkin_result()
        urlopen.assert_called_once()

    @patch("openasi_checkin.api.urlopen")
    def test_unchecked_account_submits_once(self, urlopen):
        urlopen.side_effect = [
            FakeResponse({"data": {"checkedInToday": False}}),
            FakeResponse({"data": {"amount": 100}}),
        ]
        result = OpenASIClient(token="test").checkin_result()
        self.assertEqual(result.status, "success")
        self.assertEqual(urlopen.call_count, 2)
