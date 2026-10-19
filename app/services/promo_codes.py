import psycopg
from marketplace_api.models.promo_code_create import PromoCodeCreate
from marketplace_api.models.promo_code_response import PromoCodeResponse

from app.db import pool
from app.errors import ApiError
from app.services.money import money


async def create(data: PromoCodeCreate) -> PromoCodeResponse:
    errors = []
    if data.discount_type.value == "PERCENTAGE" and data.discount_value > 100:
        errors.append({"field": "body.discount_value", "message": "percentage discount must be at most 100"})
    if data.valid_until <= data.valid_from:
        errors.append({"field": "body.valid_until", "message": "valid_until must be after valid_from"})
    if errors:
        raise ApiError(400, "VALIDATION_ERROR", "request validation failed", {"errors": errors})

    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO promo_codes (code, discount_type, discount_value, min_order_amount,
                                         max_uses, valid_from, valid_until, active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (data.code, data.discount_type.value, money(data.discount_value), money(data.min_order_amount),
                 data.max_uses, data.valid_from, data.valid_until,
                 True if data.active is None else data.active),
            )
            row = await cur.fetchone()
    except psycopg.errors.UniqueViolation:
        raise ApiError(409, "PROMO_CODE_ALREADY_EXISTS", "promo code already exists", {"code": data.code})

    return PromoCodeResponse(**{
        **row,
        "discount_value": float(row["discount_value"]),
        "min_order_amount": float(row["min_order_amount"]),
    })
