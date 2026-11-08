"""Texto de status e carrossel da tela de carregamento, sem janela."""

from __future__ import annotations

import unittest

from frontend.arcade.race_launcher import LaunchProgress
from frontend.arcade.simulation_loading_view import (
    next_index,
    progress_fraction,
    progress_text,
)


class ProgressTextTest(unittest.TestCase):
    def test_lap_in_progress_matches_the_requested_sentence(self) -> None:
        text = progress_text(
            LaunchProgress(
                "x",
                stage_index=2,
                total_stages=3,
                stage_name="Interlagos",
                lap=12,
                laps=69,
            )
        )
        self.assertEqual(
            text,
            "Simulando etapa 2 de 3 - Interlagos. Volta 12 de 69.",
        )

    def test_stage_start_has_no_lap_yet(self) -> None:
        text = progress_text(
            LaunchProgress(
                "x", stage_index=1, total_stages=1, stage_name="Spa", laps=44
            )
        )
        self.assertEqual(text, "Simulando etapa 1 de 1 - Spa. Iniciando a corrida…")

    def test_before_the_first_stage_shows_the_step_message(self) -> None:
        self.assertEqual(
            progress_text(LaunchProgress("Conferindo o grid no backend…")),
            "Conferindo o grid no backend…",
        )


class ProgressFractionTest(unittest.TestCase):
    def test_preparation_step_is_empty(self) -> None:
        self.assertEqual(progress_fraction(LaunchProgress("Preparando")), 0.0)

    def test_counts_finished_stages_plus_the_lap_in_progress(self) -> None:
        # Segunda de tres etapas, na metade da corrida: (1 + 0.5) / 3.
        fraction = progress_fraction(
            LaunchProgress(
                "x", stage_index=2, total_stages=3, stage_name="A", lap=5, laps=10
            )
        )
        self.assertAlmostEqual(fraction, 0.5)

    def test_stage_start_counts_only_finished_stages(self) -> None:
        fraction = progress_fraction(
            LaunchProgress("x", stage_index=2, total_stages=4, laps=10)
        )
        self.assertAlmostEqual(fraction, 0.25)

    def test_never_exceeds_one(self) -> None:
        fraction = progress_fraction(
            LaunchProgress("x", stage_index=2, total_stages=2, lap=99, laps=10)
        )
        self.assertEqual(fraction, 1.0)


class CarouselTest(unittest.TestCase):
    def test_steps_forward_and_backward_wrapping_at_the_ends(self) -> None:
        self.assertEqual(next_index(0, 1, 3), 1)
        self.assertEqual(next_index(2, 1, 3), 0)
        self.assertEqual(next_index(0, -1, 3), 2)


if __name__ == "__main__":
    unittest.main()
