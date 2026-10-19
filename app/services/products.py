from marketplace_api.models.product_create import ProductCreate
from marketplace_api.models.product_page import ProductPage
from marketplace_api.models.product_response import ProductResponse
from marketplace_api.models.product_update import ProductUpdate

from app.db import pool
from app.errors import product_not_found
from app.services.money import money

COLUMNS = "id, name, description, price, stock, category, status, seller_id, created_at, updated_at"


def to_response(row: dict) -> ProductResponse:
    return ProductResponse(**{**row, "price": float(row["price"]), "status": str(row["status"])})


async def create(data: ProductCreate, seller_id: int | None) -> ProductResponse:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO products (name, description, price, stock, category, status, seller_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING {COLUMNS}
            """,
            (data.name, data.description, money(data.price), data.stock, data.category,
             data.status.value, seller_id),
        )
        return to_response(await cur.fetchone())


async def get(product_id: int) -> ProductResponse:
    async with pool.connection() as conn:
        cur = await conn.execute(f"SELECT {COLUMNS} FROM products WHERE id = %s", (product_id,))
        row = await cur.fetchone()
        if row is None:
            raise product_not_found(product_id)
        return to_response(row)


async def list_page(page: int, size: int, status, category: str | None) -> ProductPage:
    where, params = [], []
    if status is not None:
        where.append("status = %s")
        params.append(status.value)
    if category is not None:
        where.append("category = %s")
        params.append(category)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    async with pool.connection() as conn:
        cur = await conn.execute(f"SELECT count(*) AS total FROM products {where_sql}", params)
        total = (await cur.fetchone())["total"]
        cur = await conn.execute(
            f"SELECT {COLUMNS} FROM products {where_sql} ORDER BY id LIMIT %s OFFSET %s",
            [*params, size, page * size],
        )
        rows = await cur.fetchall()
    return ProductPage(content=[to_response(r) for r in rows], totalElements=total, page=page, size=size)


async def update(product_id: int, data: ProductUpdate) -> ProductResponse:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE products
               SET name = %s, description = %s, price = %s, stock = %s, category = %s, status = %s
             WHERE id = %s
            RETURNING {COLUMNS}
            """,
            (data.name, data.description, money(data.price), data.stock, data.category,
             data.status.value, product_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise product_not_found(product_id)
        return to_response(row)


async def soft_delete(product_id: int) -> ProductResponse:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"UPDATE products SET status = 'ARCHIVED' WHERE id = %s RETURNING {COLUMNS}",
            (product_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise product_not_found(product_id)
        return to_response(row)
