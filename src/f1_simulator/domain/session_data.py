"""Canonical session observations supplementing the historical race catalog.

Raw sample clocks remain separate: we do not interpolate car and position
channels, infer rainfall intensity, or turn marker coordinates into a physical
track model. Nullable fields mean unknown, even for quality flags. Sequence
keys preserve simultaneous messages/samples without silently deduplicating.
"""

from f1_simulator.domain.history import Column, Table


def _text(name, required=False):
    return Column(name, "text", not required)


def _number(name, kind="float", minimum=None, maximum=None):
    return Column(name, kind, True, minimum, maximum)


_SESSION = Column("session_id", nullable=False)
_DRIVER = Column("driver_id", nullable=False)
_SEQ = Column("sequence", "int", False, 0)
_SESSION_REF = ("session_id", "sessions", "session_id")
_DRIVER_REF = ("driver_id", "drivers", "driver_id")
_CLOCK = Column("session_time_ms", "int")
_DATE = Column("date_utc", "datetime")

SESSION_TABLES = (
    Table(
        "sessions",
        (
            _SESSION,
            _text("race_id", True),
            _text("kind", True),
            _text("name", True),
            _text("event_format"),
            _DATE,
            Column("zero_time_utc", "datetime"),
            _number("start_time_ms", "int"),
            _number("circuit_rotation_deg"),
        ),
        ("session_id",),
        (("race_id", "races", "race_id"),),
    ),
    Table(
        "session_drivers",
        (
            _SESSION,
            _DRIVER,
            Column("driver_number", "int", False, 0),
            _text("external_driver_ref"),
            _text("external_team_ref"),
            _text("team_name"),
            _text("abbreviation"),
            _text("team_color"),
            _text("headshot_url"),
            _text("country_code"),
            _number("position", "int", 0),
            _text("classified_position"),
            _number("grid_position", "int", 0),
            _number("points"),
            _text("status"),
            _number("laps_completed", "int", 0),
            _number("result_time_ms", "int"),
            *(_number(f"q{i}_ms", "int", 0) for i in (1, 2, 3)),
        ),
        ("session_id", "driver_id"),
        (_SESSION_REF, _DRIVER_REF),
    ),
    Table(
        "lap_observations",
        (
            _SESSION,
            _DRIVER,
            Column("lap_number", "int", False, 1),
            _number("lap_time_ms", "int", 0),
            _CLOCK,
            _number("lap_start_ms", "int"),
            Column("lap_start_date_utc", "datetime"),
            _number("stint", "int", 0),
            _number("pit_in_ms", "int"),
            _number("pit_out_ms", "int"),
            *(_number(f"sector{i}_ms", "int", 0) for i in (1, 2, 3)),
            *(_number(f"sector{i}_session_ms", "int") for i in (1, 2, 3)),
            *(
                _number(f"speed_{trap}_kmh", minimum=0)
                for trap in ("i1", "i2", "fl", "st")
            ),
            _text("compound"),
            _number("tyre_life_laps", minimum=0),
            Column("fresh_tyre", "bool"),
            Column("personal_best", "bool"),
            _text("track_status"),
            _number("position", "int", 0),
            Column("deleted", "bool"),
            _text("deleted_reason"),
            Column("generated", "bool"),
            Column("accurate", "bool"),
        ),
        ("session_id", "driver_id", "lap_number"),
        (_SESSION_REF, _DRIVER_REF),
    ),
    Table(
        "weather_observations",
        (
            _SESSION,
            _SEQ,
            _CLOCK,
            _number("air_temperature_c"),
            _number("track_temperature_c"),
            _number("humidity_pct", minimum=0, maximum=100),
            _number("pressure_mbar", minimum=0),
            Column("rainfall", "bool"),
            _number("wind_direction_deg", minimum=0, maximum=360),
            _number("wind_speed_ms", minimum=0),
        ),
        ("session_id", "sequence"),
        (_SESSION_REF,),
    ),
    Table(
        "track_status_events",
        (
            _SESSION,
            _SEQ,
            _CLOCK,
            _text("status"),
            _text("message"),
        ),
        ("session_id", "sequence"),
        (_SESSION_REF,),
    ),
    Table(
        "session_status_events",
        (
            _SESSION,
            _SEQ,
            _CLOCK,
            _text("status"),
        ),
        ("session_id", "sequence"),
        (_SESSION_REF,),
    ),
    Table(
        "race_control_messages",
        (
            _SESSION,
            _SEQ,
            _DATE,
            _text("category"),
            _text("message"),
            _text("status"),
            _text("flag"),
            _text("scope"),
            _number("sector", "int", 0),
            _number("driver_number", "int", 0),
            _number("lap_number", "int", 0),
        ),
        ("session_id", "sequence"),
        (_SESSION_REF,),
    ),
    Table(
        "car_samples",
        (
            _SESSION,
            _DRIVER,
            _SEQ,
            _CLOCK,
            _DATE,
            _number("speed_kmh", minimum=0),
            _number("rpm", "int", 0),
            _number("gear", "int", 0),
            _number("throttle_pct", minimum=0, maximum=100),
            _number("throttle_raw_pct"),
            Column("brake", "bool"),
            _number("drs_code", "int", 0),
            _text("sample_source"),
        ),
        ("session_id", "driver_id", "sequence"),
        (_SESSION_REF, _DRIVER_REF),
    ),
    Table(
        "position_samples",
        (
            _SESSION,
            _DRIVER,
            _SEQ,
            _CLOCK,
            _DATE,
            _number("x_m"),
            _number("y_m"),
            _number("z_m"),
            _text("status"),
            _text("sample_source"),
        ),
        ("session_id", "driver_id", "sequence"),
        (_SESSION_REF, _DRIVER_REF),
    ),
    Table(
        "circuit_markers",
        (
            _SESSION,
            _SEQ,
            _text("kind", True),
            _number("number", "int", 0),
            _text("letter"),
            _number("map_x"),
            _number("map_y"),
            _number("label_angle_deg"),
            _number("estimated_distance_m", minimum=0),
        ),
        ("session_id", "sequence"),
        (_SESSION_REF,),
    ),
)

SESSION_SCHEMA = {table.name: table for table in SESSION_TABLES}
