from pathlib import Path

DATA_DIR = Path("/data/curated")
RACES_INDEX = DATA_DIR / "races-index.json"

RAW_SOURCE = Path("/data/raw/formula-1-race-data-v128.zip")

CURRENT_RACE_DB = DATA_DIR / "current-race.sqlite"
CURRENT_RACE_REPORT = DATA_DIR / "current-race-quality.json"

DEFAULT_RACE_DB = CURRENT_RACE_DB

# Banco do ETL B (historico completo dos 14 CSVs do Trotman v128, ADR 0005).
# Diferente do agregado executavel de corrida unica (DEFAULT_RACE_DB): guarda
# todas as corridas e preserva casos ambiguos (carro compartilhado). O relatorio
# de qualidade fica embutido no proprio SQLite, entao nao ha arquivo separado.
HISTORY_DB = DATA_DIR / "history.sqlite"
