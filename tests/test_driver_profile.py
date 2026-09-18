"""Known synthetic observations verify the experimental method, not calibration."""

from dataclasses import replace
import unittest

from f1_simulator.domain.driver_profile import (
    ProfileConfig,
    assess_session,
    estimate_profiles,
)
from f1_simulator.domain.session_data import SESSION_SCHEMA
from f1_simulator.factories.history_factory import HistoryFactory

CONFIG = ProfileConfig(10, 10, 120000, 3, 2, 1)


def record(table, **values):
    fields = dict.fromkeys(SESSION_SCHEMA[table].names)
    fields.update(values)
    return HistoryFactory().build(SESSION_SCHEMA[table], fields)


def lap(driver="driver:830", number=2, time=90000, **changes):
    values = dict(
        session_id="session:1141:R",
        driver_id=driver,
        lap_number=number,
        lap_time_ms=time,
        lap_start_ms=100000,
        session_time_ms=200000,
        stint=1,
        compound="MEDIUM",
        tyre_life_laps=3.0,
        track_status="1",
        accurate=True,
        generated=False,
        deleted=False,
    )
    values.update(changes)
    return record("lap_observations", **values)


def weather(time=90000, rain=False, sequence=0):
    return record(
        "weather_observations",
        session_id="session:1141:R",
        sequence=sequence,
        session_time_ms=time,
        rainfall=rain,
    )


def status(time=0, value="Started", sequence=0):
    return record(
        "session_status_events",
        session_id="session:1141:R",
        sequence=sequence,
        session_time_ms=time,
        status=value,
    )


def assess(rows, **kwargs):
    options = dict(
        session_id="session:1141:R",
        race_id="race:1141",
        season=2024,
        circuit_id="circuit:18",
        laps=tuple(rows),
        weather=(weather(),),
        session_status=(status(),),
        teams={"driver:830": "team:9", "driver:839": "team:214"},
        config=CONFIG,
    )
    options.update(kwargs)
    return assess_session(**options)


def sample():
    return [
        lap(driver, n, t)
        for driver, times in (
            ("driver:830", (90000, 92000, 94000)),
            ("driver:839", (100000, 102000, 104000)),
        )
        for n, t in enumerate(times, 2)
    ]


