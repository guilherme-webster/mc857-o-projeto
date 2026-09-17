from __future__ import annotations

from app.routers import etl, health, history, simulation
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="F1 Simulation Engine API",
    version="1.0.0",
)

# Libera CORS para o frontend local.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(etl.router)
app.include_router(history.router)
app.include_router(simulation.router)
