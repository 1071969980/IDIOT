from api.app.constant import CACHE_DIR
from api.core.env_config import logging_config

LOG_DIR = CACHE_DIR / "logs"

LOGFIRE_LOG_ENDPOINT = logging_config.logfire_log_endpoint
print("LOGFIRE_LOG_ENDPOINT:", LOGFIRE_LOG_ENDPOINT)