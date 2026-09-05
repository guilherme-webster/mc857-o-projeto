from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.engine.simulation import run_batch_simulation
from app.config import DEFAULT_RACE_DB

app = FastAPI(
    title="F1 Simulation Engine API",
    version="1.0.0"
)

# Libera CORS para o frontend local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Armazenamento em memória para as simulações prontas (ou pode salvar em arquivo)
SIMULATIONS_CACHE = {}


@app.get("/")
def health_check():
    return {
        "status": "online",
        "etl_db_found": DEFAULT_RACE_DB.exists()
    }


@app.post("/api/simulations/{race_id}/run")
def trigger_simulation(race_id: int, laps: int = 10):
    """Calcula a corrida inteira e armazena o resultado."""
    result = run_batch_simulation(race_id=race_id, total_laps=laps)
    SIMULATIONS_CACHE[race_id] = result
    return {
        "status": "completed",
        "race_id": race_id,
        "message": "Simulação pronta para consumo pelo frontend."
    }


@app.get("/api/simulations/{race_id}")
def get_simulation_data(race_id: int):
    """O Frontend consome esse endpoint para obter o 'replay' da corrida."""
    if race_id not in SIMULATIONS_CACHE:
        raise HTTPException(
            status_code=404, detail="Simulação não encontrada. Execute o POST primeiro.")
    return SIMULATIONS_CACHE[race_id]
