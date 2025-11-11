from datetime import timedelta
from typing import Annotated

from fastapi import Body, Depends, HTTPException, Query, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from api.authentication import USER_DB
from api.authentication.constant import (
    AUTH_HEADER,
    REMEMBER_ME_EXPIRE_DAYS,
    set_remember_me_cookie,
)
from api.authentication.utils import (
    _User,
    authenticate_user,
    create_access_token,
    get_current_active_user,
)

from .router_declare import router


@router.post("/token")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    rememberMe: Annotated[bool, Query()] = False,
    response: Response = None,
):
    user = await authenticate_user(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(status_code=401, detail="认证失败")

    # 根据remember_me参数决定token过期时间
    if rememberMe:
        access_token, expire = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(days=REMEMBER_ME_EXPIRE_DAYS),
        )
        # 设置remember_me cookie
        if response is not None:
            set_remember_me_cookie(response, access_token)
        return { "token_type": "bearer", "expires_in": expire }
    else:
        access_token, expire = create_access_token(data={"sub": str(user.id)})
        return {"access_token": access_token, "token_type": "bearer", "expires_in": expire}


@router.post("/signup")
async def sign_up(
    username: Annotated[str, Body()],
    password: Annotated[str, Body()],
) -> Response:
    await USER_DB.create_user(username=username, password=password)
    return Response(status_code=status.HTTP_201_CREATED)

@router.get("/user_exists")
async def user_exists(username: str) -> dict[str, bool]:
    return {
        "exists": await USER_DB.get_user_by_username(username) is not None,
    }

@router.post("/token_healthy")
async def example_auth_required_api(
    auth_header: Annotated[str, Depends(AUTH_HEADER)],  # decalre this for swagger UI generating a button to input the token
    user: Annotated[_User, Depends(get_current_active_user)],  # Using Depends validate the token and return the user
) -> None:
    pass


@router.post("/refresh_token")
async def refresh_token(
    auth_header: Annotated[str, Depends(AUTH_HEADER)],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> dict[str, str]:
    access_token, expire = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer", "expires_in": expire}


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    """登出端点，清除remember_me cookie"""
    from api.authentication.constant import clear_remember_me_cookie
    clear_remember_me_cookie(response)
    return {"message": "登出成功"}