class DriverProfileTests(unittest.TestCase):
    def test_known_reference_residuals_and_mad(self):
        profiles, audit = estimate_profiles(
            assess(sample()), ("driver:830", "driver:839"), CONFIG
        )
        first, second = profiles
        self.assertEqual(first.contexts[0].reference_ms, 97000)
        self.assertAlmostEqual(first.pace_delta_pct, -5000 / 97000 * 100)
        self.assertAlmostEqual(second.pace_delta_pct, 5000 / 97000 * 100)
        self.assertAlmostEqual(first.consistency_mad_pct, 2000 / 97000 * 100)
        self.assertEqual(first.compared_laps, 3)
        self.assertEqual(len(audit), 6)
        self.assertTrue(all(not row.exclusions for row in audit))

    def test_invalid_configuration(self):
        for changes in (
            {"min_events": 0},
            {"lap_window": True},
            {"min_laps_per_context": 1},
            {"min_drivers_per_context": 1},
            {"weather_max_age_ms": 1.5},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(CONFIG, **changes)

    def test_unknown_flags_never_become_false(self):
        row = assess([lap(accurate=None, deleted=None, generated=None)])[0]
        self.assertEqual(
            set(row.exclusions),
            {"accurate_unknown", "deleted_unknown", "generated_unknown"},
        )
        self.assertIsNone(row.context)

    def test_pits_first_lap_invalid_time_and_flags_are_all_audited(self):
        result = assess(
            [
                lap(
                    number=1,
                    time=0,
                    pit_out_ms=10,
                    deleted=True,
                    accurate=False,
                    generated=True,
                    track_status="14",
                )
            ]
        )[0]
        self.assertEqual(
            set(result.exclusions),
            {
                "first_lap",
                "invalid_lap_time",
                "pit_lap",
                "deleted_rejected",
                "accurate_rejected",
                "generated_rejected",
                "track_not_clear_or_unknown",
            },
        )

    def test_weather_uses_prior_sample_and_expires_over_whole_lap(self):
        cases = (
            ((), "weather_missing_or_stale"),
            ((weather(100001),), "weather_missing_or_stale"),
            ((weather(0),), "weather_missing_or_stale"),
            ((weather(), weather(150000, True, 1)), "weather_transition"),
            ((weather(rain=None),), "weather_missing_or_stale"),
            ((weather(), weather(90000, True, 1)), "weather_missing_or_stale"),
        )
        for observations, reason in cases:
            with self.subTest(observations=observations):
                self.assertIn(
                    reason, assess([lap()], weather=observations)[0].exclusions
                )
        self.assertFalse(assess([lap()], weather=(weather(80000),))[0].exclusions)
        self.assertIn(
            "weather_missing_or_stale",
            assess([lap()], weather=(weather(79999),))[0].exclusions,
        )

    def test_session_pause_and_unknown_state_rejected(self):
        for events in (
            (),
            (status(value="Inactive"),),
            (status(), status(150000, "Aborted", 1), status(170000, "Started", 2)),
        ):
            self.assertIn(
                "session_not_running_or_unknown",
                assess([lap()], session_status=events)[0].exclusions,
            )

    def test_missing_team_tyre_and_clock(self):
        row = assess(
            [lap(compound="UNKNOWN", stint=None, lap_start_ms=None)], teams={}
        )[0]
        self.assertEqual(
            set(row.exclusions),
            {
                "compound_unknown",
                "tyre_context_unknown",
                "lap_clock_unknown",
                "missing_or_ambiguous_team",
            },
        )

    def test_duplicate_laps_are_not_silently_counted(self):
        audit = assess([lap(), lap(time=92000)])
        self.assertTrue(all("duplicate_lap" in row.exclusions for row in audit))

    def test_no_mixing_compounds_or_age_windows(self):
        rows = sample()
        rows[-1] = lap("driver:839", 4, 104000, compound="SOFT")
        profiles, audit = estimate_profiles(
            assess(rows), ("driver:830", "driver:839"), CONFIG
        )
        self.assertTrue(all(p.pace_delta_pct is None for p in profiles))
        self.assertEqual(sum(not row.exclusions for row in audit), 0)
        a, b = assess([lap(tyre_life_laps=9), lap(number=3, tyre_life_laps=10)])
        self.assertNotEqual(a.context, b.context)

    def test_insufficient_events_keeps_context_evidence(self):
        profiles, _ = estimate_profiles(
            assess(sample()),
            ("driver:830", "driver:839", "driver:0"),
            replace(CONFIG, min_events=2),
        )
        self.assertEqual(profiles[0].unavailable_reason, "no_lap_observations")
        self.assertEqual(profiles[1].unavailable_reason, "insufficient_events")
        self.assertIsNone(profiles[1].pace_delta_pct)
        self.assertEqual(len(profiles[1].contexts), 1)

    def test_driver_medians_have_equal_weight_and_order_is_irrelevant(self):
        rows = sample() + [lap(number=5, time=92000)]
        result = estimate_profiles(assess(rows), ("driver:839", "driver:830"), CONFIG)
        reverse = estimate_profiles(
            assess(list(reversed(rows))), ("driver:830", "driver:839"), CONFIG
        )
        self.assertEqual(result, reverse)
        self.assertEqual(result[0][0].contexts[0].reference_ms, 97000)

    def test_events_have_equal_weight_and_team_stays_in_context(self):
        first = assess(sample())
        # Repeat contexts of event 1, then add an opposite outcome in event 2.
        extra = tuple(
            replace(x, context=replace(x.context, lap_window_start=11)) for x in first
        )
        other = tuple(
            replace(
                x,
                session_id="session:1142:R",
                team_id="team:99",
                lap_time_ms=194000 - x.lap_time_ms,
                context=replace(
                    x.context, session_id="session:1142:R", race_id="race:1142"
                ),
            )
            for x in first
        )
        profiles, _ = estimate_profiles(
            first + extra + other, ("driver:830", "driver:839"), CONFIG
        )
        self.assertAlmostEqual(profiles[0].pace_delta_pct, 0)
        self.assertEqual(profiles[0].events, 2)
        self.assertEqual(profiles[0].contexts[-1].team_id, "team:99")


if __name__ == "__main__":
    unittest.main()
