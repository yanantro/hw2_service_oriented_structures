create type product_status as enum ('ACTIVE', 'INACTIVE', 'ARCHIVED');
create type order_status as enum ('CREATED', 'PAYMENT_PENDING', 'PAID', 'SHIPPED', 'COMPLETED', 'CANCELED');
create type discount_type as enum ('PERCENTAGE', 'FIXED_AMOUNT');
create type operation_type as enum ('CREATE_ORDER', 'UPDATE_ORDER');

create function set_updated_at() returns trigger as $$
begin
    new.updated_at := now();
    return new;
end;
$$ language plpgsql;

create table products (
    id bigint generated always as identity primary key,
    name varchar(255) not null,
    description varchar(4000),
    price numeric(12, 2) not null check (price > 0),
    stock integer not null check (stock >= 0),
    category varchar(100) not null,
    status product_status not null,
    seller_id bigint,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index idx_products_status on products (status);
create index idx_products_category on products (category);
create trigger trg_products_updated_at before update on products
    for each row execute function set_updated_at();

create table promo_codes (
    id bigint generated always as identity primary key,
    code varchar(20) not null unique,
    discount_type discount_type not null,
    discount_value numeric(12, 2) not null check (discount_value > 0),
    min_order_amount numeric(12, 2) not null default 0 check (min_order_amount >= 0),
    max_uses integer not null check (max_uses > 0),
    current_uses integer not null default 0 check (current_uses >= 0 and current_uses <= max_uses),
    valid_from timestamptz not null,
    valid_until timestamptz not null,
    active boolean not null default true,
    check (valid_until > valid_from)
);

create table orders (
    id bigint generated always as identity primary key,
    user_id bigint not null,
    status order_status not null default 'CREATED',
    promo_code_id bigint references promo_codes (id),
    total_amount numeric(12, 2) not null check (total_amount >= 0),
    discount_amount numeric(12, 2) not null default 0 check (discount_amount >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index idx_orders_user_status on orders (user_id, status);
create unique index uq_orders_one_active_per_user on orders (user_id)
    where status in ('CREATED', 'PAYMENT_PENDING');
create trigger trg_orders_updated_at before update on orders
    for each row execute function set_updated_at();

create table order_items (
    id bigint generated always as identity primary key,
    order_id bigint not null references orders (id) on delete cascade,
    product_id bigint not null references products (id),
    quantity integer not null check (quantity between 1 and 999),
    price_at_order numeric(12, 2) not null check (price_at_order > 0)
);
create index idx_order_items_order on order_items (order_id);

create table user_operations (
    id bigint generated always as identity primary key,
    user_id bigint not null,
    operation_type operation_type not null,
    created_at timestamptz not null default now()
);
create index idx_user_operations_lookup on user_operations (user_id, operation_type, created_at desc);
