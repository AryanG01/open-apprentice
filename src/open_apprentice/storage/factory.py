"""The Store selected by environment: OA_STORE=gcs (bucket OA_BUCKET) or a local folder (OA_STORE_DIR, default .oa-store)."""

from __future__ import annotations

import os
import pathlib

from open_apprentice.storage.store import LocalStore, Store


def store_from_env() -> Store:
    if os.environ.get("OA_STORE") == "gcs":
        from google.cloud import storage

        from open_apprentice.storage.gcs import GcsStore

        return GcsStore(storage.Client().bucket(os.environ["OA_BUCKET"]))
    return LocalStore(pathlib.Path(os.environ.get("OA_STORE_DIR", ".oa-store")))
