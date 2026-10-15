"""Google Cloud Storage backend for the Store contract. Immutable create = upload with if_generation_match=0;
compare-and-set = upload with if_generation_match=<expected generation>. Generations are GCS object generations.
Real-bucket behaviour is verified only in the staging integration, after the owner approves staging resources."""

from __future__ import annotations

from typing import Any, Optional

from google.api_core.exceptions import NotFound
from google.api_core.exceptions import PreconditionFailed as GcsPreconditionFailed

from open_apprentice.storage.store import Blob, PreconditionFailed


class GcsStore:
    def __init__(self, bucket: Any, prefix: str = "") -> None:
        self.bucket, self.prefix = bucket, prefix

    def _blob(self, key: str) -> Any:
        if key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"bad key {key!r}")
        return self.bucket.blob(self.prefix + key)

    def get(self, key: str) -> Optional[Blob]:
        b = self._blob(key)
        try:
            data = b.download_as_bytes()
        except NotFound:
            return None
        return Blob(data, int(b.generation))

    def _landed(self, key: str, data: bytes) -> Optional[int]:
        """After a precondition failure: the client retries a conditional upload whose response was lost, and the retry
        then fails against our own write. If the object holds exactly our bytes, that write landed; callers write
        unique content (record ids, claim nonces) where telling writers apart matters."""
        cur = self.get(key)
        return cur.generation if cur is not None and cur.data == data else None

    def create(self, key: str, data: bytes) -> bool:
        try:
            self._blob(key).upload_from_string(data, if_generation_match=0)
        except GcsPreconditionFailed:
            return self._landed(key, data) is not None
        return True

    def put(self, key: str, data: bytes, if_generation: Optional[int]) -> int:
        b = self._blob(key)
        try:
            b.upload_from_string(
                data, if_generation_match=0 if if_generation is None else if_generation
            )
        except GcsPreconditionFailed as e:
            landed = self._landed(key, data)
            if landed is not None:
                return landed
            raise PreconditionFailed(f"{key}: generation precondition failed") from e
        return int(b.generation)
