from pathlib import Path

DATA_DIR = Path("/data/curated")
SIMULATION_DIR = Path("/data/simulation")

RAW_SOURCE = Path("/data/raw/formula-1-race-data-v128.zip")

CURRENT_RACE_DB = DATA_DIR / "current-race.sqlite"
CURRENT_RACE_JSON = SIMULATION_DIR / "current-race.json"
CURRENT_GRID_JSON = SIMULATION_DIR / "current-grid.json"
SAVED_RACES_DIR = SIMULATION_DIR / "saved-races"

DEFAULT_RACE_DB = CURRENT_RACE_DB

HISTORY_DB = DATA_DIR / "history.sqlite"

GEOMETRY_DIR = DATA_DIR.parent / "geometry"
GEOMETRY_TRACK_POINTS = GEOMETRY_DIR / "track_points.csv"
GEOMETRY_PIT_LANE_POINTS = GEOMETRY_DIR / "pit_lane_points.csv"
GEOMETRY_TRACK_MANIFEST = DATA_DIR.parent / "sources" / "fastf1-tracks-2025.json"
GEOMETRY_PIT_MANIFEST = DATA_DIR.parent / "sources" / "fastf1-pit-lanes-2025.json"

# Parametros calibrados do modelo de tempo de volta.
#
# No container, ./data e montado em /data, entao o arquivo versionado do
# repositorio aparece em /data/parameters. Fora do container esse caminho nao
# existe, e a busca cai no diretorio do proprio repositorio -- o que permite
# rodar o backend localmente sem duplicar o arquivo nem editar a configuracao.
_CONTAINER_PARAMETERS = DATA_DIR.parent / "parameters" / "model-v1.json"
_REPOSITORY_PARAMETERS = (
    Path(__file__).resolve().parents[2] / "data" / "parameters" / "model-v1.json"
)
MODEL_PARAMETERS = (
    _CONTAINER_PARAMETERS if _CONTAINER_PARAMETERS.exists() else _REPOSITORY_PARAMETERS
)

# Volta de referencia por circuito (mediana historica), gerada por
# scripts/build_reference_laps.py. Mesma regra de busca do MODEL_PARAMETERS.
_CONTAINER_REFERENCE_LAPS = DATA_DIR.parent / "parameters" / "reference-laps-v1.json"
_REPOSITORY_REFERENCE_LAPS = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "parameters"
    / "reference-laps-v1.json"
)
REFERENCE_LAPS = (
    _CONTAINER_REFERENCE_LAPS
    if _CONTAINER_REFERENCE_LAPS.exists()
    else _REPOSITORY_REFERENCE_LAPS
)
