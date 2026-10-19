from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from app.config import DATABASE_URL
pool = AsyncConnectionPool(DATABASE_URL, open=False, kwargs={"row_factory": dict_row})
