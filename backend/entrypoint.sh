#!/bin/sh
set -e

SCRIPTS="${F1_SCRIPTS_DIR:-/opt/f1/scripts}"
RAW=/data/raw/formula-1-race-data-v128.zip
INDEX=/data/curated/races-index.json

if [ ! -f "$RAW" ]; then
    echo "[bootstrap] baixando dataset bruto do Trotman..."
    python "$SCRIPTS/download_trotman.py" --destination "$RAW" || \
        echo "[bootstrap] aviso: download falhou; catalogo pode ficar vazio."
fi

if [ ! -f "$INDEX" ]; then
    echo "[bootstrap] gerando catalogo de corridas..."
    python "$SCRIPTS/list_races.py" --source "$RAW" --output "$INDEX" || \
        echo "[bootstrap] aviso: catalogo nao gerado."
fi

exec "$@"
