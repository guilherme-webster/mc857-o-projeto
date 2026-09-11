import sqlite3
from pathlib import Path


def run_batch_simulation(race_id: int, total_laps: int = 5) -> dict:
    """
    Executa a simulação completa em batch e retorna os dados prontos para exibição.
    """
    db_path = Path(f"/app/data/curated/race-{race_id}.sqlite")

    # 1. Carrega pilotos do banco do ETL
    drivers = []
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, family_name FROM drivers LIMIT 5;")
        for row in cursor.fetchall():
            drivers.append({"id": row[0], "name": row[1]})
        conn.close()
    else:
        drivers = [{"id": "driver:1", "name": "Dummy Driver"}]

    # 2. Loop de física simplificado (exemplo de avanço)
    snapshots = []
    for lap in range(1, total_laps + 1):
        lap_state = {
            "lap": lap,
            "cars": []
        }
        for idx, driver in enumerate(drivers):
            # Aqui entrarão suas fórmulas de física/desgaste
            lap_state["cars"].append({
                "driver_id": driver["id"],
                "name": driver["name"],
                # Pneu desgastando
                "lap_time_s": 75.2 + idx * 0.4 + (lap * 0.08),
                "tire_wear": round(lap * 0.05, 2)
            })
        snapshots.append(lap_state)

    return {
        "race_id": race_id,
        "total_laps": total_laps,
        "history": snapshots
    }
