from pydantic import BaseModel

class UserModel(BaseModel):
    username: str
    hashed_password: str
    disabled: bool = False