from __future__ import annotations

import json
import urllib.request

BASE_URL = "http://localhost:8000"


def fetch_track(circuit_id: int | str, base_url: str = BASE_URL) -> dict:
    url = f"{base_url}/simulation/track/{circuit_id}"
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())
