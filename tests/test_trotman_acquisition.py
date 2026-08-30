from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from f1_simulator.adapters.datasets.acquisition import (
    AcquisitionError,
    download_verified,
)
from f1_simulator.adapters.datasets.trotman_source import (
    TROTMAN_ARCHIVE_SHA256,
    TROTMAN_DATASET_REF,
    TROTMAN_DATASET_VERSION,
    TROTMAN_DOWNLOAD_URL,
)


ROOT = Path(__file__).resolve().parents[1]


class DatasetAcquisitionTest(unittest.TestCase):
    def test_downloads_atomically_and_reuses_verified_file(self) -> None:
        content = b"small deterministic dataset"
        expected_sha256 = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "source.zip"
            destination = temporary / "raw" / "dataset.zip"
            source.write_bytes(content)

            self.assertTrue(
                download_verified(source.as_uri(), destination, expected_sha256)
            )
            self.assertEqual(destination.read_bytes(), content)
            self.assertFalse(
                download_verified(source.as_uri(), destination, expected_sha256)
            )

    def test_rejects_existing_file_with_unexpected_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "dataset.zip"
            destination.write_bytes(b"unexpected")
            with self.assertRaisesRegex(AcquisitionError, "unexpected checksum"):
                download_verified(
                    "https://example.invalid/dataset.zip",
                    destination,
                    hashlib.sha256(b"expected").hexdigest(),
                )

    def test_source_manifest_matches_download_constants(self) -> None:
        manifest = json.loads(
            (ROOT / "data" / "sources" / "trotman-v128.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["dataset_ref"], TROTMAN_DATASET_REF)
        self.assertEqual(manifest["version"], TROTMAN_DATASET_VERSION)
        self.assertEqual(manifest["download_url"], TROTMAN_DOWNLOAD_URL)
        self.assertEqual(manifest["archive_sha256"], TROTMAN_ARCHIVE_SHA256)


if __name__ == "__main__":
    unittest.main()
