"""Small real CSV fixture and explicitly synthetic session data for ETL tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from f1_simulator.adapters.datasets.trotman_history import TrotmanHistoryAdapter
from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryWriter
from f1_simulator.application.history_etl import run_history_etl

FIXTURE = Path(__file__).parent / "fixtures" / "trotman_v128_history"
RACE = {"race_id": "race:1141", "season": 2024, "round_number": 21}
DRIVERS = {"max_verstappen": "driver:830", "ocon": "driver:839"}
NOW = datetime(2024, 11, 3, 15, 0, tzinfo=timezone.utc)


def make_history(destination):
    return run_history_etl(
        TrotmanHistoryAdapter(FIXTURE), SQLiteHistoryWriter(), destination
    )


def synthetic_session(kind="R"):
    """Controlled numbers exercise contracts; they are not measured lap data."""
    return SimpleNamespace(
        name="Race" if kind == "R" else "Qualifying",
        date=NOW,
        event={"RoundNumber": 21, "EventFormat": "sprint_qualifying"},
        api_path="synthetic-test-session",
        t0_date=NOW,
        session_start_time=timedelta(seconds=10),
        results=[
            {
                "DriverNumber": "1",
                "DriverId": "max_verstappen",
                "Position": 1.0,
                "GridPosition": 0.0,
                "Points": 0.0,
            }
        ],
        laps=[
            {
                "DriverNumber": "1",
                "LapNumber": 1.0,
                "LapTime": timedelta(seconds=90),
                "Time": timedelta(seconds=100),
                "LapStartTime": timedelta(seconds=10),
                "LapStartDate": NOW,
                "Sector1Time": timedelta(seconds=30),
                "Sector2Time": timedelta(seconds=30),
                "Sector3Time": timedelta(seconds=30),
                "Stint": 1.0,
                "TyreLife": 2.0,
                "Compound": "INTERMEDIATE",
                "FreshTyre": False,
                "Deleted": None,
                "IsAccurate": True,
                "FastF1Generated": False,
            }
        ],
        weather_data=[
            {
                "Time": timedelta(seconds=5),
                "Rainfall": False,
                "WindSpeed": 0.0,
                "AirTemp": 20.0,
                "Humidity": 60.0,
            }
        ],
        track_status=[
            {"Time": timedelta(seconds=1), "Status": "1", "Message": "AllClear"}
        ],
        session_status=[{"Time": timedelta(seconds=10), "Status": "Started"}],
        race_control_messages=[
            {
                "Time": NOW,
                "Category": "Flag",
                "Message": "GREEN LIGHT",
                "Flag": "GREEN",
            },
            {
                "Time": NOW,
                "Category": "Other",
                "Message": "SECOND MESSAGE AT SAME TIME",
            },
        ],
        car_data={
            "1": [
                {
                    "Time": timedelta(seconds=12),
                    "Date": NOW,
                    "Speed": 120,
                    "Throttle": 104,
                    "Brake": False,
                    "Source": "car",
                }
            ]
        },
        pos_data={
            "1": [
                {
                    "Time": timedelta(seconds=12, milliseconds=50),
                    "Date": NOW,
                    "X": 123,
                    "Y": -45,
                    "Z": 0,
                    "Source": "pos",
                    "Status": "OnTrack",
                }
            ]
        },
        get_circuit_info=lambda: SimpleNamespace(
            rotation=90.0,
            corners=[
                {
                    "X": 100.0,
                    "Y": -200.0,
                    "Number": 1,
                    "Letter": "",
                    "Angle": 45.0,
                    "Distance": 300.0,
                }
            ],
            marshal_lights=[],
            marshal_sectors=[],
        ),
    )
