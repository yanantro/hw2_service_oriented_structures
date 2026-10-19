from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI
from marketplace_api.apis.orders_api import router as orders_router
from marketplace_api.apis.products_api import router as products_router
from marketplace_api.apis.promo_codes_api import router as promo_codes_router

import app.impl.handlers
from app.db import pool
from app.errors import register_error_handlers
from app.logging_middleware import RequestLoggingMiddleware, setup_logging

SPEC_PATH = Path(__file__).resolve().parent.parent / "openapi" / "openapi.yaml"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await pool.open(wait=True)
    yield
    await pool.close()


setup_logging()
app = FastAPI(title="Marketplace API", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)
register_error_handlers(app)

app.include_router(products_router)
app.include_router(orders_router)
app.include_router(promo_codes_router)

_spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
app.openapi = lambda: _spec
