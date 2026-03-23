from api.core.env_config import app_config

CACHE_DIR = app_config.cache_dir

print("CACHE_DIR:", CACHE_DIR)

DEFAULT_DATA_BASE_NAME = "postgres"

LEGAL_FILE_EXTENSIONS = [".docx", ".doc", ".pdf", ".md" ,".txt"]
