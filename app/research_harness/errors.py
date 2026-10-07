from __future__ import annotations

from dataclasses import dataclass

import httpx


class ProviderError(Exception):
    def __init__(
        self,
        error_type: str,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        stage: str | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable
        self.status_code = status_code
        self.stage = stage

    @property
    def error_message(self) -> str:
        return str(self)


class DraftValidationError(Exception):
    def __init__(self, error_type: str, message: str, *, raw: str = "", draft=None):
        super().__init__(message)
        self.error_type = error_type
        self.raw = raw
        self.draft = draft


@dataclass(frozen=True)
class ClassifiedProviderError:
    error_type: str
    retryable: bool
    status_code: int | None
    message: str


def classify_provider_error(exc: BaseException) -> ClassifiedProviderError:
    if isinstance(exc, ProviderError):
        return ClassifiedProviderError(exc.error_type, exc.retryable, exc.status_code, str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        status = int(exc.response.status_code) if exc.response is not None else None
        message = str(exc)
        if status in {401, 403}:
            return ClassifiedProviderError("auth_quota", False, status, message)
        if status == 429:
            return ClassifiedProviderError("rate_limit", True, status, message)
        if status is not None and status >= 500:
            return ClassifiedProviderError("server_error", True, status, message)
        return ClassifiedProviderError("http_error", False, status, message)
    if isinstance(exc, (TimeoutError, httpx.TimeoutException, httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteError, httpx.PoolTimeout, httpx.RemoteProtocolError)):
        return ClassifiedProviderError("timeout", True, None, str(exc))
    return ClassifiedProviderError("provider_error", False, None, str(exc))


def is_provider_exception(exc: BaseException) -> bool:
    if isinstance(exc, ProviderError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return True
    return isinstance(exc, (
        TimeoutError,
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteError,
        httpx.PoolTimeout,
        httpx.RemoteProtocolError,
    ))


def as_provider_error(exc: BaseException, *, stage: str | None = None) -> ProviderError:
    classified = classify_provider_error(exc)
    if isinstance(exc, ProviderError):
        if stage and not exc.stage:
            exc.stage = stage
        return exc
    return ProviderError(
        classified.error_type,
        classified.message,
        retryable=classified.retryable,
        status_code=classified.status_code,
        stage=stage,
    )
