"""Transactional storage and Python queries for canonical historical facts."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from contextlib import closing
from pathlib import Path

from f1_simulator.domain.history import HISTORY_SCHEMA, HistoricalRecord, Scalar, Table
from f1_simulator.domain.race_data import RaceData
from f1_simulator.factories.history_factory import (
    HistoryFactory,
    HistoryValidationError,
)

SCHEMA_VERSION = 1


def _schema_sql(table: Table) -> str:
    """Generate SQL only from application-owned schemas, never upstream names."""
    types = {"int": "INTEGER", "bool": "INTEGER", "float": "REAL"}
    fields = [
        f'"{c.name}" {types.get(c.kind, "TEXT")}'
        + (" NOT NULL" if not c.nullable or c.name in table.key else "")
        for c in table.columns
    ]
    fields.append("PRIMARY KEY (" + ",".join(f'"{key}"' for key in table.key) + ")")
    fields.extend(
        f'FOREIGN KEY ("{field}") REFERENCES "{target}"("{key}") DEFERRABLE INITIALLY DEFERRED'
        for field, target, key in table.references
    )
    return f'CREATE TABLE IF NOT EXISTS "{table.name}" ({", ".join(fields)})'


class SQLiteHistoryWriter:
    """Build a sibling temporary database, validate it, then publish atomically.

    Enrichment uses SQLite backup to copy a consistent base snapshot. Failure
    never removes or modifies the old output/base. Each session is replaceable
    independently; other sessions and historical tables remain intact. The
    authoritative quality report is embedded in the same committed database.
    """

    def write(
        self,
        tables: tuple[Table, ...],
        records: Iterable[HistoricalRecord],
        manifest: dict[str, object],
        destination: Path,
        *,
        overwrite: bool = False,
        base: Path | None = None,
    ) -> dict[str, object]:
        """Write validated rows, preserving a base and reporting missing values."""
        destination = destination.resolve()
        if destination.exists() and not overwrite:
            raise FileExistsError(f"output already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        os.close(fd)
        temporary = Path(name)
        try:
            with closing(sqlite3.connect(temporary)) as connection:
                if base is not None:
                    with closing(_connect(base)) as original:
                        if (
                            original.execute("PRAGMA user_version").fetchone()[0]
                            != SCHEMA_VERSION
                        ):
                            raise HistoryValidationError(
                                "base must be a complete history database, schema version 1"
                            )
                        original.backup(connection)
                connection.execute("PRAGMA foreign_keys=ON")
                with connection:
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS imports (import_key TEXT PRIMARY KEY, manifest_json TEXT NOT NULL, report_json TEXT NOT NULL)"
                    )
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
                    )
                    if base is None:
                        connection.executemany(
                            "INSERT INTO metadata VALUES (?, ?)",
                            (
                                (
                                    key,
                                    str(manifest[key])
                                    if manifest.get(key) is not None
                                    else None,
                                )
                                for key in (
                                    "source_name",
                                    "source_version",
                                    "source_sha256",
                                )
                            ),
                        )
                    for table in tables:
                        connection.execute(_schema_sql(table))
                        actual = tuple(
                            r[1]
                            for r in connection.execute(
                                f'PRAGMA table_info("{table.name}")'
                            )
                        )
                        if actual != table.names:
                            raise HistoryValidationError(
                                f"incompatible schema for {table.name}"
                            )
                    session_id = manifest.get("session_id")
                    if session_id is not None:
                        # Delete children first for readable diagnostics; deferred
                        # FKs then validate the full replacement at commit time.
                        for table in reversed(tables):
                            connection.execute(
                                f'DELETE FROM "{table.name}" WHERE session_id=?',
                                (session_id,),
                            )
                    specs = {t.name: t for t in tables}
                    counts: dict[str, int] = dict.fromkeys(specs, 0)
                    nulls: dict[str, int] = defaultdict(int)
                    digest = hashlib.sha256()
                    statements = {
                        name: f'INSERT INTO "{name}" VALUES ({",".join("?" for _ in table.columns)})'
                        for name, table in specs.items()
                    }
                    for record in records:
                        if record.table not in specs:
                            raise HistoryValidationError(
                                f"unrequested table: {record.table}"
                            )
                        values = record.as_dict()
                        # Public writers and repositories share the validation
                        # boundary, including for records assembled by callers.
                        valid = HistoryFactory.build(specs[record.table], values)
                        connection.execute(
                            statements[record.table], tuple(v for _, v in valid.fields)
                        )
                        counts[record.table] += 1
                        for field, value in valid.fields:
                            if value is None:
                                nulls[f"{record.table}.{field}"] += 1
                        digest.update(
                            json.dumps(
                                [record.table, valid.fields],
                                ensure_ascii=False,
                                allow_nan=False,
                                separators=(",", ":"),
                            ).encode()
                        )
                        digest.update(b"\n")
                    if base is None and "race_results" in specs:
                        self._legacy_views(connection)
                        for table, ref in (
                            ("drivers", "driver_ref"),
                            ("teams", "team_ref"),
                            ("circuits", "circuit_ref"),
                        ):
                            connection.execute(
                                f'CREATE UNIQUE INDEX "{table}_ref" ON "{table}"("{ref}")'
                            )
                        connection.execute(
                            "CREATE INDEX laps_lookup ON laps(race_id, driver_id, lap_number)"
                        )
                        connection.execute(
                            "CREATE INDEX results_lookup ON race_results(race_id, driver_id)"
                        )
                        connection.execute(
                            "CREATE INDEX races_season ON races(season, round_number)"
                        )
                    violations = connection.execute(
                        "PRAGMA foreign_key_check"
                    ).fetchmany(10)
                    if violations:
                        raise HistoryValidationError(f"orphan references: {violations}")
                    if session_id is not None:
                        for table in (
                            "lap_observations",
                            "car_samples",
                            "position_samples",
                        ):
                            outsider = connection.execute(
                                f'''SELECT o.driver_id FROM "{table}" o
                                LEFT JOIN session_drivers d ON d.session_id=o.session_id AND d.driver_id=o.driver_id
                                WHERE o.session_id=? AND d.driver_id IS NULL LIMIT 1''',
                                (session_id,),
                            ).fetchone()
                            if outsider:
                                raise HistoryValidationError(
                                    f"{table}: driver outside session: {outsider[0]}"
                                )
                    report = {
                        "schema_version": SCHEMA_VERSION,
                        "row_counts": counts,
                        "null_counts": dict(sorted(nulls.items())),
                        "duplicate_keys": 0,
                        "orphan_references": 0,
                        "canonical_sha256": digest.hexdigest(),
                        "source": manifest,
                    }
                    if "laps" in specs:
                        duplicate_laps = connection.execute("""SELECT race_id, driver_id, lap_number, COUNT(*),
                            COUNT(DISTINCT lap_time_ms), COUNT(DISTINCT position)
                            FROM laps GROUP BY race_id, driver_id, lap_number HAVING COUNT(*)>1""").fetchall()
                        report["business_key_warnings"] = {
                            "duplicate_lap_keys": len(duplicate_laps),
                            "extra_lap_observations": sum(
                                row[3] - 1 for row in duplicate_laps
                            ),
                            "conflicting_lap_keys": sum(
                                row[4] > 1 or row[5] > 1 for row in duplicate_laps
                            ),
                            "affected_race_ids": sorted(
                                {row[0] for row in duplicate_laps}
                            ),
                        }
                    if session_id is not None:
                        report["lap_time_comparison"] = self._lap_comparison(
                            connection, session_id
                        )
                    key = str(session_id or manifest["source_name"])
                    connection.execute(
                        "INSERT OR REPLACE INTO imports VALUES (?, ?, ?)",
                        (
                            key,
                            json.dumps(manifest, sort_keys=True, allow_nan=False),
                            json.dumps(report, sort_keys=True, allow_nan=False),
                        ),
                    )
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise HistoryValidationError("SQLite integrity check failed")
            # Hard link implements no-clobber even if another process created
            # the destination after preflight. Both files are on the same FS.
            if overwrite:
                os.replace(temporary, destination)
            else:
                os.link(temporary, destination)
                temporary.unlink()
            return report
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _legacy_views(connection):
        """Keep the existing single-race repository usable for compatible races."""
        connection.execute("""CREATE VIEW race_entries AS
            SELECT r.race_id, r.driver_id, r.team_id, r.grid_position, r.finish_position,
                   r.classification_order, r.laps_completed, r.elapsed_time_ms, s.description AS status
            FROM race_results r JOIN statuses s ON s.status_id = r.status_id""")
        terms = []
        for entity, table in (
            ("circuit", "circuits"),
            ("race", "races"),
            ("driver", "drivers"),
            ("team", "teams"),
        ):
            key = f"{entity}_id"
            terms.append(
                f"SELECT '{entity}' AS entity_type, (SELECT value FROM metadata WHERE key='source_name') AS source_name, substr({key}, instr({key}, ':')+1) AS external_id, {key} AS canonical_id FROM {table}"
            )
        connection.execute("CREATE VIEW source_ids AS " + " UNION ALL ".join(terms))

    @staticmethod
    def _lap_comparison(connection, session_id):
        """Report source disagreement; never overwrite Trotman race lap times."""
        row = connection.execute(
            """SELECT COUNT(*), SUM(CASE WHEN l.lap_time_ms != o.lap_time_ms THEN 1 ELSE 0 END),
                   MAX(ABS(l.lap_time_ms-o.lap_time_ms))
            FROM lap_observations o JOIN sessions s ON s.session_id=o.session_id
            JOIN laps l ON l.race_id=s.race_id AND l.driver_id=o.driver_id AND l.lap_number=o.lap_number
            WHERE s.kind='R' AND s.session_id=? AND o.lap_time_ms IS NOT NULL""",
            (session_id,),
        ).fetchone()
        return {
            "matched": row[0],
            "different": row[1] or 0,
            "maximum_absolute_difference_ms": row[2],
        }


def _connect(source: Path) -> sqlite3.Connection:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"history database not found: {source}")
    return sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)


class SQLiteHistoryRepository:
    """Read canonical facts and import reports with no SQL in the consumer."""

    def __init__(self, source: Path) -> None:
        self.source = source.resolve()

    def records(self, table: str, **filters: Scalar) -> Iterator[HistoricalRecord]:
        """Stream rows in primary-key order; filter names come from the schema."""
        from f1_simulator.domain.session_data import SESSION_SCHEMA

        schemas = {**HISTORY_SCHEMA, **SESSION_SCHEMA}
        if table not in schemas:
            raise ValueError(f"unknown canonical table: {table}")
        spec = schemas[table]
        if not set(filters) <= set(spec.names):
            raise ValueError(
                f"unknown filters for {table}: {set(filters) - set(spec.names)}"
            )
        where = " AND ".join(f'"{key}" IS ?' for key in filters) or "1=1"
        order = ",".join(f'"{key}"' for key in spec.key)
        with closing(_connect(self.source)) as connection:
            connection.row_factory = sqlite3.Row
            for row in connection.execute(
                f'SELECT * FROM "{table}" WHERE {where} ORDER BY {order}',
                tuple(filters.values()),
            ):
                values = dict(row)
                for column in spec.columns:
                    if column.kind == "bool" and values[column.name] is not None:
                        if values[column.name] not in (0, 1):
                            raise HistoryValidationError(
                                f"invalid stored boolean: {column.name}"
                            )
                        values[column.name] = bool(values[column.name])
                yield HistoryFactory.build(spec, values)

    def reports(self) -> list[dict[str, object]]:
        """Return the authoritative report for each imported source/session."""
        with closing(_connect(self.source)) as connection:
            return [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT report_json FROM imports ORDER BY import_key"
                )
            ]

    def get_race(self, race_id: str) -> RaceData:
        """Project a compatible race onto the already implemented RaceData port.

        Historical shared-car entries remain queryable as facts but cannot be
        silently collapsed into the current one-driver/one-entry race model.
        """
        from f1_simulator.adapters.persistence.sqlite_race_data_repository import (
            SQLiteRaceDataRepository,
        )

        with closing(_connect(self.source)) as connection:
            duplicate = connection.execute(
                "SELECT driver_id FROM race_results WHERE race_id=? GROUP BY driver_id HAVING COUNT(*)>1 LIMIT 1",
                (race_id,),
            ).fetchone()
            if duplicate:
                raise HistoryValidationError(
                    "multiple entries per driver: query race_results instead of projecting RaceData"
                )
            duplicate = connection.execute(
                "SELECT driver_id FROM laps WHERE race_id=? GROUP BY driver_id, lap_number HAVING COUNT(*)>1 LIMIT 1",
                (race_id,),
            ).fetchone()
            if duplicate:
                raise HistoryValidationError(
                    "multiple observations per lap: query laps and resolve conflicts before projecting RaceData"
                )
        return SQLiteRaceDataRepository(self.source).get_race(race_id)
