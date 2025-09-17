from pathlib import Path
import os

CACHE_DIR = Path(os.environ["CACHE_DIR"]) \
    if "CACHE_DIR" in os.environ \
    else Path(__file__).parent.parent.parent.absolute()

print("CACHE_DIR:", CACHE_DIR)

DEFAULT_DATA_BASE_NAME = "postgres"

LEGAL_FILE_EXTENSIONS = [".docx", ".doc", ".pdf", ".md" ,".txt"]
