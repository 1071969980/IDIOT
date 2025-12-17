import asyncio
from asyncio import CancelledError, Event, Task
from enum import Enum
from api.redis import CLIENT, HIL_xadd_msg_with_expired, HIL_RedisMsg
from hashlib import sha256
from typing import Any, Literal
from pydantic import BaseModel, field_validator
import pickle
from uuid import uuid4
import contextlib
import json
from api.app.graceful_shutdown import set_following_task_for_graceful_shutdown_timeout
from .context import SEND_STREAM_KEY_PREFIX, RECV_STREAM_KEY_PREFIX, STREAM_EXPIRE_TIME
from .execption import HILInterruptCancelled, HILMsgStreamMissingError

class HILInterruptContentAgentToolCallBodyType(str, Enum):
    ChoiceForm = "ChoiceForm"

class HILInterruptContentAgentToolCallBody(BaseModel):
    tool_name: str
    type: HILInterruptContentAgentToolCallBodyType
    tool_exec_uuid: str
    detail: Any

    @field_validator('detail')
    @classmethod
    def validate_detail_json_serializable(cls, v):
        """
        验证detail字段是否可以序列化为JSON
        支持原生Python字典或可以转为纯JSON的Pydantic BaseModel
        """
        # 如果是Pydantic BaseModel，检查其是否可以序列化为JSON
        if isinstance(v, BaseModel):
            try:
                # 尝试转换为dict，这会触发Pydantic的序列化验证
                v = v.model_dump(mode="json")
                return v
            except Exception as e:
                raise ValueError(f"detail字段中的Pydantic模型无法序列化为JSON: {e}")

        # 如果是原生Python类型，尝试JSON序列化
        try:
            json.dumps(v)
            return v
        except (TypeError, ValueError) as e:
            raise ValueError(f"detail字段无法序列化为JSON: {e}")

        # 其他情况都拒绝
        raise ValueError(f"detail字段必须是可JSON序列化的原生Python类型或Pydantic BaseModel，当前类型: {type(v)}")

class HILInterruptContent(BaseModel):
    source: Literal["agent_tool_call"]
    body: HILInterruptContentAgentToolCallBody

async def cancel_signal(event: Event) -> None:
    await event.wait()

async def timeout_signal(timeout: int) -> None:
    await asyncio.sleep(timeout)

async def waiting_recv(stream_key: str, start_id: str = "0"):
    return await CLIENT.xread({stream_key:start_id}, block=3600*24*1000)

def _parse_recv_result(recv_stream_key: str, recv_result: Any, msg_id: str):
    if recv_result:
        stream_data = recv_result[recv_stream_key.encode()][0]
        for _data_id, data in stream_data:
            recv_msg_id = data.get(b"msg_id").decode()
            if recv_msg_id == msg_id:
                return pickle.loads(data[b"content"]), _data_id
        return None, _data_id # return last read id for next read
    return None, None

async def interrupt(content: HILInterruptContent,
                    stream_identifier: str,
                    timeout: int = 3600,
                    timeout_retry: int = 6,
                    cancel_event: Event | None = None
                    ) -> str | dict | None:
    with set_following_task_for_graceful_shutdown_timeout(60):
        task = asyncio.create_task(
            __interrupt(content, stream_identifier, timeout, timeout_retry, cancel_event)
            )
    try:
        return await task
    except CancelledError:
        return None

async def __interrupt(content: HILInterruptContent,
                    stream_identifier: str,
                    timeout: int = 3600,
                    timeout_retry: int = 6,
                    cancel_event: Event | None = None
                    ) -> str | dict:
    if not isinstance(content, HILInterruptContent):
        raise ValueError("Invalid content type, should be HILInterruptContent")
    # 0. prepare
    id = stream_identifier
    send_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{id}"
    recv_stream_key = f"{RECV_STREAM_KEY_PREFIX}:{id}"
    timeout_retry_count = 0

    while True:
        if timeout_retry_count >= timeout_retry:
            raise HILInterruptCancelled("Interrupt cancelled, due to timeout")
        # 1. check redis stream exist
        send_exist = bool(await CLIENT.exists(send_stream_key))
        # 1.1 if not exist, raise exception
        if not send_exist:
            raise HILMsgStreamMissingError("human in loop send stream not exist, or expired")
        recv_exist = bool(await CLIENT.exists(recv_stream_key))
        if not recv_exist:
            raise HILMsgStreamMissingError("human in loop recv stream not exist. or expired")
        
        # 2. add msg to redis stream
        # using pickle to serialize msg to prevent issue caused by special character
        if timeout_retry_count == 0: # do not resend msg when timeout
            pickled_content = pickle.dumps(content) 
            msg_id = str(uuid4())

            await HIL_xadd_msg_with_expired(
                send_stream_key,
                HIL_RedisMsg(
                    msg_type="HIL_interrupt_request",
                    content=pickled_content,
                    msg_id=msg_id,
                ),
                STREAM_EXPIRE_TIME,
            )

        start_id = "0"
        while True:
            break_await_recv_flag = False
            # 3. wait for reading from recv steam or interrupt signal or timeout
            timeout_task = asyncio.create_task(timeout_signal(timeout))
            recv_task = asyncio.create_task(waiting_recv(recv_stream_key, start_id))
            if cancel_event:
                cancel_task = asyncio.create_task(cancel_signal(cancel_event))
                tasks: list[Task] = [timeout_task, recv_task, cancel_task]
            else:
                tasks: list[Task] = [timeout_task, recv_task]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            # cancel pending tasks
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            
            for task in done:
                if task == recv_task:
                    recv_result = await task
                    recv_msg, start_id = _parse_recv_result(recv_stream_key, recv_result, msg_id)
                    if recv_msg:
                        # 4 return msg, delete stream msg id
                        await CLIENT.xdel(recv_stream_key, start_id)
                        return recv_msg
                    if start_id is None:
                        raise RuntimeError("Unexpected situation")
                    # if no needed msg, goto 3
                elif task == timeout_task:
                    # 3.1. if timeout, goto 1
                    timeout_retry_count += 1
                    break_await_recv_flag = True
                elif task == cancel_task:
                    # 3.2 if interrupt signal, goto raise exception
                    raise HILInterruptCancelled

            if break_await_recv_flag:
                break # will go to 1
