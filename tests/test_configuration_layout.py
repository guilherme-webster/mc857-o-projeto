from __future__ import annotations

import unittest

from frontend.arcade.configuration_layout import Bounds, build_initial_configuration_layout


class InitialConfigurationLayoutTest(unittest.TestCase):
    def test_keeps_panels_and_controls_inside_the_1280_by_720_screen(self) -> None:
        layout = build_initial_configuration_layout()

        self.assertEqual(layout.screen, Bounds(0, 0, 1280, 720))
        for panel in layout.panels:
            self.assertTrue(layout.screen.contains(panel.bounds))
        for control in layout.controls:
            self.assertTrue(layout.screen.contains(control.bounds))

    def test_exposes_reference_data_and_only_scenario_parameters_as_editable(self) -> None:
        layout = build_initial_configuration_layout()
        controls = {control.identifier: control for control in layout.controls}

        self.assertEqual(controls["reference_race"].value, "São Paulo Grand Prix 2024")
        self.assertEqual(controls["reference_circuit"].value, "Autódromo José Carlos Pace")
        self.assertFalse(controls["reference_race"].editable)
        self.assertFalse(controls["reference_circuit"].editable)
        self.assertTrue(controls["laps"].editable)
        self.assertTrue(controls["weather_schedule"].editable)
        self.assertEqual(controls["weather_schedule"].kind, "button")
        self.assertNotIn("weather", controls)
        self.assertNotIn("seed", controls)

    def test_keeps_the_main_panels_separate(self) -> None:
        layout = build_initial_configuration_layout()

        for index, panel in enumerate(layout.panels):
            for other in layout.panels[index + 1 :]:
                self.assertFalse(panel.bounds.overlaps(other.bounds))


if __name__ == "__main__":
    unittest.main()
