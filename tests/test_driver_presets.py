"""Contratos dos atributos v2, presets ficticios e borda HTTP do grid."""

from __future__ import annotations

import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = str(ROOT / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.routers import catalog as catalog_router  # noqa: E402
from app.schemas.responses import (  # noqa: E402
    AttributeOverride,
    BuildGridRequest,
    EditGridAttributesRequest,
)
from app.services import catalog as catalog_service  # noqa: E402
from f1_simulator.adapters.driver_presets_json import (  # noqa: E402
    DriverPresetError,
    load_driver_presets,
)
from f1_simulator.application.build_grid import GridEntry  # noqa: E402
from f1_simulator.application.catalog import CatalogEntry  # noqa: E402
from f1_simulator.application.generate_attributes import (  # noqa: E402
    apply_overrides,
    apply_presets,
    generate_attributes,
)
from f1_simulator.domain.attribute_effects import attributes_assumption  # noqa: E402
from f1_simulator.domain.driver_attributes import (  # noqa: E402
    ASSUMED_ARCHETYPES,
    ATTRIBUTE_FIELDS,
    PARAMETER_VERSION,
    DriverAttributes,
    archetype_profile,
)
from f1_simulator.domain.random_source import SeededRandomSource  # noqa: E402

PRESETS_PATH = ROOT / "configs" / "drivers" / "perfis-ficticios.json"


def generated(driver_ids: list[str], seed: int = 42) -> tuple[DriverAttributes, ...]:
    """Use a mesma hierarquia de fluxos adotada pela composition root."""

    source = SeededRandomSource(seed).spawn("attributes")
    return generate_attributes(driver_ids, source)


class DriverAttributesV2Test(unittest.TestCase):
    def test_new_fields_are_positive_finite_and_reported(self) -> None:
        item = generated(["driver:830"])[0]

        self.assertGreater(item.aggression, 0)
        self.assertGreater(item.composure, 0)
        self.assertEqual(item.parameter_version, "assumed-driver-attributes-v2")
        self.assertEqual(PARAMETER_VERSION, "assumed-driver-attributes-v2")
        assumption = attributes_assumption(item)
        self.assertEqual(assumption["aggression"], item.aggression)
        self.assertEqual(assumption["composure"], item.composure)

        for field in ("aggression", "composure"):
            for invalid in (0, -1, float("nan"), float("inf"), True):
                with self.subTest(field=field, invalid=invalid):
                    with self.assertRaises(ValueError):
                        replace(item, **{field: invalid})

    def test_archetype_ranges_include_aggression_and_composure(self) -> None:
        expected = {
            "aggressive": ((1.20, 1.50), (0.85, 1.05)),
            "balanced": ((0.90, 1.10), (0.90, 1.10)),
            "conservative": ((0.60, 0.85), (1.05, 1.30)),
        }

        for name, (aggression, composure) in expected.items():
            with self.subTest(archetype=name):
                profile = archetype_profile(name)  # type: ignore[arg-type]
                self.assertEqual(profile.aggression, aggression)
                self.assertEqual(profile.composure, composure)
                self.assertEqual(profile.source_kind, "heuristic")
                self.assertEqual(profile.parameter_version, PARAMETER_VERSION)

    def test_generation_stays_inside_every_archetype_range(self) -> None:
        for profile in ASSUMED_ARCHETYPES:
            item = generate_attributes(
                ["driver:1"],
                SeededRandomSource(81).spawn("attributes"),
                forced_archetypes={"driver:1": profile.name},
            )[0]
            for field in ATTRIBUTE_FIELDS:
                with self.subTest(archetype=profile.name, field=field):
                    low, high = getattr(profile, field)
                    self.assertLessEqual(low, getattr(item, field))
                    self.assertLessEqual(getattr(item, field), high)

    def test_v1_fields_keep_exact_values_for_the_same_seed(self) -> None:
        """Literais capturados antes de aggression/composure serem adicionados."""

        items = generated(["driver:830", "driver:839"], seed=42)
        observed = tuple(
            (
                item.driver_id,
                item.archetype,
                item.pace_offset_pct,
                item.consistency_factor,
                item.tyre_management_factor,
            )
            for item in items
        )
        self.assertEqual(
            observed,
            (
                (
                    "driver:830",
                    "balanced",
                    0.05195337231072339,
                    0.9817340034573214,
                    1.0789226634671676,
                ),
                (
                    "driver:839",
                    "aggressive",
                    -0.5971470341520967,
                    1.1256511263939875,
                    1.253731611415043,
                ),
            ),
        )


class DriverPresetAdapterTest(unittest.TestCase):
    def test_loads_named_2024_profiles_with_heuristic_metadata(self) -> None:
        presets = load_driver_presets(PRESETS_PATH)

        self.assertEqual(len(presets), 24)
        verstappen = presets["driver:830"]
        self.assertEqual(verstappen.driver_name, "Max Verstappen")
        self.assertEqual(verstappen.archetype, "aggressive")
        self.assertEqual(verstappen.source_kind, "heuristic")
        self.assertEqual(verstappen.parameter_version, "fictional-driver-presets-v1")
        self.assertLess(verstappen.values["pace_offset_pct"], 0)
        self.assertGreater(verstappen.values["aggression"], 1.2)

    def test_rejects_unknown_fields_and_values_outside_archetype(self) -> None:
        payload = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        for mutation, message in (
            (lambda data: data.update({"extra": True}), "campos desconhecidos"),
            (
                lambda data: data["drivers"][0]["attributes"].update(
                    {"aggression": 9.0}
                ),
                "fora da faixa",
            ),
        ):
            with self.subTest(message=message), TemporaryDirectory() as raw:
                changed = json.loads(json.dumps(payload))
                mutation(changed)
                path = Path(raw) / "presets.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaisesRegex(DriverPresetError, message):
                    load_driver_presets(path)

    def test_error_for_missing_file_includes_the_path(self) -> None:
        missing = ROOT / "tmp" / "presets-inexistentes.json"
        with self.assertRaisesRegex(DriverPresetError, "presets-inexistentes.json"):
            load_driver_presets(missing)


class ApplyDriverPresetsTest(unittest.TestCase):
    def test_preset_archetype_rerolls_omitted_fields_reproducibly(self) -> None:
        presets = load_driver_presets(PRESETS_PATH)
        source = SeededRandomSource(42).spawn("attributes")
        before = generate_attributes(["driver:830", "driver:999"], source)
        after = apply_presets(before, presets, source)
        repeated = apply_presets(before, presets, source)

        self.assertEqual(after, repeated)
        self.assertEqual(after[1], before[1])
        item = after[0]
        profile = archetype_profile("aggressive")
        self.assertEqual(item.archetype, "aggressive")
        self.assertEqual(item.pace_offset_pct, -0.58)
        self.assertEqual(item.aggression, 1.48)
        self.assertEqual(item.sources["aggression"], "preset")
        self.assertEqual(item.sources["consistency_factor"], "generated")
        self.assertLessEqual(
            profile.consistency_factor[0], item.consistency_factor
        )
        self.assertLessEqual(
            item.consistency_factor, profile.consistency_factor[1]
        )

    def test_manual_override_has_precedence_over_preset_and_generated(self) -> None:
        presets = load_driver_presets(PRESETS_PATH)
        source = SeededRandomSource(42).spawn("attributes")
        with_presets = apply_presets(
            generate_attributes(["driver:830"], source), presets, source
        )
        edited = apply_overrides(
            with_presets,
            {"driver:830": {"aggression": 1.01, "composure": 1.11}},
        )[0]

        self.assertEqual(edited.aggression, 1.01)
        self.assertEqual(edited.composure, 1.11)
        self.assertEqual(edited.sources["aggression"], "manual")
        self.assertEqual(edited.sources["composure"], "manual")
        self.assertEqual(edited.sources["pace_offset_pct"], "preset")
        self.assertEqual(edited.sources["consistency_factor"], "generated")


class CatalogPresetIntegrationTest(unittest.TestCase):
    def test_build_grid_service_applies_existing_preset_file(self) -> None:
        pool = (
            CatalogEntry(
                driver_id="driver:830",
                driver_name="Max Verstappen",
                driver_code="VER",
                team_id="team:9",
                team_name="Red Bull",
            ),
        )
        with (
            patch.object(catalog_service, "DRIVER_PRESETS_JSON", PRESETS_PATH),
            patch.object(catalog_service, "list_entries", return_value=pool),
            patch.object(catalog_service, "_write_current_grid") as write,
        ):
            pairs, attributes, seed = catalog_service.build_grid(
                1,
                mode="manual",
                manual_pair_ids=["driver:830@team:9"],
                seed=42,
            )

        self.assertEqual(seed, 42)
        self.assertEqual(pairs[0].driver_id, "driver:830")
        self.assertEqual(attributes["driver:830"].aggression, 1.48)
        self.assertEqual(attributes["driver:830"].sources["aggression"], "preset")
        write.assert_called_once()

    def test_post_grid_route_exposes_new_fields_and_preset_origin(self) -> None:
        entry = GridEntry("driver:830", "Max Verstappen", "team:9", "Red Bull")
        source = SeededRandomSource(42).spawn("attributes")
        item = apply_presets(
            generate_attributes(["driver:830"], source),
            load_driver_presets(PRESETS_PATH),
            source,
        )[0]
        with patch.object(
            catalog_router.catalog,
            "build_grid",
            return_value=((entry,), {entry.driver_id: item}, 42),
        ):
            response = catalog_router.build_grid(
                BuildGridRequest(
                    size=1,
                    mode="manual",
                    pair_ids=["driver:830@team:9"],
                    seed=42,
                )
            )

        payload = response.grid[0].attributes
        self.assertEqual(payload.aggression, 1.48)
        self.assertEqual(payload.composure, 0.9)
        self.assertEqual(payload.sources["aggression"], "preset")

    def test_patch_grid_route_accepts_new_fields_and_marks_manual_origin(self) -> None:
        entry = GridEntry("driver:830", "Max Verstappen", "team:9", "Red Bull")
        original = generated(["driver:830"])[0]
        edited = apply_overrides(
            [original], {"driver:830": {"aggression": 1.33, "composure": 1.07}}
        )[0]
        request = EditGridAttributesRequest(
            overrides=[
                AttributeOverride(
                    driver_id="driver:830", aggression=1.33, composure=1.07
                )
            ]
        )
        with patch.object(
            catalog_router.catalog,
            "edit_current_grid",
            return_value=((entry,), {entry.driver_id: edited}, 42),
        ):
            response = catalog_router.edit_grid_attributes(request)

        payload = response.grid[0].attributes
        self.assertEqual(payload.aggression, 1.33)
        self.assertEqual(payload.composure, 1.07)
        self.assertEqual(payload.sources["aggression"], "manual")
        self.assertEqual(payload.sources["composure"], "manual")

    def test_grid_json_round_trip_preserves_new_fields_and_sources(self) -> None:
        entry = GridEntry("driver:830", "Max Verstappen", "team:9", "Red Bull")
        source = SeededRandomSource(42).spawn("attributes")
        item = apply_presets(
            generate_attributes(["driver:830"], source),
            load_driver_presets(PRESETS_PATH),
            source,
        )[0]

        state = catalog_service._serialize_grid((entry,), {entry.driver_id: item}, 42)
        pairs, restored, seed = catalog_service._deserialize_grid(state)

        self.assertEqual(pairs, (entry,))
        self.assertEqual(restored[entry.driver_id], item)
        self.assertEqual(seed, 42)


if __name__ == "__main__":
    unittest.main()
