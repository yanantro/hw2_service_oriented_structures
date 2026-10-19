#!/usr/bin/env bash
API=${API:-http://localhost:8000}
J='Content-Type: application/json'
step() { echo; echo "$1"; }

step "создание товаров"
curl -s -X POST $API/products -H "$J" -H 'X-User-Id: 100' \
  -d '{"name":"Ноутбук","description":"16 ГБ ОЗУ","price":1000,"stock":10,"category":"electronics","status":"ACTIVE"}'; echo
curl -s -X POST $API/products -H "$J" -H 'X-User-Id: 100' \
  -d '{"name":"Мышь","price":50.5,"stock":5,"category":"electronics","status":"ACTIVE"}'; echo
curl -s -X POST $API/products -H "$J" -H 'X-User-Id: 100' \
  -d '{"name":"Старая модель","price":300,"stock":5,"category":"electronics","status":"INACTIVE"}'; echo

step "список товаров"
curl -s "$API/products?status=ACTIVE&category=electronics&page=0&size=1"; echo

step "создание промокодов"
curl -s -X POST $API/promo-codes -H "$J" \
  -d '{"code":"SALE10","discount_type":"PERCENTAGE","discount_value":10,"min_order_amount":500,"max_uses":100,"valid_from":"2026-01-01T00:00:00Z","valid_until":"2030-01-01T00:00:00Z"}'; echo
curl -s -X POST $API/promo-codes -H "$J" \
  -d '{"code":"FIX300","discount_type":"FIXED_AMOUNT","discount_value":300,"min_order_amount":0,"max_uses":1,"valid_from":"2026-01-01T00:00:00Z","valid_until":"2030-01-01T00:00:00Z"}'; echo

step "создание заказа"
curl -s -X POST $API/orders -H "$J" -H 'X-User-Id: 1' \
  -d '{"items":[{"product_id":1,"quantity":2},{"product_id":2,"quantity":1}],"promo_code":"SALE10"}'; echo

step "изменение цены товара"
curl -s -X PUT $API/products/1 -H "$J" \
  -d '{"name":"Ноутбук","description":"16 ГБ ОЗУ","price":1500,"stock":8,"category":"electronics","status":"ACTIVE"}'; echo
curl -s $API/orders/1 -H 'X-User-Id: 1'; echo

step "обновление заказа"
curl -s -X PUT $API/orders/1 -H "$J" -H 'X-User-Id: 1' \
  -d '{"items":[{"product_id":2,"quantity":2}]}'; echo

step "отмена заказа"
curl -s -X POST $API/orders/1/cancel -H 'X-User-Id: 1'; echo

step "удаление товара"
curl -s -X DELETE $API/products/3; echo
