from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, BinaryIO, Callable

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

    def __repr__(self) -> str:
        loaded = self._records is not None
        return f"GoogleKeyLoader(path={self._path!r}, loaded={loaded})"

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

    def _capture_stream_metadata(self, stream: BinaryIO) -> _FileMetadata:
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


import json
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

import httpx
from fastapi.responses import StreamingResponse


@dataclass(frozen=True)
class ErrorClassification:
    type: str
    retryable: bool
    should_rotate: bool
    status_code: int | None = None
    message: str = ""

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class GoogleNativeAdapter:
    DEFAULT_CONNECT_TIMEOUT = 15
    DEFAULT_READ_TIMEOUT = 300
    DEFAULT_WRITE_TIMEOUT = 30
    DEFAULT_POOL_TIMEOUT = 30
    DEFAULT_MAX_CONNECTIONS = 100
    DEFAULT_MAX_KEEPALIVE = 20
    ERROR_CODE_UNAVAILABLE = 503

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=self.DEFAULT_CONNECT_TIMEOUT,
                read=self.DEFAULT_READ_TIMEOUT,
                write=self.DEFAULT_WRITE_TIMEOUT,
                pool=self.DEFAULT_POOL_TIMEOUT,
            ),
            limits=httpx.Limits(
                max_connections=self.DEFAULT_MAX_CONNECTIONS,
                max_keepalive_connections=self.DEFAULT_MAX_KEEPALIVE,
            ),
        )
        self._base_url = "https://generativelanguage.googleapis.com/v1beta"

    def _build_url(self, model: str, method: str) -> str:
        return f"{self._base_url}/models/{model}:{method}"

    def _clean_headers(self, headers: dict[str, str]) -> dict[str, str]:
        cleaned = dict(headers)
        for header in ("Authorization", "x-goog-api-key", "x-api-key"):
            cleaned.pop(header, None)
        return cleaned

    def _clean_params(self, params: dict[str, str]) -> dict[str, str]:
        cleaned = dict(params)
        cleaned.pop("key", None)
        return cleaned

    def _add_api_key(self, headers: dict[str, str], api_key: str) -> dict[str, str]:
        headers = dict(headers)
        headers["x-goog-api-key"] = api_key
        return headers

    def _prepare_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    def _classify_error(self, error: httpx.Response | Exception) -> ErrorClassification:
        if isinstance(error, httpx.TimeoutException):
            return ErrorClassification(
                type="timeout",
                retryable=True,
                should_rotate=True,
                message=str(error),
            )
        if isinstance(error, httpx.ConnectError):
            return ErrorClassification(
                type="network",
                retryable=True,
                should_rotate=True,
                message=str(error),
            )
        if isinstance(error, httpx.Response):
            status = error.status_code
            if status == 429:
                return ErrorClassification(
                    type="quota",
                    retryable=True,
                    should_rotate=True,
                    status_code=status,
                    message="Quota exceeded",
                )
            if status in (401, 403):
                return ErrorClassification(
                    type="auth",
                    retryable=False,
                    should_rotate=True,
                    status_code=status,
                    message="Authentication failed",
                )
            if 500 <= status < 600:
                return ErrorClassification(
                    type="server",
                    retryable=True,
                    should_rotate=True,
                    status_code=status,
                    message="Server error",
                )
            if 400 <= status < 500:
                return ErrorClassification(
                    type="client",
                    retryable=False,
                    should_rotate=False,
                    status_code=status,
                    message="Client error",
                )
        return ErrorClassification(
            type="unknown",
            retryable=False,
            should_rotate=False,
            message=str(error),
        )

    def _process_sse_chunks(self, chunks: list[bytes]) -> list[bytes]:
        result = []
        for chunk in chunks:
            for line in chunk.splitlines():
                if line.startswith(b"data:"):
                    result.append(line)
        return result

    def _failover_before_first_byte(self, keys: list[str], error: ErrorClassification) -> str | None:
        if len(keys) <= 1:
            return None
        return keys[1]

    def _handle_stream_failover(
        self, stream: Any, keys: list[str], error: ErrorClassification, current_key_idx: int
    ) -> str | None:
        if current_key_idx + 1 < len(keys):
            return keys[current_key_idx + 1]
        return None

    async def _execute_with_failover(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        keys: list[str],
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        last_error: ErrorClassification | None = None
        last_exception: httpx.HTTPStatusError | None = None
        for i, api_key in enumerate(keys):
            try:
                return await self._execute_unary(
                    model, method, payload, api_key, None, None
                )
            except httpx.HTTPStatusError as e:
                last_error = self._classify_error(e.response)
                if not last_error.should_rotate:
                    raise
                if i < len(keys) - 1:
                    continue
        if last_exception:
            raise httpx.HTTPStatusError(
                f"All keys exhausted: {last_error.message if last_error else 'unknown error'}",
                request=last_exception.request,
                response=last_exception.response,
            ) from last_exception
        raise httpx.HTTPStatusError(
            "All keys exhausted",
            request=httpx.Request("POST", ""),
            response=httpx.Response(self.ERROR_CODE_UNAVAILABLE),
        )

    async def _execute_stream_with_failover(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        keys: list[str],
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> StreamingResponse:
        last_error: ErrorClassification | None = None
        last_exception: httpx.HTTPStatusError | None = None
        for i, api_key in enumerate(keys):
            try:
                return await self._execute_stream(
                    model, method, payload, api_key, None, None
                )
            except httpx.HTTPStatusError as e:
                last_error = self._classify_error(e.response)
                if not last_error.should_rotate:
                    raise
                if i < len(keys) - 1:
                    continue
        if last_exception:
            raise httpx.HTTPStatusError(
                f"All keys exhausted: {last_error.message if last_error else 'unknown error'}",
                request=last_exception.request,
                response=last_exception.response,
            ) from last_exception
        raise httpx.HTTPStatusError(
            "All keys exhausted",
            request=httpx.Request("POST", ""),
            response=httpx.Response(self.ERROR_CODE_UNAVAILABLE),
        )

    async def _capture_first_chunk(self, response: httpx.Response) -> bytes | None:
        aiter = response.aiter_raw
        if callable(aiter):
            aiter = aiter()
        if hasattr(aiter, "__await__"):
            aiter = await aiter
        if hasattr(aiter, "__aiter__"):
            async for chunk in aiter:
                return chunk
        else:
            for chunk in aiter:
                return chunk
        return None

    def _build_exhausted_error(self) -> dict[str, Any]:
        return {
            "error": {
                "code": 503,
                "message": "All API keys exhausted",
                "status": "UNAVAILABLE",
            }
        }

    def _build_request(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, str], dict[str, str], dict[str, Any]]:
        url = self._build_url(model, method)
        headers = self._clean_headers(incoming_headers or {})
        headers = self._add_api_key(headers, api_key)
        params = self._clean_params(incoming_params or {})
        if method == "streamGenerateContent":
            params["alt"] = "sse"
        json_payload = self._prepare_payload(payload)
        return url, headers, params, json_payload

    async def _execute_unary(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url, headers, params, json_payload = self._build_request(
            model, method, payload, api_key, None, None
        )
        response = await self._client.post(url, headers=headers, params=params, json=json_payload)
        if response.is_success:
            return response.json()
        error = self._classify_error(response)
        if error.should_rotate:
            raise httpx.HTTPStatusError(
                f"Error {response.status_code}", request=response.request, response=response
            )
        raise httpx.HTTPStatusError(
            f"Error {response.status_code}", request=response.request, response=response
        )

    async def _execute_stream(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> StreamingResponse:
        url, headers, params, json_payload = self._build_request(
            model, method, payload, api_key, None, None
        )

        async def stream_generator() -> AsyncGenerator[bytes, None]:
            async with self._client.stream(
                "POST", url, headers=headers, params=params, json=json_payload
            ) as response:
                if not response.is_success:
                    error = self._classify_error(response)
                    if error.should_rotate:
                        raise httpx.HTTPStatusError(
                            f"Error {response.status_code}", request=response.request, response=response
                        )
                    raise httpx.HTTPStatusError(
                        f"Error {response.status_code}", request=response.request, response=response
                    )

                first_chunk = await self._capture_first_chunk(response)
                if first_chunk is None:
                    raise httpx.HTTPStatusError(
                        "Empty response stream",
                        request=httpx.Request("POST", ""),
                        response=httpx.Response(self.ERROR_CODE_UNAVAILABLE),
                    )

                yield first_chunk
                aiter = response.aiter_raw
                if callable(aiter):
                    aiter = aiter()
                async for chunk in aiter:
                    if chunk:
                        yield chunk

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    async def generate_content(
        self,
        model: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            model, "generateContent", payload, [api_key], None, None
        )

    async def stream_generate_content(
        self,
        model: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> StreamingResponse:
        return await self._execute_stream_with_failover(
            model, "streamGenerateContent", payload, [api_key], None, None
        )

    async def count_tokens(
        self,
        model: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            model, "countTokens", payload, [api_key], None, None
        )

    async def _execute_with_failover(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        keys: list[str],
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        last_error: ErrorClassification | None = None
        last_exception: httpx.HTTPStatusError | None = None
        for i, api_key in enumerate(keys):
            try:
                return await self._execute_unary(
                    model, method, payload, api_key, None, None
                )
            except httpx.HTTPStatusError as e:
                last_error = self._classify_error(e.response)
                if not last_error.should_rotate:
                    raise
                if i < len(keys) - 1:
                    continue
        if last_exception:
            raise httpx.HTTPStatusError(
                f"All keys exhausted: {last_error.message if last_error else 'unknown error'}",
                request=last_exception.request,
                response=last_exception.response,
            ) from last_exception
        raise httpx.HTTPStatusError(
            "All keys exhausted",
            request=httpx.Request("POST", ""),
            response=httpx.Response(self.ERROR_CODE_UNAVAILABLE),
        )

    async def _execute_stream_with_failover(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        keys: list[str],
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> StreamingResponse:
        last_error: ErrorClassification | None = None
        last_exception: httpx.HTTPStatusError | None = None
        for i, api_key in enumerate(keys):
            try:
                return await self._execute_stream(
                    model, method, payload, api_key, None, None
                )
            except httpx.HTTPStatusError as e:
                last_error = self._classify_error(e.response)
                if not last_error.should_rotate:
                    raise
                if i < len(keys) - 1:
                    continue
        if last_exception:
            raise httpx.HTTPStatusError(
                f"All keys exhausted: {last_error.message if last_error else 'unknown error'}",
                request=last_exception.request,
                response=last_exception.response,
            ) from last_exception
        raise httpx.HTTPStatusError(
            "All keys exhausted",
            request=httpx.Request("POST", ""),
            response=httpx.Response(self.ERROR_CODE_UNAVAILABLE),
        )

    async def _capture_first_chunk(self, response: httpx.Response) -> bytes | None:
        aiter = response.aiter_raw
        if callable(aiter):
            aiter = aiter()
        if hasattr(aiter, "__await__"):
            aiter = await aiter
        if hasattr(aiter, "__aiter__"):
            async for chunk in aiter:
                return chunk
        else:
            for chunk in aiter:
                return chunk
        return None

    def _build_exhausted_error(self) -> dict[str, Any]:
        return {
            "error": {
                "code": 503,
                "message": "All API keys exhausted",
                "status": "UNAVAILABLE",
            }
        }

    def _build_request(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, str], dict[str, str], dict[str, Any]]:
        url = self._build_url(model, method)
        headers = self._clean_headers(incoming_headers or {})
        headers = self._add_api_key(headers, api_key)
        params = self._clean_params(incoming_params or {})
        if method == "streamGenerateContent":
            params["alt"] = "sse"
        json_payload = self._prepare_payload(payload)
        return url, headers, params, json_payload

    async def _execute_unary(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url, headers, params, json_payload = self._build_request(
            model, method, payload, api_key, None, None
        )
        response = await self._client.post(url, headers=headers, params=params, json=json_payload)
        if response.is_success:
            return response.json()
        error = self._classify_error(response)
        if error.should_rotate:
            raise httpx.HTTPStatusError(
                f"Error {response.status_code}", request=response.request, response=response
            )
        raise httpx.HTTPStatusError(
            f"Error {response.status_code}", request=response.request, response=response
        )

    async def _execute_stream(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> StreamingResponse:
        url, headers, params, json_payload = self._build_request(
            model, method, payload, api_key, None, None
        )

        async def stream_generator() -> AsyncGenerator[bytes, None]:
            async with self._client.stream(
                "POST", url, headers=headers, params=params, json=json_payload
            ) as response:
                if not response.is_success:
                    error = self._classify_error(response)
                    if error.should_rotate:
                        raise httpx.HTTPStatusError(
                            f"Error {response.status_code}", request=response.request, response=response
                        )
                    raise httpx.HTTPStatusError(
                        f"Error {response.status_code}", request=response.request, response=response
                    )

                first_chunk = await self._capture_first_chunk(response)
                if first_chunk is None:
                    raise httpx.HTTPStatusError(
                        "Empty response stream",
                        request=httpx.Request("POST", ""),
                        response=httpx.Response(self.ERROR_CODE_UNAVAILABLE),
                    )

                yield first_chunk
                aiter = response.aiter_raw
                if callable(aiter):
                    aiter = aiter()
                async for chunk in aiter:
                    if chunk:
                        yield chunk

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    async def generate_content(
        self,
        model: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            model, "generateContent", payload, [api_key], None, None
        )

    async def stream_generate_content(
        self,
        model: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> StreamingResponse:
        return await self._execute_stream_with_failover(
            model, "streamGenerateContent", payload, [api_key], None, None
        )

    async def count_tokens(
        self,
        model: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            model, "countTokens", payload, [api_key], None, None
        )

    async def _execute_with_failover(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        keys: list[str],
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        last_error: ErrorClassification | None = None
        last_exception: httpx.HTTPStatusError | None = None
        for i, api_key in enumerate(keys):
            try:
                return await self._execute_unary(
                    model, method, payload, api_key, None, None
                )
            except httpx.HTTPStatusError as e:
                last_error = self._classify_error(e.response)
                if not last_error.should_rotate:
                    raise
                if i < len(keys) - 1:
                    continue
        if last_exception:
            raise httpx.HTTPStatusError(
                f"All keys exhausted: {last_error.message if last_error else 'unknown error'}",
                request=last_exception.request,
                response=last_exception.response,
            ) from last_exception
        raise httpx.HTTPStatusError(
            "All keys exhausted",
            request=httpx.Request("POST", ""),
            response=httpx.Response(self.ERROR_CODE_UNAVAILABLE),
        )

    async def _execute_stream_with_failover(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        keys: list[str],
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> StreamingResponse:
        last_error: ErrorClassification | None = None
        last_exception: httpx.HTTPStatusError | None = None
        for i, api_key in enumerate(keys):
            try:
                return await self._execute_stream(
                    model, method, payload, api_key, None, None
                )
            except httpx.HTTPStatusError as e:
                last_error = self._classify_error(e.response)
                if not last_error.should_rotate:
                    raise
                if i < len(keys) - 1:
                    continue
        if last_exception:
            raise httpx.HTTPStatusError(
                f"All keys exhausted: {last_error.message if last_error else 'unknown error'}",
                request=last_exception.request,
                response=last_exception.response,
            ) from last_exception
        raise httpx.HTTPStatusError(
            "All keys exhausted",
            request=httpx.Request("POST", ""),
            response=httpx.Response(self.ERROR_CODE_UNAVAILABLE),
        )

    async def _capture_first_chunk(self, response: httpx.Response) -> bytes | None:
        aiter = response.aiter_raw
        if callable(aiter):
            aiter = aiter()
        if hasattr(aiter, "__await__"):
            aiter = await aiter
        if hasattr(aiter, "__aiter__"):
            async for chunk in aiter:
                return chunk
        else:
            for chunk in aiter:
                return chunk
        return None

    def _build_exhausted_error(self) -> dict[str, Any]:
        return {
            "error": {
                "code": 503,
                "message": "All API keys exhausted",
                "status": "UNAVAILABLE",
            }
        }

    def _build_request(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, str], dict[str, str], dict[str, Any]]:
        url = self._build_url(model, method)
        headers = self._clean_headers(incoming_headers or {})
        headers = self._add_api_key(headers, api_key)
        params = self._clean_params(incoming_params or {})
        if method == "streamGenerateContent":
            params["alt"] = "sse"
        json_payload = self._prepare_payload(payload)
        return url, headers, params, json_payload

    async def _execute_unary(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url, headers, params, json_payload = self._build_request(
            model, method, payload, api_key, None, None
        )
        response = await self._client.post(url, headers=headers, params=params, json=json_payload)
        if response.is_success:
            return response.json()
        error = self._classify_error(response)
        if error.should_rotate:
            raise httpx.HTTPStatusError(
                f"Error {response.status_code}", request=response.request, response=response
            )
        raise httpx.HTTPStatusError(
            f"Error {response.status_code}", request=response.request, response=response
        )

    async def _execute_stream(
        self,
        model: str,
        method: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> StreamingResponse:
        url, headers, params, json_payload = self._build_request(
            model, method, payload, api_key, None, None
        )

        async def stream_generator() -> AsyncGenerator[bytes, None]:
            async with self._client.stream(
                "POST", url, headers=headers, params=params, json=json_payload
            ) as response:
                if not response.is_success:
                    error = self._classify_error(response)
                    if error.should_rotate:
                        raise httpx.HTTPStatusError(
                            f"Error {response.status_code}", request=response.request, response=response
                        )
                    raise httpx.HTTPStatusError(
                        f"Error {response.status_code}", request=response.request, response=response
                    )

                first_chunk = await self._capture_first_chunk(response)
                if first_chunk is None:
                    raise httpx.HTTPStatusError(
                        "Empty response stream",
                        request=httpx.Request("POST", ""),
                        response=httpx.Response(self.ERROR_CODE_UNAVAILABLE),
                    )

                yield first_chunk
                aiter = response.aiter_raw
                if callable(aiter):
                    aiter = aiter()
                async for chunk in aiter:
                    if chunk:
                        yield chunk

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    async def generate_content(
        self,
        model: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            model, "generateContent", payload, [api_key], None, None
        )

    async def stream_generate_content(
        self,
        model: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> StreamingResponse:
        return await self._execute_stream_with_failover(
            model, "streamGenerateContent", payload, [api_key], None, None
        )

    async def count_tokens(
        self,
        model: str,
        payload: dict[str, Any],
        api_key: str,
        incoming_headers: dict[str, str] | None = None,
        incoming_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self._execute_with_failover(
            model, "countTokens", payload, [api_key], None, None
        )