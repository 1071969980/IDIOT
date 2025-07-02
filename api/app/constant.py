from pathlib import Path
import os

CACHE_DIR = Path(os.environ["CACHE_DIR"]) \
    if "CACHE_DIR" in os.environ \
    else Path(__file__).parent.parent.parent.absolute()

print("CACHE_DIR:", CACHE_DIR)

LOG_DIR = CACHE_DIR / "logs"

LOGFIRE_LOG_ENDPOINT = os.getenv("LOGFIRE_LOG_ENDPOINT")\
    if "LOGFIRE_LOG_ENDPOINT" in os.environ \
    else None
print("LOGFIRE_LOG_ENDPOINT:", LOGFIRE_LOG_ENDPOINT)

DEFAULT_DATA_BASE_NAME = "default.db"

LEGAL_FILE_EXTENSIONS = [".docx", ".doc", ".pdf", ".md" ,".txt"]
