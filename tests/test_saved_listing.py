"""Nomes e linhas da lista unica de simulacoes salvas, sem janela."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = str(ROOT / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.services import catalog as catalog_service  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from frontend.arcade.saved_tournaments_view import (  # noqa: E402
    renamed_items,
    row_lines,
    without_item,
)

RACE_RECORD = {
    "id": "interlagos-abc123",
    "name": "Autódromo de Interlagos · 07/11/2026 15:34",
    "saved_at": "2026-11-07T18:34:00+00:00",
    "track_id": "circuit:6",
    "track_name": "Autódromo de Interlagos",
    "total_laps": 69,
    "car_count": 20,
}


class RowLinesTest(unittest.TestCase):
    def test_race_row_shows_the_track_name_not_the_id(self) -> None:
        name, stages, details = row_lines("race", RACE_RECORD)

        self.assertEqual(name, "Autódromo de Interlagos · 07/11/2026 15:34")
        self.assertEqual(stages, "Pista: Autódromo de Interlagos")
        self.assertTrue(details.startswith("Corrida · 69 voltas · 20 carros · salvo em "))
        self.assertNotIn("circuit:6", stages + details)

    def test_race_saved_before_track_names_falls_back_to_the_id(self) -> None:
        record = {k: v for k, v in RACE_RECORD.items() if k != "track_name"}

        _name, stages, _details = row_lines("race", record)

        self.assertEqual(stages, "Pista: circuit:6")

    def test_tournament_row_lists_the_stage_names(self) -> None:
        record = {
            "id": "copa-abc123",
            "name": "Copa",
            "saved_at": "2026-10-30T12:00:00+00:00",
            "stage_count": 2,
            "car_count": 20,
            "circuits": ["circuit:1", "circuit:6"],
            "stage_names": ["Monza", "Interlagos"],
        }

        name, stages, details = row_lines("tournament", record)

        self.assertEqual(name, "Copa")
        self.assertEqual(stages, "Pistas: Monza · Interlagos")
        self.assertTrue(details.startswith("Torneio · 2 etapa(s) · 20 carros · salvo em "))

    def test_long_names_are_cut(self) -> None:
        record = {**RACE_RECORD, "name": "x" * 200}

        name, _stages, _details = row_lines("race", record)

        self.assertEqual(len(name), 60)
        self.assertTrue(name.endswith("…"))


class SaveSentRaceTest(unittest.TestCase):
    def test_sent_race_is_saved_with_the_default_name_and_track_name(self) -> None:
        race = {
            "setup": {"track_id": "circuit:6", "total_laps": 3},
            "classification": [{"driver_id": "a"}],
            "track_reference": {
                "requested_track_id": "circuit:6",
                "model_track_id": "circuit:6",
                "model_track_name": "Autódromo de Interlagos",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(catalog_service, "SAVED_RACES_DIR", Path(directory)):
                meta = catalog_service.save_current_race(None, race)

                self.assertTrue(meta["name"].startswith("Autódromo de Interlagos · "))
                self.assertEqual(meta["track_name"], "Autódromo de Interlagos")
                self.assertTrue((Path(directory) / f"{meta['id']}.json").exists())

    def test_incomplete_race_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(catalog_service, "SAVED_RACES_DIR", Path(directory)):
                with self.assertRaises(HTTPException) as caught:
                    catalog_service.save_current_race(None, {"setup": {}})

                self.assertEqual(caught.exception.status_code, 422)
                self.assertEqual(list(Path(directory).glob("*.json")), [])


class ManageSavedRaceTest(unittest.TestCase):
    RACE = {
        "setup": {"track_id": "circuit:6", "total_laps": 3},
        "classification": [{"driver_id": "a"}],
    }

    def test_rename_keeps_the_race_and_trims_the_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(catalog_service, "SAVED_RACES_DIR", Path(directory)):
                meta = catalog_service.save_current_race("Original", self.RACE)

                renamed = catalog_service.rename_saved_race(meta["id"], "  Nova  ")

                self.assertEqual(renamed["name"], "Nova")
                stored = json.loads((Path(directory) / f"{meta['id']}.json").read_text())
                self.assertEqual(stored["meta"]["name"], "Nova")
                self.assertEqual(stored["race"], self.RACE)

    def test_blank_name_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(catalog_service, "SAVED_RACES_DIR", Path(directory)):
                meta = catalog_service.save_current_race("Original", self.RACE)

                with self.assertRaises(HTTPException) as caught:
                    catalog_service.rename_saved_race(meta["id"], "   ")

                self.assertEqual(caught.exception.status_code, 422)

    def test_delete_removes_the_file_and_a_second_delete_is_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(catalog_service, "SAVED_RACES_DIR", Path(directory)):
                meta = catalog_service.save_current_race("Original", self.RACE)

                catalog_service.delete_saved_race(meta["id"])

                self.assertFalse((Path(directory) / f"{meta['id']}.json").exists())
                with self.assertRaises(HTTPException) as caught:
                    catalog_service.delete_saved_race(meta["id"])
                self.assertEqual(caught.exception.status_code, 404)


class LocalListChangeTest(unittest.TestCase):
    ITEMS = [{"id": "a", "name": "Um"}, {"id": "b", "name": "Dois"}]

    def test_rename_changes_only_the_named_item(self) -> None:
        result = renamed_items(self.ITEMS, "b", "Novo")

        self.assertEqual(result, [{"id": "a", "name": "Um"}, {"id": "b", "name": "Novo"}])
        self.assertEqual(self.ITEMS[1]["name"], "Dois")

    def test_delete_drops_only_the_named_item(self) -> None:
        self.assertEqual(without_item(self.ITEMS, "a"), [{"id": "b", "name": "Dois"}])


class DefaultRaceNameTest(unittest.TestCase):
    def test_track_name_comes_from_the_model_when_it_matches_the_setup(self) -> None:
        race = {
            "setup": {"track_id": "circuit:6"},
            "track_reference": {
                "requested_track_id": "circuit:6",
                "model_track_id": "circuit:6",
                "model_track_name": "Autódromo de Interlagos",
            },
        }

        self.assertEqual(catalog_service._track_name(race), "Autódromo de Interlagos")
        self.assertTrue(
            catalog_service._default_race_name(race).startswith(
                "Autódromo de Interlagos · "
            )
        )

    def test_a_model_name_for_another_track_is_not_used(self) -> None:
        race = {
            "setup": {"track_id": "circuit:1"},
            "track_reference": {
                "requested_track_id": "circuit:6",
                "model_track_id": "circuit:6",
                "model_track_name": "Autódromo de Interlagos",
            },
        }

        self.assertEqual(catalog_service._track_name(race), "circuit:1")

    def test_missing_track_gets_a_readable_default(self) -> None:
        self.assertTrue(
            catalog_service._default_race_name({"setup": {}}).startswith("Sem pista · ")
        )


if __name__ == "__main__":
    unittest.main()
