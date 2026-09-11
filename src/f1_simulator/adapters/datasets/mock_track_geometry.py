"""Read the reduced track/pit CSV artifacts of ADR 0003, never live telemetry."""

import csv
import hashlib
import io
import json
import math
from datetime import date
from pathlib import Path

from f1_simulator.application.track_geometry_dto import NormalizedTrackGeometry


class MockTrackDatasetError(ValueError):
    """Reduced geometry or its companion provenance is missing or inconsistent."""


class MockTrackDatasetAdapter:
    """Normalize the issue #51 artifacts without requiring Pandas or FastF1.

    These CSVs map Trotman circuitId to canonical circuit:<id>. Their XY is
    already centered and uniformly scaled; independently rescaling the pit
    lane would detach it from the track. Original values are preserved.
    """

    def __init__(
        self,
        track_points: Path,
        track_manifest: Path,
        pit_lane_points: Path,
        pit_lane_manifest: Path,
    ) -> None:
        """Configure explicit artifact/manifest pairs; no implicit download occurs."""

        self._track = (track_points, track_manifest)
        self._pit = (pit_lane_points, pit_lane_manifest)

    def load_geometry(self, circuit_id: str) -> NormalizedTrackGeometry:
        """Verify checksums, shared coordinates and source metadata before parsing.

        Manifest paths are supplied by the caller; the artifact path mentioned
        inside a manifest is documentation and is never followed. Checksums
        detect mismatched inputs, not authenticity of an untrusted manifest.
        """

        try:
            if not isinstance(circuit_id, str) or not circuit_id.startswith("circuit:"):
                raise MockTrackDatasetError("expected canonical circuit:<id>")
            external_id = circuit_id.removeprefix("circuit:")
            if not external_id.isdecimal() or int(external_id) <= 0:
                raise MockTrackDatasetError(
                    "circuit ID must map to a positive Trotman ID"
                )
            track_bytes, track_manifest, track_source = self._read_pair(*self._track)
            pit_bytes, pit_manifest, pit_source = self._read_pair(*self._pit)
            if (
                pit_manifest["transform"]["track_artifact_sha256"]
                != track_source["artifact_sha256"]
            ):
                raise MockTrackDatasetError(
                    "pit lane was generated for a different track artifact"
                )
            track = self._rows(track_bytes, external_id, pit=False)
            pit = self._rows(pit_bytes, external_id, pit=True)
            for manifest, points in ((track_manifest, track), (pit_manifest, pit)):
                events = [
                    e
                    for e in manifest["source"]["events"]
                    if e["circuit_id"] == external_id
                ]
                if len(events) != 1 or events[0]["point_count"] != len(points):
                    raise MockTrackDatasetError(
                        "manifest must identify the circuit and its point count"
                    )
            track_event = next(
                e
                for e in track_manifest["source"]["events"]
                if e["circuit_id"] == external_id
            )
            # The existing CSV stores distances to three decimal places. This
            # tolerance covers only that rounding, never a layout discrepancy.
            if not math.isclose(
                track[-1]["cumulative_distance_m"],
                float(track_event["lap_length_m"]),
                rel_tol=0,
                abs_tol=0.001,
            ):
                raise MockTrackDatasetError("lap distance differs from its manifest")
            return NormalizedTrackGeometry(
                circuit_id, track, pit, track_source, pit_source
            )
        except MockTrackDatasetError:
            raise
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            csv.Error,
        ) as error:
            raise MockTrackDatasetError(
                f"cannot normalize geometry for {circuit_id}: {error}"
            ) from error

    @staticmethod
    def _read_pair(artifact_path: Path, manifest_path: Path):
        raw = artifact_path.read_bytes()
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        checksum = hashlib.sha256(raw).hexdigest()
        if checksum != manifest["artifact_sha256"]:
            raise MockTrackDatasetError(f"artifact checksum mismatch: {artifact_path}")
        source = manifest["source"]
        transform = manifest["transform"]
        for field in ("coordinates", "sampling"):
            if not isinstance(transform[field], str) or not transform[field].strip():
                raise MockTrackDatasetError(f"manifest {field} must be non-empty text")
        return (
            raw,
            manifest,
            {
                "source_name": source["library"],
                "source_version": source["library_version"],
                "source_year": source["year"],
                "generated_on": date.fromisoformat(manifest["generated_at"]),
                # The pit manifest omits this label. Keep the absence explicit;
                # its upstream licence and link to the track checksum are retained.
                "upstream": source.get("upstream"),
                "upstream_data_license": source["upstream_data_license"],
                "artifact_sha256": checksum,
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "transformation": f"{transform['coordinates']}; {transform['sampling']}",
            },
        )

    @staticmethod
    def _rows(
        raw: bytes, external_id: str, *, pit: bool
    ) -> tuple[dict[str, object], ...]:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        progress_field = "pathFraction" if pit else "cumulativeDistanceMeters"
        required = {"circuitId", "sequence", "x", "y", progress_field}
        if pit:
            required.add("isServicePoint")
        if not required.issubset(reader.fieldnames or ()):
            raise MockTrackDatasetError(
                f"missing geometry columns: {sorted(required - set(reader.fieldnames or ()))}"
            )
        rows = []
        for row in reader:
            if row["circuitId"] != external_id:
                continue
            normalized = {
                "sequence": int(row["sequence"]),
                "x_normalized": float(row["x"]),
                "y_normalized": float(row["y"]),
                "path_fraction" if pit else "cumulative_distance_m": float(
                    row[progress_field]
                ),
            }
            if pit:
                if row["isServicePoint"] not in ("true", "false"):
                    raise MockTrackDatasetError("isServicePoint must be true or false")
                normalized["is_service_point"] = row["isServicePoint"] == "true"
            rows.append(normalized)
        if not rows:
            raise MockTrackDatasetError(
                f"no {'pit lane' if pit else 'track'} for circuitId={external_id}"
            )
        return tuple(sorted(rows, key=lambda row: row["sequence"]))
