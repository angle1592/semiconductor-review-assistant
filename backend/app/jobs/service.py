from datetime import UTC, datetime
import json
import re
from typing import Any

from sqlmodel import Session

from app.jobs.models import DurableJob


_CREDENTIAL_KEYS = ("api_key", "apikey", "token", "authorization", "secret", "password")
_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|authorization|secret|password)\s*[:=]\s*\S+"),
    re.compile(r"\b(?:sk|key)-[A-Za-z0-9_-]{6,}\b"),
)


def _contains_credentials(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(secret in normalized for secret in _CREDENTIAL_KEYS):
                return True
            if _contains_credentials(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_credentials(item) for item in value)
    return False


def redact_error_detail(error: Exception) -> str:
    detail = f"{type(error).__name__}: {error}"[:1000]
    for pattern in _SECRET_PATTERNS:
        detail = pattern.sub("[REDACTED]", detail)
    return detail


def enqueue_job(
    session: Session,
    kind: str,
    payload: dict[str, Any],
    *,
    max_attempts: int = 3,
    now: datetime | None = None,
) -> DurableJob:
    if _contains_credentials(payload):
        raise ValueError("Job payload must not contain credential fields")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    timestamp = now or datetime.now(UTC)
    job = DurableJob(
        kind=kind,
        payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        max_attempts=max_attempts,
        available_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job
