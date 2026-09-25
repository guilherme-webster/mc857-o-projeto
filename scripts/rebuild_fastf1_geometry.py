#!/usr/bin/env python3
"""Reconstruct reduced 2025 track and pit-lane CSVs from FastF1 observations.

The original acquisition script was never committed. This is a documented
reconstruction of the transformations in ADR 0003, not a claim that it will
reproduce the historical CSV checksums byte for byte. Nothing is downloaded
or written when this module is imported.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
import tempfile
from bisect import bisect_right
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACK_MANIFEST = ROOT / "data/sources/fastf1-tracks-2025.json"
PIT_MANIFEST = ROOT / "data/sources/fastf1-pit-lanes-2025.json"
VERSION = "3.8.3"


@dataclass(frozen=True)
class Transform:
    """Common origin and scale; pit coordinates must never be scaled alone."""

    center_x: float
    center_y: float
    half_span: float

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.center_x) / self.half_span, (
            y - self.center_y
        ) / self.half_span


def _finite_rows(rows, columns: tuple[str, ...]) -> list[tuple[float, ...]]:
    """Discard incomplete vendor samples, preserving the requested field order."""

    samples = []
    for row in rows:
        try:
            values = tuple(float(row[key]) for key in columns)
        except (KeyError, TypeError, ValueError):
            continue
        if all(math.isfinite(value) for value in values):
            samples.append(values)
    return samples


def _interpolate(
    samples: list[tuple[float, float, float]], progress: float
) -> tuple[float, float]:
    """Linearly interpolate X/Y along increasing distance or path progress."""

    positions = [sample[0] for sample in samples]
    upper = min(max(bisect_right(positions, progress), 1), len(samples) - 1)
    before, after = samples[upper - 1], samples[upper]
    weight = (progress - before[0]) / (after[0] - before[0])
    return (
        before[1] + weight * (after[1] - before[1]),
        before[2] + weight * (after[2] - before[2]),
    )


def _increasing(
    samples: list[tuple[float, float, float]],
) -> list[tuple[float, float, float]]:
    """Remove repeated/retrograde progress values before interpolation."""

    ordered = sorted(samples)
    result = []
    for sample in ordered:
        if not result or sample[0] > result[-1][0]:
            result.append(sample)
    if len(result) < 2 or result[-1][0] <= result[0][0]:
        raise ValueError("insufficient distinct geometry samples")
    return result


def reduce_track(
    rows, count: int = 240
) -> tuple[list[tuple[float, float, float]], Transform]:
    """Sample one lap at equal distance increments and close its centerline.

    Input Distance is metres. X/Y remain in the vendor coordinate system until
    a single uniform transformation is calculated for both track and pit lane.
    """

    if count < 4:
        raise ValueError("track needs at least four samples")
    samples = _increasing(_finite_rows(rows, ("Distance", "X", "Y")))
    start, end = samples[0][0], samples[-1][0]
    length = end - start
    original = [
        _interpolate(samples, start + length * index / (count - 1))
        for index in range(count)
    ]
    # Closing only the display polyline does not change the measured lap length.
    original[-1] = original[0]
    xs, ys = zip(*original)
    half_span = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
    if half_span <= 0:
        raise ValueError("track has no spatial extent")
    transform = Transform((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, half_span)
    reduced = [
        (*transform.apply(x, y), length * index / (count - 1))
        for index, (x, y) in enumerate(original)
    ]
    return reduced, transform


def reduce_pit(
    rows,
    transform: Transform,
    service_time_s: float,
    count: int = 80,
) -> tuple[list[tuple[float, float, float, bool]], int]:
    """Resample a pit transit by geometric progress, marking one service point.

    Input rows contain SessionTime in seconds, X and Y. The time of the middle
    minimum-speed car sample identifies a representative stop, not a garage.
    """

    if count < 2:
        raise ValueError("pit lane needs at least two samples")
    timed = sorted(_finite_rows(rows, ("SessionTime", "X", "Y")))
    if len(timed) < 2:
        raise ValueError("pit lane has insufficient position samples")
    path = [(0.0, timed[0][1], timed[0][2])]
    for _, x, y in timed[1:]:
        previous = path[-1]
        progress = previous[0] + math.hypot(x - previous[1], y - previous[2])
        if progress > previous[0]:
            path.append((progress, x, y))
    if len(path) < 2:
        raise ValueError("pit lane has no spatial extent")
    total = path[-1][0]
    reduced = []
    for index in range(count):
        x, y = _interpolate(path, total * index / (count - 1))
        reduced.append((*transform.apply(x, y), index / (count - 1), False))
    nearest_observed = min(timed, key=lambda item: abs(item[0] - service_time_s))
    nearest_index = min(
        range(count),
        key=lambda index: math.dist(
            reduced[index][:2], transform.apply(*nearest_observed[1:])
        ),
    )
    x, y, fraction, _ = reduced[nearest_index]
    reduced[nearest_index] = (x, y, fraction, True)
    return reduced, nearest_index


def _selected_lap(session, driver: str, lap_number: int):
    laps = session.laps
    selected = laps[(laps["Driver"] == driver) & (laps["LapNumber"] == lap_number)]
    if len(selected) != 1:
        raise ValueError(f"expected one lap for {driver} lap {lap_number}")
    return selected.iloc[0]


def _load_session(round_number: int, cache_dir: Path):
    """The only network boundary; FastF1 is optional outside offline acquisition."""

    try:
        import fastf1
    except ImportError as error:
        raise RuntimeError(
            "install requirements-etl.txt in an isolated environment"
        ) from error
    if fastf1.__version__ != VERSION:
        raise RuntimeError(f"expected FastF1 {VERSION}, got {fastf1.__version__}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))
    session = fastf1.get_session(2025, round_number, "R")
    session.load(laps=True, telemetry=True, weather=False, messages=False)
    return session


def _session_rows(session, track_event: dict, pit_event: dict):
    """Extract only the recorded lap and pit transit, never persist raw feeds."""

    import pandas as pd  # FastF1 dependency; loaded only during acquisition

    lap = _selected_lap(session, track_event["driver"], track_event["lap_number"])
    telemetry = lap.get_telemetry()
    track_rows = telemetry[["Distance", "X", "Y"]].to_dict("records")
    in_lap = _selected_lap(session, pit_event["driver"], pit_event["pit_in_lap"])
    out_lap = _selected_lap(session, pit_event["driver"], pit_event["pit_out_lap"])
    if pd.isna(in_lap["PitInTime"]) or pd.isna(out_lap["PitOutTime"]):
        raise ValueError("recorded pit-in/out time is unavailable")
    start_s = in_lap["PitInTime"].total_seconds()
    end_s = out_lap["PitOutTime"].total_seconds()
    if end_s <= start_s:
        raise ValueError("pit-out must be after pit-in")
    driver_number = str(in_lap["DriverNumber"])
    positions = session.pos_data[driver_number]
    cars = session.car_data[driver_number]
    pos_rows = [
        {"SessionTime": row.SessionTime.total_seconds(), "X": row.X, "Y": row.Y}
        for row in positions.itertuples()
        if pd.notna(row.SessionTime)
        and start_s <= row.SessionTime.total_seconds() <= end_s
    ]
    speed_rows = [
        (row.SessionTime.total_seconds(), float(row.Speed))
        for row in cars.itertuples()
        if pd.notna(row.SessionTime)
        and pd.notna(row.Speed)
        and start_s <= row.SessionTime.total_seconds() <= end_s
    ]
    if not speed_rows:
        raise ValueError("no car-speed samples for the selected pit stop")
    minimum = min(speed for _, speed in speed_rows)
    stopped = [time_s for time_s, speed in speed_rows if speed == minimum]
    return track_rows, pos_rows, stopped[len(stopped) // 2], minimum


def _number(value: float, places: int) -> str:
    """Round only at the CSV boundary, retaining a decimal on whole values."""

    rounded = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return rounded if "." in rounded else f"{rounded}.0"


def _csv_bytes(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def rebuild(
    track_manifest: dict,
    pit_manifest: dict,
    rounds: set[int] | None = None,
    *,
    loader=_load_session,
    cache_dir: Path,
) -> tuple[bytes, bytes, dict]:
    """Generate both CSVs in memory; fail before publishing incomplete results."""

    track_events = track_manifest["source"]["events"]
    pit_events = {
        event["round_number"]: event for event in pit_manifest["source"]["events"]
    }
    if (
        track_manifest["source"]["year"] != 2025
        or pit_manifest["source"]["year"] != 2025
    ):
        raise ValueError("this generator is restricted to the 2025 manifests")
    if (
        pit_manifest["transform"]["track_artifact_sha256"]
        != track_manifest["artifact_sha256"]
    ):
        raise ValueError("pit manifest references a different track artifact")
    if len(track_events) != len(pit_events):
        raise ValueError("track and pit manifests cover different events")
    if rounds and not rounds <= {event["round_number"] for event in track_events}:
        raise ValueError("requested round missing from track manifest")
    tracks: list[tuple[str, ...]] = []
    pits: list[tuple[str, ...]] = []
    report_events = []
    for event in track_events:
        round_number = event["round_number"]
        if rounds is not None and round_number not in rounds:
            continue
        pit_event = pit_events.get(round_number)
        if pit_event is None or pit_event["circuit_id"] != event["circuit_id"]:
            raise ValueError(f"pit manifest does not match round {round_number}")
        session = loader(round_number, cache_dir)
        track_rows, pit_rows, service_time, minimum_speed = _session_rows(
            session, event, pit_event
        )
        track, transform = reduce_track(track_rows)
        pit, service_index = reduce_pit(pit_rows, transform, service_time)
        circuit_id = event["circuit_id"]
        tracks.extend(
            (circuit_id, str(index), _number(x, 6), _number(y, 6), _number(distance, 3))
            for index, (x, y, distance) in enumerate(track)
        )
        pits.extend(
            (
                circuit_id,
                str(index),
                _number(x, 6),
                _number(y, 6),
                _number(fraction, 6),
                str(service).lower(),
            )
            for index, (x, y, fraction, service) in enumerate(pit)
        )
        report_events.append(
            {
                "round_number": round_number,
                "circuit_id": circuit_id,
                "track_driver": event["driver"],
                "track_lap": event["lap_number"],
                "pit_driver": pit_event["driver"],
                "pit_in_lap": pit_event["pit_in_lap"],
                "pit_out_lap": pit_event["pit_out_lap"],
                "minimum_speed_kph": minimum_speed,
                "service_path_fraction": pit[service_index][2],
                "lap_length_m": track[-1][2],
            }
        )
        print(
            f"processed round {round_number}: {event['circuit_name']}", file=sys.stderr
        )
    track_data = _csv_bytes(
        ("circuitId", "sequence", "x", "y", "cumulativeDistanceMeters"), tracks
    )
    pit_data = _csv_bytes(
        ("circuitId", "sequence", "x", "y", "pathFraction", "isServicePoint"), pits
    )
    report = {
        "reconstruction": True,
        "warning": "Original generation code was not versioned; byte-identical CSVs are not guaranteed.",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "upstream": "F1 live timing",
            "library": "FastF1",
            "library_version": VERSION,
            "upstream_data_license": "upstream terms apply; FastF1 MIT covers the software only",
            "track_manifest": str(TRACK_MANIFEST.relative_to(ROOT)),
            "pit_manifest": str(PIT_MANIFEST.relative_to(ROOT)),
        },
        "transform": {
            "track": "finite Distance/X/Y samples; linear interpolation at 240 equal lap-distance intervals; centered uniform scale; closed display polyline",
            "pit": "positions between recorded pit-in/out; 80 equal geometric-progress intervals in track coordinates",
            "service_point": "nearest path sample to the middle minimum-speed car sample",
        },
        "track_sha256": hashlib.sha256(track_data).hexdigest(),
        "pit_sha256": hashlib.sha256(pit_data).hexdigest(),
        "events": report_events,
    }
    if len(report_events) == len(track_events):
        report["matches_historical_checksums"] = {
            "track": report["track_sha256"] == track_manifest["artifact_sha256"],
            "pit": report["pit_sha256"] == pit_manifest["artifact_sha256"],
        }
    return track_data, pit_data, report


def main(argv: list[str] | None = None) -> int:
    """Rebuild into a new directory, never replacing versioned artifacts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--round", type=int, action="append", dest="rounds")
    parser.add_argument(
        "--cache-dir", type=Path, help="optional persistent FastF1 cache"
    )
    args = parser.parse_args(argv)
    destination = args.output_dir.resolve()
    protected = (
        ROOT / "tests/fixtures/trotman_v128_tracks_2025",
        ROOT / "data/sources",
        ROOT / "data/raw",
    )
    if any(
        destination == path or destination.is_relative_to(path) for path in protected
    ):
        parser.error(
            "output directory cannot be inside versioned fixtures, sources or raw data"
        )
    if destination.exists():
        parser.error("output directory already exists; choose a new directory")
    track_manifest = json.loads(TRACK_MANIFEST.read_text(encoding="utf-8"))
    pit_manifest = json.loads(PIT_MANIFEST.read_text(encoding="utf-8"))
    cache_context = (
        nullcontext(args.cache_dir)
        if args.cache_dir
        else tempfile.TemporaryDirectory(prefix="fastf1-geometry-")
    )
    try:
        with cache_context as cache:
            track, pit, report = rebuild(
                track_manifest,
                pit_manifest,
                set(args.rounds) if args.rounds else None,
                cache_dir=Path(cache),
            )
        destination.mkdir(parents=True, exist_ok=False)
        (destination / "track_points.csv").write_bytes(track)
        (destination / "pit_lane_points.csv").write_bytes(pit)
        (destination / "generation_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    print(f"geometry written to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
