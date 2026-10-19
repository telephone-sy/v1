from collections import OrderedDict, deque
from hashlib import sha256
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError


_memory_attempts: OrderedDict[str, deque[float]] = OrderedDict()
_memory_lock = Lock()
_memory_key_limit = 20_000
_REDIS_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('PEXPIRE', KEYS[1], ARGV[1]) end
return count
"""


def clear_memory_rate_limits() -> None:
    with _memory_lock:
        _memory_attempts.clear()


def enforce_rate_limit(
    request: Request,
    bucket: str,
    limit: int,
    seconds: int = 60,
    identity: str | None = None,
) -> None:
    client_host = request.client.host if request.client else "unknown"
    client_hash = sha256(client_host.encode("utf-8")).hexdigest()[:24]
    keys = [f"telephone-sy:rate:{bucket}:ip:{client_hash}"]
    if identity:
        identity_hash = sha256(identity.strip().lower().encode("utf-8")).hexdigest()[:24]
        keys.append(f"telephone-sy:rate:{bucket}:identity:{identity_hash}")
    redis_client = getattr(request.app.state, "redis", None)

    if redis_client is not None:
        try:
            for key in keys:
                count = int(redis_client.eval(_REDIS_SCRIPT, 1, key, seconds * 1000))
                if count > limit:
                    raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "طلبات كثيرة، حاول لاحقاً")
        except RedisError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "خدمة الحماية غير متاحة مؤقتاً") from None
        return

    now = monotonic()
    with _memory_lock:
        for key in keys:
            attempts = _memory_attempts.setdefault(key, deque())
            _memory_attempts.move_to_end(key)
            while attempts and now - attempts[0] >= seconds:
                attempts.popleft()
            if len(attempts) >= limit:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "طلبات كثيرة، حاول لاحقاً")
            attempts.append(now)
        while len(_memory_attempts) > _memory_key_limit:
            _memory_attempts.popitem(last=False)