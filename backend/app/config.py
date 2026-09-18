from pathlib import Path

DATA_DIR = Path("/data/curated")
RACES_INDEX = DATA_DIR / "races-index.json"

RAW_SOURCE = Path("/data/raw/formula-1-race-data-v128.zip")

CURRENT_RACE_DB = DATA_DIR / "current-race.sqlite"
CURRENT_RACE_REPORT = DATA_DIR / "current-race-quality.json"

DEFAULT_RACE_DB = CURRENT_RACE_DB

HISTORY_DB = DATA_DIR / "history.sqlite"

RACE_JSON = Path(__file__).resolve().parent.parent / "races" / "race.json"
