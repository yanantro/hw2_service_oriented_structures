import logging
import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("api")


class ApiError(Exception):

    def __init__(self, status: int, error_code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.error_code = error_code
        self.message = message
        self.details = details


def product_not_found(product_id) -> ApiError:
    return ApiError(404, "PRODUCT_NOT_FOUND", "product not found", {"product_id": product_id})


def order_not_found(order_id) -> ApiError:
    return ApiError(404, "ORDER_NOT_FOUND", "order not found", {"order_id": order_id})


_UNION_TAG = re.compile(r"^(constrained-|function-|lax-|strict-)|^(float|int|str|bool)$")


def _field_name(loc) -> str:
    parts = [str(p) for i, p in enumerate(loc) if not (i >= 2 and isinstance(p, str) and _UNION_TAG.search(p))]
    return ".".join(parts)


def _body(error_code: str, message: str, details: dict | None) -> dict:
    return {"error_code": error_code, "message": message, "details": details}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=_body(exc.error_code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError):
        errors, seen = [], set()
        for err in exc.errors():
            field = _field_name(err["loc"])
            if field in seen:
                continue
            seen.add(field)
            errors.append({"field": field, "message": err["msg"], "type": err["type"]})
        return JSONResponse(
            status_code=400,
            content=_body("VALIDATION_ERROR", "request validation failed", {"errors": errors}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "INTERNAL_ERROR")
        return JSONResponse(status_code=exc.status_code, content=_body(code, str(exc.detail).lower(), None))

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content=_body("INTERNAL_ERROR", "internal server error", None))
