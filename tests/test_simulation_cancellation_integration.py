"""Cancelamento atraves de HTTP, motor 2D e persistencia temporaria."""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402
from app.services import catalog  # noqa: E402
from app.services.cancellation import Cancellation, SimulationCancelled  # noqa: E402

from frontend.arcade import track_client  # noqa: E402
from tests.geometry_support import fixture_geometry  # noqa: E402
from tests.model_support import parameters  # noqa: E402
from tests.test_catalog_grid_run import current_grid  # noqa: E402


class CancelIntegrationTest(unittest.TestCase):
    def test_cancel_during_request_stops_motor_and_preserves_saved_data(self):
        geometry = fixture_geometry()
        entered = threading.Event()
        release = threading.Event()
        accepted = threading.Event()
        user_cancelled = threading.Event()
        real_check, real_cancel = Cancellation.check, Cancellation.cancel
        checks = []

        def check(job):
            checks.append(1)
            if not entered.is_set():
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("motor nao liberado pelo teste")
            return real_check(job)

        def cancel(job):
            result = real_cancel(job)
            if result:
                accepted.set()
            return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "current.json"
            saved = root / "saved"
            saved.mkdir()
            previous = b'{"existing": "preservado"}'
            current.write_bytes(previous)
            (saved / "previous.json").write_bytes(previous)
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            sock.listen(128)
            url = f"http://127.0.0.1:{sock.getsockname()[1]}"
            server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
            thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]})
            with (
                patch.object(catalog, "read_current_grid", return_value=current_grid()),
                patch.object(catalog, "_track_reference", return_value=("circuit:1", geometry.lap_length_m)),
                patch.object(catalog, "_track_geometry", return_value=geometry),
                patch.object(catalog, "_model_parameters", return_value=parameters()),
                patch.object(catalog, "CURRENT_RACE_JSON", current),
                patch.object(catalog, "SAVED_RACES_DIR", saved),
                patch.object(Cancellation, "check", check),
                patch.object(Cancellation, "cancel", cancel),
            ):
                thread.start()
                outcome = []

                def run():
                    try:
                        track_client.run_grid_stream(
                            {"total_laps": 5, "track_id": "circuit:1"},
                            url,
                            cancelled=user_cancelled.is_set,
                        )
                    except Exception as error:
                        outcome.append(error)

                request = threading.Thread(target=run)
                try:
                    request.start()
                    self.assertTrue(entered.wait(10), "motor nao iniciou")
                    self.assertTrue(request.is_alive())
                    user_cancelled.set()
                    self.assertTrue(accepted.wait(10), "backend nao aceitou cancelamento")
                    release.set()
                    request.join(10)
                    self.assertFalse(request.is_alive())
                    self.assertEqual(len(checks), 1)
                    self.assertEqual(len(outcome), 1)
                    self.assertIsInstance(outcome[0], track_client.SimulationCancelled)
                    self.assertEqual(current.read_bytes(), previous)
                    self.assertEqual([p.name for p in saved.iterdir()], ["previous.json"])
                    self.assertEqual((saved / "previous.json").read_bytes(), previous)
                    self.assertEqual(json.loads(current.read_text()), {"existing": "preservado"})
                finally:
                    release.set()
                    request.join(10)
                    server.should_exit = True
                    thread.join(10)
                    sock.close()

    def test_completed_request_still_persists_result(self):
        geometry = fixture_geometry()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current, saved = root / "current.json", root / "saved"
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            sock.listen(128)
            url = f"http://127.0.0.1:{sock.getsockname()[1]}"
            server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
            thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]})
            with (
                patch.object(catalog, "read_current_grid", return_value=current_grid()),
                patch.object(catalog, "_track_reference", return_value=("circuit:1", geometry.lap_length_m)),
                patch.object(catalog, "_track_geometry", return_value=geometry),
                patch.object(catalog, "_model_parameters", return_value=parameters()),
                patch.object(catalog, "CURRENT_RACE_JSON", current),
                patch.object(catalog, "SAVED_RACES_DIR", saved),
            ):
                thread.start()
                try:
                    result = track_client.run_grid_stream(
                        {"total_laps": 1, "track_id": "circuit:1"}, url
                    )
                    self.assertEqual(json.loads(current.read_text()), result)
                    self.assertEqual(len(list(saved.glob("*.json"))), 1)
                finally:
                    server.should_exit = True
                    thread.join(10)
                    sock.close()

    def test_cancel_and_commit_are_exclusive(self):
        job = Cancellation()
        self.assertTrue(job.cancel())
        with self.assertRaises(SimulationCancelled):
            with job.commit():
                self.fail("cancelamento aceito nao pode gravar")
        completed = Cancellation()
        with completed.commit():
            pass
        self.assertFalse(completed.cancel())
