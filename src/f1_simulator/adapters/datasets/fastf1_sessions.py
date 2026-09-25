"""Normalize FastF1 sessions without joining or interpolating sample clocks.

FastF1/Pandas are optional acquisition dependencies. The adapter also accepts
an injected session and ordinary record lists for deterministic tests. Only
this boundary understands vendor columns, missing sentinels and decimetres.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from importlib.metadata import version, PackageNotFoundError

from f1_simulator.domain.history import Scalar

from f1_simulator.domain.session_data import SESSION_SCHEMA, SESSION_TABLES

FASTF1_VERSION = "3.8.3"
SESSION_KINDS = ("R", "Q", "FP1", "FP2", "FP3", "S", "SQ", "SS")


class FastF1DatasetError(ValueError):
    """A session cannot be mapped safely to the canonical historical catalog."""


def load_session(
    season: int, round_number: int, kind: str, cache: Path, *, telemetry: bool = True
) -> Any:
    """Acquire one selected session; never download telemetry in the motor.

    The caller owns the cache lifecycle. The fixed library version identifies
    transformations; it is not a version identifier or license for upstream data.
    """
    try:
        import fastf1
    except ImportError as error:
        raise FastF1DatasetError(
            "install requirements-etl.txt in an isolated environment"
        ) from error
    if fastf1.__version__ != FASTF1_VERSION:
        raise FastF1DatasetError(
            f"expected FastF1 {FASTF1_VERSION}, got {fastf1.__version__}"
        )
    if season < 2018 or kind not in SESSION_KINDS:
        raise FastF1DatasetError(
            "timing enrichment requires season >= 2018 and a supported session kind"
        )
    cache.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache))
    session = fastf1.get_session(season, round_number, kind)
    session.load(laps=True, telemetry=telemetry, weather=True, messages=True)
    return session


def _scalar(value):
    """Convert numpy scalars and Pandas absence without losing false or zero."""
    if value is None or type(value).__name__ in ("NAType", "NaTType"):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        return value.strip() or None
    return value


def _milliseconds(value):
    value = _scalar(value)
    if value is None:
        return None
    if not isinstance(value, timedelta):
        raise FastF1DatasetError(f"expected timedelta, got {type(value).__name__}")
    microseconds = (value.days * 86400 + value.seconds) * 1_000_000 + value.microseconds
    return int(
        (Decimal(microseconds) / 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    )


def _utc(value):
    value = _scalar(value)
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise FastF1DatasetError(f"expected datetime, got {type(value).__name__}")
    # FastF1 timing timestamps are UTC but commonly timezone-naive. This is a
    # source convention, never an inference from the machine's local timezone.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _rows(frame):
    if hasattr(frame, "itertuples"):
        yield from (
            dict(zip(frame.columns, values))
            for values in frame.itertuples(index=False, name=None)
        )
    else:
        yield from frame


# Mapping values: canonical name, conversion. Durations are explicit rather
# than inferred from a suffix: wind_speed_ms means m/s, not milliseconds.
_LAPS = {
    "LapNumber": ("lap_number", "int"),
    "LapTime": ("lap_time_ms", "duration"),
    "Time": ("session_time_ms", "duration"),
    "LapStartTime": ("lap_start_ms", "duration"),
    "LapStartDate": ("lap_start_date_utc", "utc"),
    "Stint": ("stint", "int"),
    "PitInTime": ("pit_in_ms", "duration"),
    "PitOutTime": ("pit_out_ms", "duration"),
    **{f"Sector{i}Time": (f"sector{i}_ms", "duration") for i in (1, 2, 3)},
    **{
        f"Sector{i}SessionTime": (f"sector{i}_session_ms", "duration")
        for i in (1, 2, 3)
    },
    **{
        f"Speed{trap.upper()}": (f"speed_{trap}_kmh", "float")
        for trap in ("i1", "i2", "fl", "st")
    },
    "Compound": ("compound", "text"),
    "TyreLife": ("tyre_life_laps", "float"),
    "FreshTyre": ("fresh_tyre", "bool"),
    "IsPersonalBest": ("personal_best", "bool"),
    "TrackStatus": ("track_status", "text"),
    "Position": ("position", "int"),
    "Deleted": ("deleted", "bool"),
    "DeletedReason": ("deleted_reason", "text"),
    "FastF1Generated": ("generated", "bool"),
    "IsAccurate": ("accurate", "bool"),
}
_RESULTS = {
    "DriverNumber": ("driver_number", "int"),
    "DriverId": ("external_driver_ref", "text"),
    "TeamId": ("external_team_ref", "text"),
    "TeamName": ("team_name", "text"),
    "Abbreviation": ("abbreviation", "text"),
    "TeamColor": ("team_color", "text"),
    "HeadshotUrl": ("headshot_url", "text"),
    "CountryCode": ("country_code", "text"),
    "Position": ("position", "int"),
    "ClassifiedPosition": ("classified_position", "text"),
    "GridPosition": ("grid_position", "int"),
    "Points": ("points", "float"),
    "Status": ("status", "text"),
    "Laps": ("laps_completed", "int"),
    "Time": ("result_time_ms", "duration"),
    **{f"Q{i}": (f"q{i}_ms", "duration") for i in (1, 2, 3)},
}
_CLOCK = {"Time": ("session_time_ms", "duration"), "Date": ("date_utc", "utc")}
MAPPINGS = {
    "session_drivers": _RESULTS,
    "lap_observations": _LAPS,
    "weather_observations": {
        "Time": ("session_time_ms", "duration"),
        "AirTemp": ("air_temperature_c", "float"),
        "TrackTemp": ("track_temperature_c", "float"),
        "Humidity": ("humidity_pct", "float"),
        "Pressure": ("pressure_mbar", "float"),
        "Rainfall": ("rainfall", "bool"),
        "WindDirection": ("wind_direction_deg", "float"),
        "WindSpeed": ("wind_speed_ms", "float"),
    },
    "track_status_events": {
        "Time": ("session_time_ms", "duration"),
        "Status": ("status", "text"),
        "Message": ("message", "text"),
    },
    "session_status_events": {
        "Time": ("session_time_ms", "duration"),
        "Status": ("status", "text"),
    },
    "race_control_messages": {
        "Time": ("date_utc", "utc"),
        "Category": ("category", "text"),
        "Message": ("message", "text"),
        "Status": ("status", "text"),
        "Flag": ("flag", "text"),
        "Scope": ("scope", "text"),
        "Sector": ("sector", "int"),
        "RacingNumber": ("driver_number", "int"),
        "Lap": ("lap_number", "int"),
    },
    "car_samples": {
        **_CLOCK,
        "Speed": ("speed_kmh", "float"),
        "RPM": ("rpm", "int"),
        "nGear": ("gear", "int"),
        "Throttle": ("throttle_pct", "float"),
        "Brake": ("brake", "bool"),
        "DRS": ("drs_code", "int"),
        "Source": ("sample_source", "text"),
    },
    "position_samples": {
        **_CLOCK,
        "X": ("x_m", "decimetres"),
        "Y": ("y_m", "decimetres"),
        "Z": ("z_m", "decimetres"),
        "Status": ("status", "text"),
        "Source": ("sample_source", "text"),
    },
    "circuit_markers": {
        "X": ("map_x", "float"),
        "Y": ("map_y", "float"),
        "Number": ("number", "int"),
        "Letter": ("letter", "text"),
        "Angle": ("label_angle_deg", "float"),
        "Distance": ("estimated_distance_m", "float"),
    },
}


def _convert(value, kind):
    value = _scalar(value)
    if value is None:
        return None
    if kind == "duration":
        return _milliseconds(value)
    if kind == "utc":
        return _utc(value)
    if kind == "text":
        return str(value)
    if kind == "bool":
        if type(value) is bool or type(value) in (int, float) and value in (0, 1):
            return bool(value)
        raise FastF1DatasetError(f"invalid boolean: {value!r}")
    if kind == "int":
        number = float(value)
        if not math.isfinite(number) or not number.is_integer():
            raise FastF1DatasetError(f"invalid integer: {value!r}")
        return int(number)
    return float(value) / 10 if kind == "decimetres" else float(value)


class FastF1SessionAdapter:
    """Supplement a catalog by event and session, mapping drivers explicitly.

    Driver numbers are resolved only within this session's results, after
    matching DriverId to the catalog's driver_ref. Unknown identities fail;
    no matching by global number, approximate name or finishing position occurs.
    Optional unavailable feeds are reported, and strict mode rejects them.
    """

    tables = SESSION_TABLES

    def __init__(
        self,
        session,
        race: Mapping[str, object],
        driver_refs: Mapping[str, str],
        kind: str,
        *,
        telemetry: bool = True,
        strict: bool = False,
    ) -> None:
        if kind not in SESSION_KINDS:
            raise FastF1DatasetError(f"unsupported session kind: {kind}")
        self.session, self.race, self.kind = session, race, kind
        if (
            int(session.event["RoundNumber"]) != race["round_number"]
            or session.date.year != race["season"]
        ):
            raise FastF1DatasetError(
                "session event does not match the catalog season/round"
            )
        names = {
            "R": {"Race"},
            "Q": {"Qualifying"},
            "FP1": {"Practice 1"},
            "FP2": {"Practice 2"},
            "FP3": {"Practice 3"},
            "S": {"Sprint"},
            "SQ": {"Sprint Qualifying", "Sprint Shootout"},
            "SS": {"Sprint Shootout", "Sprint Qualifying"},
        }
        if session.name not in names[kind]:
            raise FastF1DatasetError("loaded session does not match the requested kind")
        self.telemetry, self.strict = telemetry, strict
        self.session_id = f"session:{race['race_id'].split(':', 1)[1]}:{kind}"
        self.manifest = {
            "source_name": "fastf1",
            "source_version": FASTF1_VERSION,
            "source_sha256": None,
            "transform_version": "fastf1-session-1",
            "schema_version": 1,
            "session_id": self.session_id,
            "race_id": race["race_id"],
            "season": race["season"],
            "round_number": race["round_number"],
            "kind": kind,
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
            "upstream_api_path": getattr(session, "api_path", None),
            "url": "https://docs.fastf1.dev/data_reference/index.html",
            "software_license": "MIT",
            "data_license": "upstream terms; not covered by software MIT",
            "upstream_sources": [
                "F1 live timing",
                "Jolpica session results",
                "MultiViewer circuit markers",
            ],
            "retention": "local curated observations; cache managed by acquisition command; no raw data in Git",
            "coverage": {},
            "missing_columns": {},
            "warnings": {},
            "transforms": [
                "UTC timestamps",
                "durations rounded to milliseconds",
                "position decimetres to metres",
                "separate original sample clocks; no interpolation",
                "marker XY retained in upstream map frame",
            ],
        }
        self.results = list(_rows(self._feed("results", required=True)))
        dependencies = {}
        for package in ("fastf1", "pandas", "numpy"):
            try:
                dependencies[package] = version(package)
            except PackageNotFoundError:
                dependencies[package] = None
        self.manifest["dependency_versions"] = dependencies
        if not self.results:
            raise FastF1DatasetError(
                "session has no driver results for identity mapping"
            )
        self.drivers = {}
        for row in self.results:
            ref = _scalar(row.get("DriverId"))
            number = _convert(row.get("DriverNumber"), "int")
            if ref not in driver_refs or number is None:
                raise FastF1DatasetError(
                    f"driver mapping missing: DriverId={ref!r}, number={number!r}"
                )
            if number in self.drivers:
                raise FastF1DatasetError(f"duplicate session driver number: {number}")
            self.drivers[number] = driver_refs[ref]
        self.circuit_info = self._feed("get_circuit_info", call=True)

    def _feed(self, attribute, *, required=False, call=False):
        try:
            value = getattr(self.session, attribute)
            value = value() if call else value
            if value is None:
                raise FastF1DatasetError("source returned no feed")
            return value
        except Exception as error:
            # FastF1 soft-fails individual feeds and its circuit-info helper can
            # fail separately. Record every failure; never convert it to "dry"
            # or an empty successful measurement. Strict mode preserves failure.
            self.manifest["coverage"][attribute] = {
                "status": "unavailable",
                "reason": f"{type(error).__name__}: {error}",
            }
            if required or self.strict:
                raise FastF1DatasetError(f"{attribute} unavailable: {error}") from error
            return None

    def _normalize(self, table, row, **keys):
        result = dict.fromkeys(SESSION_SCHEMA[table].names)
        result.update(session_id=self.session_id, **keys)
        mapping = MAPPINGS[table]
        missing = self.manifest["missing_columns"].setdefault(table, [])
        for source, (target, kind) in mapping.items():
            if source not in row and source not in missing:
                missing.append(source)
            result[target] = _convert(row.get(source), kind)
        if table == "car_samples":
            result["throttle_raw_pct"] = result["throttle_pct"]
            if (
                result["throttle_pct"] is not None
                and not 0 <= result["throttle_pct"] <= 100
            ):
                # Preserve sentinels such as 104 for audit, while consumers see
                # unknown pedal input rather than a fabricated/clipped percent.
                warnings = self.manifest["warnings"]
                warnings["invalid_throttle_pct"] = (
                    warnings.get("invalid_throttle_pct", 0) + 1
                )
                result["throttle_pct"] = None
        return result

    def _driver(self, number):
        number = _convert(number, "int")
        if number not in self.drivers:
            raise FastF1DatasetError(f"unknown driver number in session: {number}")
        return self.drivers[number]

    def rows(self, table: str) -> Iterator[dict[str, Scalar]]:
        """Yield canonical rows and distinguish unavailable, empty and skipped feeds."""
        count = 0
        for row in self._table_rows(table):
            count += 1
            yield row
        self.manifest["coverage"].setdefault(
            table, {"status": "available" if count else "empty"}
        )
        self.manifest["coverage"][table]["rows"] = count

    def _table_rows(self, table):
        if table == "sessions":
            yield dict(
                session_id=self.session_id,
                race_id=self.race["race_id"],
                kind=self.kind,
                name=self.session.name,
                event_format=_scalar(self.session.event.get("EventFormat")),
                date_utc=_utc(self.session.date),
                zero_time_utc=_utc(self._feed("t0_date")),
                start_time_ms=_milliseconds(self._feed("session_start_time")),
                circuit_rotation_deg=_scalar(
                    getattr(self.circuit_info, "rotation", None)
                ),
            )
            return
        if table == "session_drivers":
            for row in self.results:
                yield self._normalize(
                    table, row, driver_id=self._driver(row["DriverNumber"])
                )
            return
        if table == "circuit_markers":
            if self.circuit_info is None:
                self.manifest["coverage"][table] = {"status": "unavailable"}
                return
            sequence = 0
            for category in ("corners", "marshal_lights", "marshal_sectors"):
                for row in _rows(getattr(self.circuit_info, category)):
                    yield self._normalize(table, row, sequence=sequence, kind=category)
                    sequence += 1
            return
        feeds = {
            "lap_observations": "laps",
            "weather_observations": "weather_data",
            "track_status_events": "track_status",
            "session_status_events": "session_status",
            "race_control_messages": "race_control_messages",
            "car_samples": "car_data",
            "position_samples": "pos_data",
        }
        if table not in feeds:
            raise FastF1DatasetError(f"unknown session table: {table}")
        if table in ("car_samples", "position_samples") and not self.telemetry:
            self.manifest["coverage"][table] = {"status": "not_requested"}
            return
        frame = self._feed(feeds[table], required=table == "lap_observations")
        if frame is None:
            self.manifest["coverage"][table] = {"status": "unavailable"}
            return
        if table in ("car_samples", "position_samples"):
            missing = set(self.drivers) - {_convert(n, "int") for n in frame}
            self.manifest["coverage"][table] = {
                "status": "partial" if missing else "available",
                "missing_driver_numbers": sorted(missing),
            }
            if missing and self.strict:
                raise FastF1DatasetError(
                    f"{table}: missing telemetry for {sorted(missing)}"
                )
            for number, samples in frame.items():
                for sequence, row in enumerate(_rows(samples)):
                    yield self._normalize(
                        table, row, driver_id=self._driver(number), sequence=sequence
                    )
        else:
            for sequence, row in enumerate(_rows(frame)):
                keys = (
                    {"driver_id": self._driver(row.get("DriverNumber"))}
                    if table == "lap_observations"
                    else {"sequence": sequence}
                )
                yield self._normalize(table, row, **keys)
