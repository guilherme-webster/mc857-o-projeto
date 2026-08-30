from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path


class AcquisitionError(RuntimeError):
    """Raised when a dataset cannot be downloaded or verified."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(
    url: str,
    destination: Path,
    expected_sha256: str,
    *,
    overwrite: bool = False,
) -> bool:
    """Download atomically and verify its checksum.

    Returns True after a download and False when an existing verified file was
    reused.
    """

    destination = destination.resolve()
    if destination.exists() and not overwrite:
        current = sha256_file(destination)
        if current == expected_sha256:
            return False
        raise AcquisitionError(
            f"destination exists with unexpected checksum: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "f1-simulator-etl/1"})
    try:
        with (
            urllib.request.urlopen(request) as response,
            temporary.open("wb") as target,
        ):
            while chunk := response.read(1024 * 1024):
                target.write(chunk)
        actual_sha256 = sha256_file(temporary)
        if actual_sha256 != expected_sha256:
            raise AcquisitionError(
                "download checksum mismatch: "
                f"expected {expected_sha256}, received {actual_sha256}"
            )
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return True
