"""Object store with the two primitives the event log needs: atomic create of immutable objects and compare-and-set
on a generation number (the GCS `ifGenerationMatch` semantics). `LocalStore` is the development backend; the GCS backend
(Plan 2) implements the same protocol."""

from __future__ import annotations

import fcntl
import os
import uuid
import pathlib
from dataclasses import dataclass
from typing import Optional, Protocol


class PreconditionFailed(Exception):
    """The object's current generation did not match the caller's expectation."""


@dataclass(frozen=True)
class Blob:
    data: bytes
    generation: int


class Store(Protocol):
    def get(self, key: str) -> Optional[Blob]: ...

    def create(self, key: str, data: bytes) -> bool: ...

    def put(self, key: str, data: bytes, if_generation: Optional[int]) -> int: ...


class LocalStore:
    """Files under `root`. A generation lives in `<file>.gen`; a per-key lock file serialises compare-and-set."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> pathlib.Path:
        if key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"bad key {key!r}")
        return self.root / key

    def get(self, key: str) -> Optional[Blob]:
        p = self._path(key)
        if not p.exists():
            return None
        gen_file = p.with_name(p.name + ".gen")
        gen = int(gen_file.read_text()) if gen_file.exists() else 1
        return Blob(p.read_bytes(), gen)

    def create(self, key: str, data: bytes) -> bool:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            return False
        # write a private temp file, then hard-link it into place: atomic, fails if the key exists, and readers never see
        # a created-but-unwritten file
        tmp = p.with_name(f"{p.name}.{uuid.uuid4().hex}.new")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(tmp, p)
            except FileExistsError:
                return False
            return True
        finally:
            tmp.unlink(missing_ok=True)

    def put(self, key: str, data: bytes, if_generation: Optional[int]) -> int:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        lock = p.with_name(p.name + ".lock")
        with open(lock, "a+") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            current = self.get(key)
            if (current is None) != (if_generation is None) or (
                current is not None and current.generation != if_generation
            ):
                raise PreconditionFailed(
                    f"{key}: expected {if_generation}, found {current and current.generation}"
                )
            new_gen = 1 if current is None else current.generation + 1
            gen_tmp = p.with_name(p.name + ".gen.tmp")
            gen_tmp.write_text(str(new_gen))
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, p)
            os.replace(
                gen_tmp, p.with_name(p.name + ".gen")
            )  # atomic: readers never see a partial value
            return new_gen
