from pathlib import Path

FILE_CACHE_DIR = Path(__file__).parent.parent.parent / "file_cache"
FILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

SQLLITE_DB_PATH = Path(__file__).parent.parent.parent / "db.sqlite3"

LEGAL_FILE_EXTENSIONS = [".docx", ".doc", ".pdf", ".md" ,".txt"]
