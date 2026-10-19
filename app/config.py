import os
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://marketplace:marketplace@localhost:5432/marketplace")
ORDER_RATE_LIMIT_MINUTES = int(os.getenv("ORDER_RATE_LIMIT_MINUTES", "1"))
MAX_PERCENT_DISCOUNT = 70
