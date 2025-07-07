from pydantic import BaseModel

class RetryConfigForAPIError(BaseModel):
    error_code_to_match: list[str]