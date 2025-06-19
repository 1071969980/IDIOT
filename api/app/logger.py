from loguru import logger
from constant import LOG_DIR
import sys

def init_logger():
    # file log
    logger.add(str(LOG_DIR / "app.log"), rotation="100 MB", level="DEBUG")
    # stderr log
    logger.add(sink=sys.stderr, level="WARNING")
    logger.info("Logger initialized")