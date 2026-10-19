from marketplace_api.apis.orders_api_base import BaseOrdersApi
from marketplace_api.apis.products_api_base import BaseProductsApi
from marketplace_api.apis.promo_codes_api_base import BasePromoCodesApi

from app.services import orders, products, promo_codes


class ProductsApi(BaseProductsApi):
    async def create_product(self, product_create, x_user_id):
        return await products.create(product_create, seller_id=x_user_id)

    async def list_products(self, page, size, status, category):
        return await products.list_page(page, size, status, category)

    async def get_product(self, id):
        return await products.get(id)

    async def update_product(self, id, product_update):
        return await products.update(id, product_update)

    async def delete_product(self, id):
        return await products.soft_delete(id)


class OrdersApi(BaseOrdersApi):
    async def create_order(self, x_user_id, order_create):
        return await orders.create_order(x_user_id, order_create.items, order_create.promo_code)

    async def get_order(self, id, x_user_id):
        return await orders.get_order(id, x_user_id)

    async def update_order(self, id, x_user_id, order_update):
        return await orders.update_order(id, x_user_id, order_update.items)

    async def cancel_order(self, id, x_user_id):
        return await orders.cancel_order(id, x_user_id)

    async def change_order_status(self, id, x_user_id, order_status_change):
        return await orders.change_status(id, x_user_id, order_status_change.status.value)


class PromoCodesApi(BasePromoCodesApi):
    async def create_promo_code(self, promo_code_create):
        return await promo_codes.create(promo_code_create)
