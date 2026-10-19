from decimal import Decimal

from marketplace_api.models.order_item_request import OrderItemRequest
from marketplace_api.models.order_response import OrderResponse

from app.config import MAX_PERCENT_DISCOUNT, ORDER_RATE_LIMIT_MINUTES
from app.db import pool
from app.errors import ApiError, order_not_found, product_not_found
from app.services.money import money

ACTIVE_STATUSES = ("CREATED", "PAYMENT_PENDING")

TRANSITIONS = {
    "CREATED": {"PAYMENT_PENDING", "CANCELED"},
    "PAYMENT_PENDING": {"PAID", "CANCELED"},
    "PAID": {"SHIPPED"},
    "SHIPPED": {"COMPLETED"},
    "COMPLETED": set(),
    "CANCELED": set(),
}


def merge_items(items: list[OrderItemRequest]) -> dict[int, int]:
    merged: dict[int, int] = {}
    for item in items:
        merged[item.product_id] = merged.get(item.product_id, 0) + item.quantity
    return merged


async def lock_user(conn, user_id: int) -> None:
    await conn.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))


async def check_rate_limit(conn, user_id: int, operation: str) -> None:
    cur = await conn.execute(
        """
        SELECT ceil(extract(epoch FROM created_at + make_interval(mins => %s) - now()))::int AS retry_after
          FROM user_operations
         WHERE user_id = %s AND operation_type = %s
         ORDER BY created_at DESC
         LIMIT 1
        """,
        (ORDER_RATE_LIMIT_MINUTES, user_id, operation),
    )
    row = await cur.fetchone()
    if row is not None and row["retry_after"] > 0:
        raise ApiError(
            429, "ORDER_LIMIT_EXCEEDED",
            f"too many {operation} operations, wait {ORDER_RATE_LIMIT_MINUTES} min between them",
            {"operation": operation, "retry_after_seconds": row["retry_after"]},
        )


async def lock_products(conn, product_ids) -> dict[int, dict]:
    cur = await conn.execute(
        "SELECT id, price, stock, status FROM products WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
        (list(product_ids),),
    )
    return {row["id"]: row for row in await cur.fetchall()}


def check_catalog_and_stock(wanted: dict[int, int], products: dict[int, dict]) -> None:
    missing = [pid for pid in wanted if pid not in products]
    if missing:
        err = product_not_found(missing[0])
        err.details = {"product_ids": missing}
        raise err

    inactive = [pid for pid in wanted if products[pid]["status"] != "ACTIVE"]
    if inactive:
        raise ApiError(409, "PRODUCT_INACTIVE", "product is not active",
                       {"product_ids": inactive,
                        "statuses": {str(pid): products[pid]["status"] for pid in inactive}})

    shortages = [
        {"product_id": pid, "requested": qty, "available": products[pid]["stock"]}
        for pid, qty in wanted.items()
        if products[pid]["stock"] < qty
    ]
    if shortages:
        raise ApiError(409, "INSUFFICIENT_STOCK", "insufficient stock", {"items": shortages})


async def change_stock(conn, quantities: dict[int, int], sign: int) -> None:
    async with conn.cursor() as cur:
        await cur.executemany(
            "UPDATE products SET stock = stock + %s WHERE id = %s",
            [(sign * qty, pid) for pid, qty in quantities.items()],
        )


async def save_items(conn, order_id: int, wanted: dict[int, int], products: dict[int, dict]) -> Decimal:
    async with conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO order_items (order_id, product_id, quantity, price_at_order) VALUES (%s, %s, %s, %s)",
            [(order_id, pid, qty, products[pid]["price"]) for pid, qty in wanted.items()],
        )
    return money(sum(products[pid]["price"] * qty for pid, qty in wanted.items()))


def calc_discount(total: Decimal, promo: dict) -> Decimal:
    value = promo["discount_value"]
    if promo["discount_type"] == "PERCENTAGE":
        if value > MAX_PERCENT_DISCOUNT:
            return money(0)
        return money(total * value / 100)
    return money(min(value, total))


