import sqlite3
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from app.config import DEFAULT_RACE_DB

app = FastAPI(
    title="F1 Simulation Engine API",
    version="1.0.0",
)

# Libera CORS para o frontend local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_connection():
    """Gera uma conexão SQLite somente leitura com suporte a dicionários."""
    if not DEFAULT_RACE_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Arquivo {DEFAULT_RACE_DB} não encontrado no volume."
        )
    conn = sqlite3.connect(f"file:{DEFAULT_RACE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def validate_table_exists(conn: sqlite3.Connection, table_name: str) -> None:
    """Verifica se a tabela solicitada existe no banco para evitar erros de SQL."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,)
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tabela '{table_name}' não existe no banco de dados."
        )


@app.get("/", tags=["Health"])
def health_check():
    """Health check do backend e verificação do arquivo de banco curado."""
    return {
        "status": "online",
        "etl_db_found": DEFAULT_RACE_DB.exists()
    }


@app.get("/api/etl/tables", tags=["ETL Inspector"])
def list_tables():
    """Lista todas as tabelas criadas pelo ETL no banco SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()
    return {"tables": tables, "count": len(tables)}


@app.get("/api/etl/schema/{table_name}", tags=["ETL Inspector"])
def get_table_schema(table_name: str):
    """Mostra as colunas e tipos de dados de uma tabela específica."""
    conn = get_db_connection()
    validate_table_exists(conn, table_name)
    cursor = conn.cursor()
    cursor.execute(f'PRAGMA table_info("{table_name}");')
    columns = [
        {
            "column_id": row[0],
            "name": row[1],
            "type": row[2],
            "notnull": bool(row[3])
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return {"table": table_name, "columns": columns}


@app.get("/api/etl/preview/{table_name}", tags=["ETL Inspector"])
def preview_table_data(
    table_name: str,
    limit: int = Query(default=10, ge=1, le=1000,
                       description="Quantidade de linhas a retornar")
):
    """Mostra as primeiras N linhas de qualquer tabela do ETL."""
    conn = get_db_connection()
    validate_table_exists(conn, table_name)
    cursor = conn.cursor()
    cursor.execute(f'SELECT * FROM "{table_name}" LIMIT ?', (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"table": table_name, "count": len(rows), "data": rows}


@app.get("/api/etl/table/{table_name}", tags=["ETL Inspector"])
def get_full_table(table_name: str):
    """Retorna todos os registros de uma tabela sem corte de paginação."""
    conn = get_db_connection()
    validate_table_exists(conn, table_name)
    cursor = conn.cursor()
    cursor.execute(f'SELECT * FROM "{table_name}"')
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"table": table_name, "total_rows": len(rows), "data": rows}


@app.get("/api/etl/database/dump", tags=["ETL Inspector"])
def dump_entire_database():
    """Retorna o banco inteiro: todas as tabelas com todos os seus registros."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    tables = [row["name"] for row in cursor.fetchall()]

    full_database = {}
    for table in tables:
        cursor.execute(f'SELECT * FROM "{table}"')
        full_database[table] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return {
        "database": DEFAULT_RACE_DB.name,
        "tables_count": len(tables),
        "data": full_database
    }
