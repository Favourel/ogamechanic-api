import hashlib
import json
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django_redis import get_redis_connection


class IdempotencyConflict(Exception):
    pass


def _redis() -> Any:
    return get_redis_connection(
        getattr(settings, "IDEMPOTENCY_REDIS_ALIAS", "default")
    )


def _make_key(user_id: str, method: str, path: str, idem_key: str) -> str:
    return f"idem:v1:{user_id}:{method.upper()}:{path}:{idem_key}"


def _hash_payload(payload: Any) -> str:
    try:
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    except Exception:
        raw = repr(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def get_cached_response(
    *,
    user_id: str,
    method: str,
    path: str,
    idempotency_key: str,
    request_payload: Any,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return (cached_response, redis_key).

    Raises IdempotencyConflict when key reused with different payload.
    """
    redis_key = _make_key(user_id, method, path, idempotency_key)
    payload_hash = _hash_payload(request_payload)

    conn = _redis()
    existing = conn.get(redis_key)
    if not existing:
        return None, redis_key

    data = json.loads(existing)
    if data.get("payload_hash") != payload_hash:
        raise IdempotencyConflict(
            "Idempotency-Key reuse with different payload"
        )

    return data.get("response"), redis_key


def store_response(
    *,
    redis_key: str,
    request_payload: Any,
    response_payload: Dict[str, Any],
    ttl_seconds: int = 60 * 60 * 24,
) -> None:
    payload_hash = _hash_payload(request_payload)
    value = json.dumps(
        {"payload_hash": payload_hash, "response": response_payload},
        default=str,
    )
    _redis().setex(redis_key, ttl_seconds, value)
