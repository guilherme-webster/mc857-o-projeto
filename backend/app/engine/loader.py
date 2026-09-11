from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

from app.engine.models import DriverParameters


def load_driver_parameters(
    db_path: Path, *, limit: int | None = None
) -> list[DriverParameters]:

    if not db_path.exists():
        raise FileNotFoundError(f"curated race database not found: {db_path}")

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        entries = _read_entries(connection)
        parameters = [_build_parameters(connection, entry) for entry in entries]
    finally:
        connection.close()

    if limit is not None:
        parameters = parameters[:limit]
    return parameters


def _read_entries(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return one row per participating car, ordered by starting grid slot."""

    return connection.execute(
        """
        SELECT
            e.driver_id AS driver_id,
            e.team_id AS team_id,
            e.grid_position AS grid_position,
            d.given_name AS given_name,
            d.family_name AS family_name
        FROM race_entries AS e
        JOIN drivers AS d ON d.driver_id = e.driver_id
        ORDER BY
            CASE WHEN e.grid_position <= 0 THEN 1 ELSE 0 END,
            e.grid_position
        """
    ).fetchall()


def _build_parameters(
    connection: sqlite3.Connection, entry: sqlite3.Row
) -> DriverParameters:
    """Build parameters for one car; pace is ``None`` when it has no lap data.

    A car without laps (e.g. a withdrawal) cannot get a data-derived pace, so
    ``base_lap_time_ms`` stays ``None`` rather than receiving an invented value.
    """

    driver_id = entry["driver_id"]
    lap_times = [
        row["lap_time_ms"]
        for row in connection.execute(
            "SELECT lap_time_ms FROM laps WHERE driver_id = ? ORDER BY lap_number",
            (driver_id,),
        )
    ]
    base_lap_time_ms = _estimate_base_pace(lap_times) if lap_times else None

    return DriverParameters(
        driver_id=driver_id,
        name=_display_name(entry),
        team_id=entry["team_id"],
        grid_position=entry["grid_position"],
        base_lap_time_ms=base_lap_time_ms,
        degradation_ms_per_lap=_estimate_degradation(lap_times), # TODO
        pit_loss_ms=_estimate_pit_loss(connection, driver_id), # TODO
    )


def _estimate_base_pace(lap_times: list[int]) -> float:
    """Use the median of the fastest quartile as clean-air pace.

    The fastest laps approximate low-fuel, fresh-tire running, which is a better
    baseline than the overall mean skewed by traffic and worn tires. Assumes a
    non-empty input, guaranteed by the caller.
    """

    ordered = sorted(lap_times)
    quartile = max(1, len(ordered) // 4)
    return float(statistics.median(ordered[:quartile]))


def _estimate_degradation(lap_times: list[int]) -> float:
    """Approximate per-lap degradation from the least-squares trend of lap times.

    The slope over lap index captures how much slower the car gets each lap.
    With fewer than three laps, or a flat/negative trend (fuel burn dominating),
    the result is ``0.0``: the source shows no measurable degradation, which is a
    fact rather than a placeholder.
    """

    count = len(lap_times)
    if count < 3:
        return 0.0

    indices = range(count)
    mean_x = (count - 1) / 2
    mean_y = statistics.fmean(lap_times)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(indices, lap_times))
    denominator = sum((x - mean_x) ** 2 for x in indices)
    if denominator == 0:
        return 0.0
    slope = numerator / denominator
    return max(0.0, slope)


def _estimate_pit_loss(connection: sqlite3.Connection, driver_id: str) -> float:
    """Average recorded pit-stop duration in milliseconds.

    Returns ``0.0`` when the car has no recorded stop with a duration: the
    source reports no pit loss, so none is applied.
    """

    durations = [
        row["duration_ms"]
        for row in connection.execute(
            "SELECT duration_ms FROM pit_stops "
            "WHERE driver_id = ? AND duration_ms IS NOT NULL",
            (driver_id,),
        )
    ]
    if not durations:
        return 0.0
    return float(statistics.fmean(durations))


def _display_name(entry: sqlite3.Row) -> str:
    """Build a readable driver name from the available name columns."""

    given = (entry["given_name"] or "").strip()
    family = (entry["family_name"] or "").strip()
    full = f"{given} {family}".strip()
    return full or entry["driver_id"]
