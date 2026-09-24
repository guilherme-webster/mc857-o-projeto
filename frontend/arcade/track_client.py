from __future__ import annotations

import json
import urllib.request

BASE_URL = "http://localhost:8000"

# Build urllib's handlers on the Arcade/UI thread. Lazily constructing the
# default opener inside a worker also initializes an unused HTTPS context and
# fails with ``ssl.SSLError`` on the Fedora/Pyglet combination used by the
# project, even though this client talks to the local backend over plain HTTP.
_OPENER = urllib.request.build_opener()


def _get(path: str, base_url: str) -> dict:
    with _OPENER.open(f"{base_url}{path}", timeout=10) as response:
        return json.loads(response.read())


def fetch_track(circuit_id: int | str, base_url: str = BASE_URL) -> dict:
    return _get(f"/simulation/track/{circuit_id}", base_url)


def fetch_tracks(base_url: str = BASE_URL) -> dict:
    """Return the backend catalog of circuits with available geometry."""

    return _get("/simulation/tracks", base_url)


def fetch_race(base_url: str = BASE_URL) -> dict:
    return _get("/simulation/race", base_url)