async def load_promo_for_update(conn, *, code: str | None = None, promo_id: int | None = None) -> dict | None:
    field, value = ("code", code) if code is not None else ("id", promo_id)
    cur = await conn.execute(
        f"""
        SELECT *, now() BETWEEN valid_from AND valid_until AS in_window
          FROM promo_codes WHERE {field} = %s
           FOR UPDATE
        """,
        (value,),
    )
    return await cur.fetchone()


async def insert_operation(conn, user_id: int, operation: str) -> None:
    await conn.execute(
        "INSERT INTO user_operations (user_id, operation_type) VALUES (%s, %s)", (user_id, operation)
    )


async def lock_order(conn, order_id: int, user_id: int) -> dict:
    cur = await conn.execute("SELECT * FROM orders WHERE id = %s FOR UPDATE", (order_id,))
    order = await cur.fetchone()
    if order is None:
        raise order_not_found(order_id)
    if order["user_id"] != user_id:
        raise ApiError(403, "ORDER_OWNERSHIP_VIOLATION", "order belongs to another user", {"order_id": order_id})
    return order


async def build_response(conn, order_id: int) -> OrderResponse:
    cur = await conn.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    order = await cur.fetchone()
    cur = await conn.execute(
        "SELECT id, product_id, quantity, price_at_order FROM order_items WHERE order_id = %s ORDER BY id",
        (order_id,),
    )
    items = [{**i, "price_at_order": float(i["price_at_order"])} for i in await cur.fetchall()]
    return OrderResponse(
        id=order["id"], user_id=order["user_id"], status=order["status"],
        promo_code_id=order["promo_code_id"],
        total_amount=float(order["total_amount"]), discount_amount=float(order["discount_amount"]),
        items=items, created_at=order["created_at"], updated_at=order["updated_at"],
    )


async def create_order(user_id: int, items: list[OrderItemRequest], promo_code: str | None) -> OrderResponse:
    wanted = merge_items(items)
    async with pool.connection() as conn, conn.transaction():
        await lock_user(conn, user_id)

        await check_rate_limit(conn, user_id, "CREATE_ORDER")

        cur = await conn.execute(
            "SELECT id FROM orders WHERE user_id = %s AND status = ANY(%s::order_status[]) LIMIT 1",
            (user_id, list(ACTIVE_STATUSES)),
        )
        active = await cur.fetchone()
        if active:
            raise ApiError(409, "ORDER_HAS_ACTIVE", "user already has an active order",
                           {"active_order_id": active["id"]})

        products = await lock_products(conn, wanted.keys())
        check_catalog_and_stock(wanted, products)

        await change_stock(conn, wanted, sign=-1)

        cur = await conn.execute(
            "INSERT INTO orders (user_id, status, total_amount) VALUES (%s, 'CREATED', 0) RETURNING id",
            (user_id,),
        )
        order_id = (await cur.fetchone())["id"]

        total = await save_items(conn, order_id, wanted, products)
        discount, promo_id = money(0), None
        if promo_code is not None:
            promo = await load_promo_for_update(conn, code=promo_code)
            if (promo is None or not promo["active"] or promo["current_uses"] >= promo["max_uses"]
                    or not promo["in_window"]):
                raise ApiError(422, "PROMO_CODE_INVALID", "promo code is not found, expired, exhausted or inactive",
                               {"promo_code": promo_code})
            if total < promo["min_order_amount"]:
                raise ApiError(422, "PROMO_CODE_MIN_AMOUNT", "order amount is below promo code minimum",
                               {"min_order_amount": float(promo["min_order_amount"]), "order_amount": float(total)})
            discount, promo_id = calc_discount(total, promo), promo["id"]
            await conn.execute("UPDATE promo_codes SET current_uses = current_uses + 1 WHERE id = %s", (promo_id,))

        await conn.execute(
            "UPDATE orders SET total_amount = %s, discount_amount = %s, promo_code_id = %s WHERE id = %s",
            (total - discount, discount, promo_id, order_id),
        )

        await insert_operation(conn, user_id, "CREATE_ORDER")
        return await build_response(conn, order_id)


