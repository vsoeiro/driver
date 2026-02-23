"""Typed domain errors used by services/application layer."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for domain-level errors."""

    default_status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.message = str(message)
        self.status_code = int(status_code or self.default_status_code)
        super().__init__(self.message)


class NotFoundError(DomainError):
    default_status_code = 404


class ValidationError(DomainError):
    default_status_code = 400


class ConflictError(DomainError):
    default_status_code = 409


class ExternalServiceError(DomainError):
    default_status_code = 502

