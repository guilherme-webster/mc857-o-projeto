from __future__ import annotations

import json
import urllib.request

BASE_URL = "http://localhost:8000"


def _get(path: str, base_url: str) -> dict:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as response:
        return json.loads(response.read())


def fetch_track(circuit_id: int | str, base_url: str = BASE_URL) -> dict:
    return _get(f"/simulation/track/{circuit_id}", base_url)


def fetch_race(base_url: str = BASE_URL) -> dict:
    return _get("/simulation/race", base_url)
