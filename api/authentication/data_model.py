from pydantic import BaseModel

class UserModel(BaseModel):
    uuid: str
    username: str
    hashed_password: str
    disabled: bool = False