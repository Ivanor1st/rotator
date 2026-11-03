from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


from constants import Provider, ProviderKeyValidation


FileSignature = tuple[int, int]
FileMetadataSignature = tuple[int, int, int, int, int]
_MAX_READ_ATTEMPTS = 3


def _file_identity(_path: Path, stat: os.stat_result) -> tuple[int, int, int]:
    return stat.st_ctime_ns, stat.st_dev, stat.st_ino


class GoogleKeyFileError(ValueError):
    pass


@dataclass(frozen=True)
class _FileMetadata:
    signature: FileSignature
    full_signature: FileMetadataSignature


@dataclass(frozen=True)
class _FileSnapshot:
    metadata: _FileMetadata
    content_digest: str


@dataclass(frozen=True)
class GoogleKeyRecord:
    key_id: str
    value: str = field(repr=False)
    label: str
    provider: str
    source: str


class GoogleKeyLoader:
    def __init__(
        self,
        path: str | Path,
        validator: Callable[[str], bool] | None = None,
    ) -> None:
        self._path = Path(path)
        self._validator = validator or ProviderKeyValidation.google
        self._records: tuple[GoogleKeyRecord, ...] | None = None
        self._snapshot: _FileSnapshot | None = None
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def signature(self) -> FileSignature | None:
        with self._lock:
            if self._snapshot is None:
                return None
            return self._snapshot.metadata.signature

    @property
    def records(self) -> tuple[GoogleKeyRecord, ...] | None:
        with self._lock:
            return self._records

    def load(self) -> tuple[GoogleKeyRecord, ...]:
        with self._lock:
            return self._load_locked()

    def _load_locked(self) -> tuple[GoogleKeyRecord, ...]:
        for _ in range(_MAX_READ_ATTEMPTS):
            try:
                with self._path.open("rb") as stream:
                    before = self._capture_stream_metadata(stream)
                    content_bytes = stream.read()
                    after = self._capture_stream_metadata(stream)
                    current = self._capture_path_metadata()
            except OSError as exc:
                raise GoogleKeyFileError("Unable to read Google keys file safely") from exc

            if current is None:
                continue
            if before.full_signature != after.full_signature:
                continue
            if after.signature != current.signature:
                continue

            normalized = content_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            digest = hashlib.sha256(normalized).hexdigest()
            snapshot = _FileSnapshot(after, digest)
            if (
                self._records is not None
                and self._snapshot is not None
                and digest == self._snapshot.content_digest
            ):
                self._snapshot = snapshot
                return self._records

            records = self._parse(content_bytes.decode("utf-8"))
            self._records = records
            self._snapshot = snapshot
            return records

        raise GoogleKeyFileError("Google keys file changed while it was being read")

    def reload_if_changed(self) -> tuple[GoogleKeyRecord, ...]:
        return self.load()

    def _capture_stream_metadata(self, stream) -> _FileMetadata:
        import os
        stat = os.fstat(stream.fileno())
        identity = _file_identity(self._path, stat)
        signature = stat.st_mtime_ns, stat.st_size
        full_signature = signature[0], signature[1], *identity
        return _FileMetadata(signature, full_signature)

    def _capture_path_metadata(self) -> _FileMetadata | None:
        try:
            stat = self._path.stat()
            identity = _file_identity(self._path, stat)
        except OSError:
            return None
        signature = stat.st_mtime_ns, stat.st_size
        full_signature = signature[0], signature[1], *identity
        return _FileMetadata(signature, full_signature)

    def _parse(self, content: str) -> tuple[GoogleKeyRecord, ...]:
        records: list[GoogleKeyRecord] = []
        seen: set[str] = set()

        for line_number, raw_line in enumerate(content.splitlines(), start=1):
            value = raw_line.strip()
            if not value or value.startswith("#"):
                continue

            try:
                valid = self._validator(value)
            except Exception:
                valid = False

            if not valid:
                raise GoogleKeyFileError(
                    f"Invalid Google API key format at line {line_number}"
                )

            fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()
            if fingerprint in seen:
                continue

            seen.add(fingerprint)
            short_fingerprint = fingerprint[:12]
            records.append(
                GoogleKeyRecord(
                    key_id=f"{Provider.GOOGLE.value}:{short_fingerprint}",
                    value=value,
                    label=f"Google {short_fingerprint}",
                    provider=Provider.GOOGLE.value,
                    source=str(self._path),
                )
            )

        return tuple(records)


def load_google_keys(path: str | Path) -> tuple[GoogleKeyRecord, ...]:
    path_obj = Path(path)
    if not path_obj.exists():
        return ()
    return GoogleKeyLoader(path).load()