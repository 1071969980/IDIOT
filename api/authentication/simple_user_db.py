
from .constant import PWD_CONTEXT
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from api.authentication.sql_orm import SimpleUser
from api.sql_orm_models.constant import SQL_ENGINE
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete

from .data_model import UserBase
from .user_db_base import UserDBBase

class SimpleUserDB(UserDBBase):
    def create_user(self, username, password, *args, **kwargs):
        hashed_password = PWD_CONTEXT.hash(password)
        uuid = str(uuid4())
        now = datetime.now(tz=timezone(timedelta(hours=8)))
        user = SimpleUser(
            uuid=uuid,
            user_name=username,
            hashed_password=hashed_password,
            create_time=now,
        )
        with Session(bind=SQL_ENGINE) as session:
            session.add(user)
            session.commit()

    def get_user(self, username, *args, **kwargs):
        with Session(bind=SQL_ENGINE) as session:
            cmd = select(SimpleUser).where(SimpleUser.user_name == username)
            user = session.execute(cmd).scalar_one_or_none()
            if not user:
                return None
            return UserBase(
                username=user.user_name,
                hashed_password=user.hashed_password,
                disabled=user.is_deleted,
            )

    def update_user(self, 
                    uuid, 
                    user_name:str|None = None,
                    password:str|None = None,
                    *args, 
                    **kwargs):
        update_dict = {}
        if user_name:
            update_dict["user_name"] = user_name
        if password:
            update_dict["hashed_password"] = PWD_CONTEXT.hash(password)

        with Session() as session:
            cmd = update(SimpleUser)\
                    .where(SimpleUser.uuid == uuid)\
                    .values(**update_dict)
            session.execute(cmd)
            session.commit()

    def delete_user(self, uuid: str, *args, **kwargs):
        with Session() as session:
            cmd = delete(SimpleUser)\
                    .where(SimpleUser.uuid == uuid)
            session.execute(cmd)
            session.commit()
        
