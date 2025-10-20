from pydantic import BaseModel

class SessionToolConfigBase(BaseModel):
    enabled: bool