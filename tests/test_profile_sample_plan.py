"""Keep previously inspected races out of the new reserved evaluation sample."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import unittest

from scripts.evaluate_profiles import load_plan

ROOT = Path(__file__).resolve().parents[1]


class ProfileSamplePlanTests(unittest.TestCase):
    def test_previously_inspected_events_are_development_only(self):
        previous = load_plan(ROOT / "configs/profile-evaluation-2024.json")
        expanded = load_plan(ROOT / "configs/profile-evaluation-2024-expanded.json")
        inspected = set(previous.development_sessions + previous.validation_sessions)
        self.assertTrue(inspected <= set(expanded.development_sessions))
        self.assertFalse(inspected & set(expanded.validation_sessions))
        self.assertEqual(expanded.config, previous.config)

    def test_all_2024_races_are_selected_once_with_six_reserved(self):
        expanded = load_plan(ROOT / "configs/profile-evaluation-2024-expanded.json")
        sessions = expanded.development_sessions + expanded.validation_sessions
        self.assertEqual(len(expanded.development_sessions), 18)
        self.assertEqual(len(expanded.validation_sessions), 6)
        self.assertEqual(
            set(sessions), {f"session:{race}:R" for race in range(1121, 1145)}
        )
        self.assertEqual(len(set(sessions)), len(sessions))

    def test_documented_freeze_digest_matches_the_executable_plan(self):
        expanded = load_plan(ROOT / "configs/profile-evaluation-2024-expanded.json")
        canonical = json.dumps(
            asdict(expanded), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        document = (ROOT / "docs/amostra-pilotos-2024-expandida.md").read_text()
        self.assertIn(f"`{digest}`", document)


if __name__ == "__main__":
    unittest.main()
