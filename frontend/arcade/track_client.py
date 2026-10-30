from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE_URL = os.environ.get("F1_API_BASE_URL", "http://localhost:8000").rstrip("/")

# Build urllib's handlers on the Arcade/UI thread. Lazily constructing the
# default opener inside a worker also initializes an unused HTTPS context and
# fails with ``ssl.SSLError`` on the Fedora/Pyglet combination used by the
# project, even though this client talks to the local backend over plain HTTP.
_OPENER = urllib.request.build_opener()


# Rodar o grid no motor detalhado leva alguns segundos numa corrida longa;
# as consultas de catalogo continuam com o limite curto.
RUN_TIMEOUT_S = 120


class BackendError(RuntimeError):
    """Resposta de erro do backend, com o ``detail`` do FastAPI quando houver."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{detail} (HTTP {status})")
        self.status = status
        self.detail = detail


def _get(path: str, base_url: str) -> dict:
    with _OPENER.open(f"{base_url}{path}", timeout=10) as response:
        return json.loads(response.read())


def _post(
    path: str,
    payload: dict,
    base_url: str,
    timeout: float = 10,
    method: str = "POST",
) -> dict:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise BackendError(error.code, _error_detail(error)) from error


def _error_detail(error: urllib.error.HTTPError) -> str:
    """Extraia o ``detail`` do corpo de erro, que pode ser texto ou lista."""

    try:
        detail = json.loads(error.read()).get("detail")
    except (ValueError, AttributeError):
        return error.reason or "erro no backend"
    finally:
        error.close()
    if isinstance(detail, list):
        # Erros de validacao do Pydantic: uma entrada por campo.
        return "; ".join(str(item.get("msg", item)) for item in detail)
    return str(detail) if detail else (error.reason or "erro no backend")


def fetch_track(circuit_id: int | str, base_url: str = BASE_URL) -> dict:
    return _get(f"/simulation/track/{circuit_id}", base_url)


def fetch_tracks(base_url: str = BASE_URL) -> dict:
    """Return the backend catalog of circuits with available geometry."""

    return _get("/simulation/tracks", base_url)


def fetch_race(base_url: str = BASE_URL) -> dict:
    return _get("/simulation/race", base_url)


def fetch_saved_races(base_url: str = BASE_URL) -> dict:
    return _get("/simulation/saved", base_url)


def fetch_saved_race(race_id: str, base_url: str = BASE_URL) -> dict:
    return _get(f"/simulation/saved/{race_id}", base_url)


def fetch_current_grid(base_url: str = BASE_URL) -> dict | None:
    """Grid atual do backend, ou ``None`` se nenhum foi montado ainda."""

    try:
        return _get("/catalog/grid", base_url)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise BackendError(error.code, _error_detail(error)) from error


def build_grid(
    size: int | None = None,
    mode: str = "random",
    seed: int | None = None,
    race_id: str | None = None,
    base_url: str = BASE_URL,
) -> dict:
    """Monte um grid novo no backend (``POST /catalog/grid``).

    ``mode="race"`` usa a largada de ``race_id``; ai o tamanho vem da corrida.
    """

    payload: dict = {"mode": mode}
    if size is not None:
        payload["size"] = size
    if race_id is not None:
        payload["race_id"] = race_id
    if seed is not None:
        payload["seed"] = seed
    return _post("/catalog/grid", payload, base_url)


def edit_grid(
    overrides: list[dict] | None = None,
    base_url: str = BASE_URL,
    *,
    order: list[str] | None = None,
) -> dict:
    """Edite atributos e/ou a ordem do grid atual em um unico ``PATCH``."""

    payload = {}
    if overrides is not None:
        payload["overrides"] = overrides
    if order is not None:
        payload["order"] = order
    return _post("/catalog/grid", payload, base_url, method="PATCH")


def fetch_history_races(season: int, base_url: str = BASE_URL) -> dict:
    """Corridas historicas de uma temporada, para montar grids de largada."""

    try:
        return _get(f"/api/history/races?season={int(season)}", base_url)
    except urllib.error.HTTPError as error:
        raise BackendError(error.code, _error_detail(error)) from error


def run_grid(setup: dict, base_url: str = BASE_URL) -> dict:
    """Rode o grid atual com ``setup`` e devolva a corrida salva pelo backend."""

    return _post("/catalog/grid/run", {"setup": setup}, base_url, RUN_TIMEOUT_S)


def fetch_championship_standings(request: dict, base_url: str = BASE_URL) -> dict:
    """Tabela do campeonato calculada pelo backend para as etapas enviadas."""

    return _post("/championship/standings", request, base_url)


def save_tournament(payload: dict, base_url: str = BASE_URL) -> dict:
    """Salve um torneio ja simulado (``POST /tournaments``); devolve o resumo."""

    return _post("/tournaments", payload, base_url)


def fetch_saved_tournaments(base_url: str = BASE_URL) -> dict:
    """Resumo dos torneios salvos, do mais recente ao mais antigo."""

    try:
        return _get("/tournaments", base_url)
    except urllib.error.HTTPError as error:
        raise BackendError(error.code, _error_detail(error)) from error


def fetch_saved_tournament(tournament_id: str, base_url: str = BASE_URL) -> dict:
    """Registro completo de um torneio salvo, com as corridas de cada etapa."""

    try:
        return _get(f"/tournaments/{tournament_id}", base_url)
    except urllib.error.HTTPError as error:
        raise BackendError(error.code, _error_detail(error)) from error


def restore_tournament_grid(tournament_id: str, base_url: str = BASE_URL) -> dict:
    """Torne o grid congelado do torneio o grid atual, antes de reexecuta-lo."""

    return _post(f"/tournaments/{tournament_id}/restore-grid", {}, base_url)
