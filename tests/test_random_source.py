from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError

from f1_simulator.domain.random_source import (
    MAX_TRUNCATED_STANDARD_NORMAL_ATTEMPTS,
    RandomDraw,
    SeededRandomSource,
    truncated_standard_normal,
)


class AlwaysOutsideSource:
    """Fonte controlada que torna observavel o limite da amostragem por rejeicao."""

    def __init__(self) -> None:
        self.calls = 0
        self.labels: set[str] = set()

    def standard_normal(self, label: str) -> float:
        self.calls += 1
        self.labels.add(label)
        return 2.0


class SeededRandomSourceTest(unittest.TestCase):
    def test_same_seed_reproduces_sequence(self) -> None:
        first = SeededRandomSource(42)
        second = SeededRandomSource(42)

        first_values = [first.standard_normal("lap_noise") for _ in range(20)]
        second_values = [second.standard_normal("lap_noise") for _ in range(20)]

        self.assertEqual(first_values, second_values)

    def test_different_seeds_produce_different_sequences(self) -> None:
        first = SeededRandomSource(42)
        second = SeededRandomSource(43)

        first_values = [first.standard_normal("lap_noise") for _ in range(20)]
        second_values = [second.standard_normal("lap_noise") for _ in range(20)]

        self.assertNotEqual(first_values, second_values)

    def test_spawn_reproduces_same_key_and_separates_different_keys(self) -> None:
        source = SeededRandomSource(2026)

        first = source.spawn("circuit:1")
        repeated = source.spawn("circuit:1")
        different = source.spawn("circuit:2")
        first_values = [first.standard_normal("lap_noise") for _ in range(10)]

        self.assertEqual(
            first_values,
            [repeated.standard_normal("lap_noise") for _ in range(10)],
        )
        self.assertNotEqual(
            first_values,
            [different.standard_normal("lap_noise") for _ in range(10)],
        )

    def test_spawn_does_not_consume_or_change_parent_stream(self) -> None:
        source = SeededRandomSource(99)
        untouched = SeededRandomSource(99)

        source.spawn("driver:1")
        before_parent_draws = [source.standard_normal("parent") for _ in range(5)]
        source.spawn("driver:2")
        after_parent_draws = [source.standard_normal("parent") for _ in range(5)]
        expected = [untouched.standard_normal("parent") for _ in range(10)]

        self.assertEqual(before_parent_draws + after_parent_draws, expected)

    def test_spawn_is_identical_with_different_python_hash_seeds(self) -> None:
        script = """
import json
from f1_simulator.domain.random_source import SeededRandomSource

source = SeededRandomSource(123456).spawn("circuit:18")
print(json.dumps([source.standard_normal("lap_noise") for _ in range(12)]))
"""

        outputs = []
        for hash_seed in ("1", "987654"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = hash_seed
            environment["PYTHONPATH"] = os.pathsep.join(
                filter(None, ("src", environment.get("PYTHONPATH")))
            )
            completed = subprocess.run(
                [sys.executable, "-c", script],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            outputs.append(json.loads(completed.stdout))

        self.assertEqual(outputs[0], outputs[1])

    def test_draw_recording_is_optional_ordered_and_immutable(self) -> None:
        unrecorded = SeededRandomSource(7)
        unrecorded.standard_normal("ignored")
        self.assertEqual(unrecorded.draws, ())

        recorded = SeededRandomSource(7, record_draws=True)
        first = recorded.standard_normal("driver:1/lap:1")
        second = recorded.standard_normal("driver:2/lap:1")

        self.assertEqual(
            recorded.draws,
            (
                RandomDraw("driver:1/lap:1", first),
                RandomDraw("driver:2/lap:1", second),
            ),
        )
        self.assertIsInstance(recorded.draws, tuple)
        with self.assertRaises(FrozenInstanceError):
            recorded.draws[0].label = "altered"  # type: ignore[misc]

    def test_spawn_preserves_recording_configuration(self) -> None:
        child = SeededRandomSource(7, record_draws=True).spawn("circuit:18")

        value = child.standard_normal("lap_noise")

        self.assertEqual(child.draws, (RandomDraw("lap_noise", value),))

    def test_rejects_non_integer_seed_including_bool(self) -> None:
        for invalid_seed in (True, False, 1.5, "42", None):
            with self.subTest(seed=invalid_seed):
                with self.assertRaises(ValueError):
                    SeededRandomSource(invalid_seed)  # type: ignore[arg-type]

    def test_rejects_invalid_public_argument_types(self) -> None:
        with self.assertRaises(ValueError):
            SeededRandomSource(1, record_draws=1)  # type: ignore[arg-type]

        source = SeededRandomSource(1)
        with self.assertRaises(ValueError):
            source.standard_normal(1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            source.spawn(1)  # type: ignore[arg-type]


class TruncatedStandardNormalTest(unittest.TestCase):
    def test_many_draws_respect_inclusive_limit(self) -> None:
        source = SeededRandomSource(123)
        limit_sigmas = 2.5

        values = [
            truncated_standard_normal(source, "lap_noise", limit_sigmas)
            for _ in range(5_000)
        ]

        self.assertTrue(all(-limit_sigmas <= value <= limit_sigmas for value in values))

    def test_rejected_attempts_keep_same_label_in_audit_log(self) -> None:
        source = SeededRandomSource(2, record_draws=True)

        result = truncated_standard_normal(source, "driver:1/lap:1", 0.1)

        self.assertGreater(len(source.draws), 1)
        self.assertTrue(all(draw.label == "driver:1/lap:1" for draw in source.draws))
        self.assertEqual(result, source.draws[-1].value)

    def test_rejects_non_positive_non_finite_and_non_numeric_limit(self) -> None:
        invalid_limits = (
            0.0,
            -1.0,
            float("inf"),
            float("-inf"),
            float("nan"),
            True,
            "3",
        )
        source = SeededRandomSource(1)

        for invalid_limit in invalid_limits:
            with self.subTest(limit=invalid_limit):
                with self.assertRaises(ValueError):
                    truncated_standard_normal(
                        source,
                        "lap_noise",
                        invalid_limit,  # type: ignore[arg-type]
                    )

    def test_raises_when_rejection_attempts_are_exhausted(self) -> None:
        source = AlwaysOutsideSource()

        with self.assertRaisesRegex(ValueError, "numero maximo de tentativas"):
            truncated_standard_normal(source, "lap_noise", 1.0)

        self.assertEqual(source.calls, MAX_TRUNCATED_STANDARD_NORMAL_ATTEMPTS)
        self.assertEqual(source.labels, {"lap_noise"})


if __name__ == "__main__":
    unittest.main()
