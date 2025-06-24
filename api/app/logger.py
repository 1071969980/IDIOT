from loguru import logger
from constant import LOG_DIR, JAEGER_LOG_API
import sys
import os
import logfire

def init_logger():
    # file log
    logger.add(str(LOG_DIR / "app.log"), rotation="100 MB", level="DEBUG")
    # stderr log
    logger.add(sink=sys.stderr, level="WARNING")
    logger.info("Logger initialized")

    if JAEGER_LOG_API:
        os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = JAEGER_LOG_API
        logfire.configure(
            # Setting a service name is good practice in general, but especially
            # important for Jaeger, otherwise spans will be labeled as 'unknown_service'
            service_name="test_service",

            # Sending to Logfire is on by default regardless of the OTEL env vars.
            # Keep this line here if you don't want to send to both Jaeger and Logfire.
            send_to_logfire=False,
        )
        