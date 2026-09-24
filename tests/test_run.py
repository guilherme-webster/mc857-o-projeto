"""Tests for orchestration that must finish before the Arcade client starts."""

from __future__ import annotations

import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import run


class WaitForBackendTest(unittest.TestCase):
    @staticmethod
    def _response(status: int):
        response = MagicMock()
        response.__enter__.return_value.status = status
        return response

    @patch("run.time.sleep")
    @patch("run.urllib.request.urlopen")
    def test_retries_until_backend_is_ready(self, urlopen, sleep) -> None:
        urlopen.side_effect = [
            urllib.error.URLError("connection refused"),
            self._response(200),
        ]

        ready = run.wait_for_backend(attempts=2, retry_interval=0.01)

        self.assertTrue(ready)
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.01)

    @patch("run.time.sleep")
    @patch("run.urllib.request.urlopen")
    def test_reports_failure_after_all_attempts(self, urlopen, sleep) -> None:
        urlopen.side_effect = urllib.error.URLError("connection refused")

        ready = run.wait_for_backend(attempts=3, retry_interval=0.01)

        self.assertFalse(ready)
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