async def get_order(order_id: int, user_id: int) -> OrderResponse:
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT user_id FROM orders WHERE id = %s", (order_id,))
        order = await cur.fetchone()
        if order is None:
            raise order_not_found(order_id)
        if order["user_id"] != user_id:
            raise ApiError(403, "ORDER_OWNERSHIP_VIOLATION", "order belongs to another user", {"order_id": order_id})
        return await build_response(conn, order_id)


async def update_order(order_id: int, user_id: int, items: list[OrderItemRequest]) -> OrderResponse:
    wanted = merge_items(items)
    async with pool.connection() as conn, conn.transaction():
        await lock_user(conn, user_id)

        order = await lock_order(conn, order_id, user_id)
        if order["status"] != "CREATED":
            raise ApiError(409, "INVALID_STATE_TRANSITION", "order can be updated only in CREATED status",
                           {"current_status": order["status"]})
        await check_rate_limit(conn, user_id, "UPDATE_ORDER")

        cur = await conn.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
        old = {row["product_id"]: row["quantity"] for row in await cur.fetchall()}

        await lock_products(conn, set(old) | set(wanted))

        await change_stock(conn, old, sign=+1)

        products = await lock_products(conn, wanted.keys())
        check_catalog_and_stock(wanted, products)
        await change_stock(conn, wanted, sign=-1)

        await conn.execute("DELETE FROM order_items WHERE order_id = %s", (order_id,))
        total = await save_items(conn, order_id, wanted, products)
        discount, promo_id = money(0), order["promo_code_id"]
        if promo_id is not None:
            promo = await load_promo_for_update(conn, promo_id=promo_id)
            still_valid = promo["active"] and promo["in_window"] and total >= promo["min_order_amount"]
            if still_valid:
                discount = calc_discount(total, promo)
            else:
                await conn.execute("UPDATE promo_codes SET current_uses = current_uses - 1 WHERE id = %s",
                                   (promo_id,))
                promo_id = None

        await conn.execute(
            "UPDATE orders SET total_amount = %s, discount_amount = %s, promo_code_id = %s WHERE id = %s",
            (total - discount, discount, promo_id, order_id),
        )

        await insert_operation(conn, user_id, "UPDATE_ORDER")
        return await build_response(conn, order_id)


async def _cancel_locked(conn, order: dict) -> None:
    if order["status"] not in ACTIVE_STATUSES:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "order can be canceled only from CREATED or PAYMENT_PENDING",
                       {"current_status": order["status"], "target_status": "CANCELED"})
    cur = await conn.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order["id"],))
    items = {row["product_id"]: row["quantity"] for row in await cur.fetchall()}
    await lock_products(conn, items.keys())
    await change_stock(conn, items, sign=+1)
    if order["promo_code_id"] is not None:
        await conn.execute("UPDATE promo_codes SET current_uses = current_uses - 1 WHERE id = %s",
                           (order["promo_code_id"],))
    await conn.execute("UPDATE orders SET status = 'CANCELED' WHERE id = %s", (order["id"],))


async def cancel_order(order_id: int, user_id: int) -> OrderResponse:
    async with pool.connection() as conn, conn.transaction():
        order = await lock_order(conn, order_id, user_id)
        await _cancel_locked(conn, order)
        return await build_response(conn, order_id)


async def change_status(order_id: int, user_id: int, target: str) -> OrderResponse:
    async with pool.connection() as conn, conn.transaction():
        order = await lock_order(conn, order_id, user_id)
        current = order["status"]
        if target not in TRANSITIONS[current]:
            raise ApiError(409, "INVALID_STATE_TRANSITION", f"transition from {current} to {target} is not allowed",
                           {"current_status": current, "target_status": target,
                            "allowed": sorted(TRANSITIONS[current])})
        if target == "CANCELED":
            await _cancel_locked(conn, order)
        else:
            await conn.execute("UPDATE orders SET status = %s WHERE id = %s", (target, order_id))
        return await build_response(conn, order_id)
