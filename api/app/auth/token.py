from datetime import timedelta
from typing import Annotated

from fastapi import Body, Depends, HTTPException, Query, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from api.authentication import USER_DB
from api.authentication.constant import (
    REMEMBER_ME_EXPIRE_DAYS,
    set_auth_token_cookie,
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
    response: Response,
    rememberMe: Annotated[bool, Query()] = False,
):
    user = await authenticate_user(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(status_code=401, detail="认证失败")

    # 根据remember_me参数决定token过期时间
    if rememberMe:
        access_token, expire_time_stamp = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(days=REMEMBER_ME_EXPIRE_DAYS),
        )
        # 设置remember_me cookie
        set_remember_me_cookie(response, access_token)
        return { "token_type": "bearer", "expires_in": expire_time_stamp }
    else:
        access_token, expire_time_stamp = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(minutes=15),
        )
        set_auth_token_cookie(response, access_token, 15*60) # 15分钟过期
        return {"token_type": "bearer", "expires_in": expire_time_stamp}


@router.post("/signup")
async def sign_up(
    username: Annotated[str, Body()],
    password: Annotated[str, Body()],
) -> Response:
    from api.juiceFS.creator import create_juicefs_for_user, check_juicefs_formatted
    import logfire

    user_id = await USER_DB.create_user(username=username, password=password)

    # 创建用户的 JuiceFS 环境（先检查是否已存在）
    try:
        if await check_juicefs_formatted(user_id):
            logfire.warning(f"JuiceFS already exists for user {user_id}")
        else:
            await create_juicefs_for_user(user_id)
            logfire.info(f"JuiceFS created for user {user_id}")
    except Exception as e:
        logfire.error(f"Failed to create JuiceFS for user {user_id}: {e}")

    return Response(status_code=status.HTTP_201_CREATED)

@router.get("/user_exists")
async def user_exists(username: str) -> dict[str, bool]:
    return {
        "exists": await USER_DB.get_user_by_username(username) is not None,
    }

@router.post("/token_healthy")
async def example_auth_required_api(
    user: Annotated[_User, Depends(get_current_active_user)],  # Using Depends validate the token and return the user
) -> None:
    pass


@router.post("/refresh_token")
async def refresh_token(
    user: Annotated[_User, Depends(get_current_active_user)],
    response: Response,
):
    access_token, expire_timestamp = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=15),
    )
    set_auth_token_cookie(response, access_token, 15*60)
    return {"token_type": "bearer", "expires_in": expire_timestamp}


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    """登出端点，清除remember_me cookie"""
    from api.authentication.constant import clear_auth_token_cookie
    clear_auth_token_cookie(response)
    return {"message": "登出成功"}


@router.delete("/user/{user_id}")
async def delete_user(
    user_id: str,
    user: Annotated[_User, Depends(get_current_active_user)],
) -> dict[str, str]:
    """删除用户及其 JuiceFS 环境

    只能删除当前登录的用户。
    """
    from api.juiceFS.creator import delete_juicefs_for_user, check_juicefs_formatted
    import logfire

    if str(user.id) != user_id:
        raise HTTPException(status_code=403, detail="无权删除其他用户")

    # 先删除用户的 JuiceFS 环境（检查是否存在）
    try:
        if await check_juicefs_formatted(user_id):
            await delete_juicefs_for_user(user_id)
            logfire.info(f"JuiceFS deleted for user {user_id}")
        else:
            logfire.warning(f"JuiceFS does not exist for user {user_id}")
    except Exception as e:
        logfire.error(f"Failed to delete JuiceFS for user {user_id}: {e}")

    # 删除用户记录
    success = await USER_DB.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在或删除失败")

    return {"message": "用户删除成功"}
