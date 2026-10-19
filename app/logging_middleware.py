import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

SENSITIVE_KEYS = ("password", "token", "secret")
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

logger = logging.getLogger("api.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            return json.dumps(record.msg, ensure_ascii=False, default=str)
        return json.dumps({"level": record.levelname, "message": record.getMessage()}, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    for name in ("api", "api.access"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.setLevel(logging.INFO)
        lg.propagate = False


def mask(value):
    if isinstance(value, dict):
        return {k: ("***" if any(s in k.lower() for s in SENSITIVE_KEYS) else mask(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v) for v in value]
    return value


def parse_body(raw: bytes):
    if not raw:
        return None
    try:
        return mask(json.loads(raw))
    except ValueError:
        return raw[:1000].decode("utf-8", errors="replace")


def header(scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        body_chunks: list[bytes] = []
        status = {"code": 500}

        async def receive_wrapper():
            message = await receive()
            if message["type"] == "http.request":
                body_chunks.append(message.get("body", b""))
            return message

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [(b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            raw_user = header(scope, b"x-user-id")
            entry = {
                "timestamp": started_at.isoformat(),
                "request_id": request_id,
                "method": scope["method"],
                "endpoint": scope["path"],
                "status_code": status["code"],
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                "user_id": int(raw_user) if raw_user and raw_user.isdigit() else None,
            }
            if scope["method"] in MUTATING_METHODS:
                entry["request_body"] = parse_body(b"".join(body_chunks))
            logger.info(entry)
