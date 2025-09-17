import os
from api.app.constant import CACHE_DIR

LOG_DIR = CACHE_DIR / "logs"

LOGFIRE_LOG_ENDPOINT = os.getenv("LOGFIRE_LOG_ENDPOINT")\
    if "LOGFIRE_LOG_ENDPOINT" in os.environ \
    else None
print("LOGFIRE_LOG_ENDPOINT:", LOGFIRE_LOG_ENDPOINT)