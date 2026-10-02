"""Known trends, early-lap missingness and selection boundaries for tyre studies."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from f1_simulator.application.analyze_tyres import (
    analyze_tyres,
    describe_stint,
    fit_trend,
)
from scripts.analyze_tyres import publish
from tests.test_profile_evaluation import MemoryHistory
from tests.test_driver_profile import CONFIG


def rows(slope=100):
    return [
        dict(
            session_id="session:1:R",
            driver_id="driver:1",
            stint=2,
            compound="MEDIUM",
            fresh_tyre=True,
            lap_number=10 + i,
            tyre_life_laps=i + 1,
            lap_time_ms=90000 + slope * i,
            pit_out_ms=1 if i == 0 else None,
            eligible=i != 0,
            exclusions=["pit_lap"] if i == 0 else [],
        )
        for i in range(12)
    ]


class TyreStudyTests(unittest.TestCase):
    def test_known_positive_negative_and_constant(self):
        for slope in (-100, 0, 100):
            fit = fit_trend(rows(slope))
            self.assertEqual(fit["slope_ms_per_age_lap"], slope)
            self.assertEqual(fit["robust_slope_ms_per_age_lap"], slope)
            self.assertEqual(fit["linear_mae_ms"], 0)
        self.assertIsNone(fit_trend(rows()[:4]))
        short_span = rows()
        for r in short_span:
            r["tyre_life_laps"] = 1
        self.assertIsNone(fit_trend(short_span))

    def test_early_contrast_uses_race_laps_not_filtered_rank(self):
        source = rows()
        stint = describe_stint(source)
        self.assertEqual(stint["early_minus_later_ms"], -400)
        self.assertEqual(stint["start_kind"], "post_pit")
        source[1]["eligible"] = False
        missing = describe_stint(source)
        self.assertIsNone(missing["early_minus_later_ms"])
        self.assertEqual(missing["early_laps"], 1)
        self.assertEqual(missing["sensitivity"]["3"]["laps"], 9)

    def test_age_audit_gaps_and_unknown_start(self):
        source = rows()
        del source[4]
        self.assertFalse(describe_stint(source)["issues"])
        source[3]["tyre_life_laps"] += 1
        invalid = describe_stint(source)
        self.assertIn("age_progression_mismatch", invalid["issues"])
        self.assertIsNone(invalid["fit"])
        unknown = rows()[1:]
        study = describe_stint(unknown)
        self.assertIsNotNone(study["fit"])
        self.assertFalse(study["start_known"])
        self.assertIsNone(study["early_minus_later_ms"])
        self.assertIsNone(study["sensitivity"]["3"])

    def test_mixed_compound_wet_and_used(self):
        source = rows()
        source[2]["compound"] = "HARD"
        self.assertIsNone(describe_stint(source)["fit"])
        source = rows()
        for r in source:
            r["fresh_tyre"] = False
            r["tyre_life_laps"] += 4
        used = describe_stint(source)
        self.assertEqual(used["fit"]["slope_ms_per_age_lap"], 100)
        self.assertFalse(used["fresh_tyre"])
        for r in source:
            r["compound"] = "WET"
        self.assertIsNone(describe_stint(source)["fit"])

    def test_repository_selection_reproducibility_and_publication(self):
        repo = MemoryHistory()
        result = analyze_tyres(repo, session_ids=("session:1:R",), config=CONFIG)
        self.assertEqual(set(result["events"]), {"session:1:R"})
        self.assertTrue(
            all(
                filters.get("session_id") in (None, "session:1:R")
                for _, filters in repo.calls
            )
        )
        self.assertEqual(
            result,
            analyze_tyres(MemoryHistory(), session_ids=("session:1:R",), config=CONFIG),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = publish(result, root, plots=False)
            original = (first / "analysis.json").read_bytes()
            with patch(
                "scripts.analyze_tyres.os.rename", side_effect=OSError("failed")
            ):
                with self.assertRaises(OSError):
                    publish(deepcopy(result), root, plots=False)
            self.assertEqual((first / "analysis.json").read_bytes(), original)
            self.assertEqual(len(list(root.iterdir())), 1)
