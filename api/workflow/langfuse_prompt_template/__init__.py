import os
from langfuse import get_client

LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST")

if not (LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY and LANGFUSE_HOST):
    raise Exception("env vars LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_HOST are required")

LANGFUSE_CLIENT = get_client()