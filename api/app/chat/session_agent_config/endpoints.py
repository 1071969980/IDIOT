from fastapi import Body, Depends, HTTPException, status
from typing import Annotated

from api.authentication.utils import get_current_user_id
from api.redis.distributed_lock import RedisDistributedLock
from api.redis.lock_names import LockNames

from .router_declare import router
from .data_model import CommandRequest, CommandResponse
from .command.registry import COMMAND_REGISTRY


@router.post("/command", response_model=CommandResponse)
async def execute_command(
    request: Annotated[CommandRequest, Body()],
    user_id: Annotated[str, Depends(get_current_user_id)]
) -> CommandResponse:
    """执行指定命令，发生异常时自动执行回滚

    使用分布式锁确保同一用户同一会话的命令不会并发执行。
    """

    command_info = COMMAND_REGISTRY.get(request.command_name)
    if not command_info:
        error_msg = f"Command {request.command_name} not found"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_msg
        )

    # 使用Pydantic验证输入
    try:
        input_model = command_info['input_model'].model_validate(request.params)
    except Exception as validation_error:
        error_msg = f"Input validation failed: {str(validation_error)}"
        return CommandResponse(
            success=False,
            error_message=error_msg,
            command_name=request.command_name
        )

    # 分布式锁 key
    lock_key = LockNames.session_agent_config_command(request.session_id)

    async with RedisDistributedLock(lock_key, timeout=30):
        # 创建命令实例
        command_class = command_info['command_class']
        command_instance = command_class(input_model, request.session_id, user_id)

        try:
            # 执行命令
            result = await command_instance.execute()

            return CommandResponse(
                success=True,
                data=result,
                command_name=request.command_name,
                rollback_performed=False
            )
        except Exception as e:
            # 发生异常时尝试回滚
            rollback_performed = False
            try:
                if command_instance is not None:
                    await command_instance.rollback()
                    rollback_performed = True
            except NotImplementedError:
                # 如果回滚未实现，则跳过
                pass
            except Exception as rollback_error:
                pass
            return CommandResponse(
                success=False,
                error_message=str(e),
                command_name=request.command_name,
                rollback_performed=rollback_performed
            )
