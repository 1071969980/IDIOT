from pathlib import Path
import os

CACHE_DIR = Path(os.environ["CACHE_DIR"]) \
    if "CACHE_DIR" in os.environ \
    else Path(__file__).parent.parent.parent.absolute()

print("CACHE_DIR:", CACHE_DIR)

FILE_CACHE_DIR = CACHE_DIR / "file_cache"
FILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = CACHE_DIR / "logs"

SQLLITE_DB_PATH = CACHE_DIR / "db.sqlite3"

LEGAL_FILE_EXTENSIONS = [".docx", ".doc", ".pdf", ".md" ,".txt"]
