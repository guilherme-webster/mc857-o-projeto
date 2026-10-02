from pathlib import Path

DATA_DIR = Path("/data/curated")

RAW_SOURCE = Path("/data/raw/formula-1-race-data-v128.zip")

CURRENT_RACE_DB = DATA_DIR / "current-race.sqlite"
CURRENT_RACE_JSON = DATA_DIR / "current-race.json"
CURRENT_GRID_JSON = DATA_DIR / "current-grid.json"

DEFAULT_RACE_DB = CURRENT_RACE_DB

HISTORY_DB = DATA_DIR / "history.sqlite"

GEOMETRY_DIR = DATA_DIR.parent / "geometry"
GEOMETRY_TRACK_POINTS = GEOMETRY_DIR / "track_points.csv"
GEOMETRY_PIT_LANE_POINTS = GEOMETRY_DIR / "pit_lane_points.csv"
GEOMETRY_TRACK_MANIFEST = DATA_DIR.parent / "sources" / "fastf1-tracks-2025.json"
GEOMETRY_PIT_MANIFEST = DATA_DIR.parent / "sources" / "fastf1-pit-lanes-2025.json"
