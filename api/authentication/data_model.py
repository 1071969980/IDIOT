from pydantic import BaseModel

class UserBase(BaseModel):
    username: str
    hashed_password: str
    disabled: bool = False