from pydantic import BaseModel

class RetryConfig(BaseModel):
    max_retry: int = 3
    retry_interval_seconds: int = 1

class RetryConfigForAPIError(BaseModel):
    situations: dict[str, RetryConfig]
    max_total_retry: int = -1