import asyncio
import contextlib
import pickle

import websockets
from loguru import logger
from jose import JWTError, jwt
from websockets.exceptions import ConnectionClosed
from pydantic import BaseModel, ValidationError
from uuid import uuid4

from api.authentication.constant import JWT_SECRET_KEY
from api.redis import CLIENT, HIL_xadd_msg_with_expired, HIL_RedisMsg

from ..context import SEND_STREAM_KEY_PREFIX, STREAM_EXPIRE_TIME
from .data_model import AUTH_TOKEN_KEY, JsonRPCError, JsonRPCRequest, JsonRPCResponse


LISTEN_PORT = 8000

async def send_error_response(websocket: websockets.ServerConnection,
                              id: str,
                              error_code: int,
                              error_message: str):
    payload = JsonRPCResponse(
        id=id,
        error=JsonRPCError(
            code=error_code,
            message=error_message,
        ),
    )
    await websocket.send(payload.model_dump_json())

def verfiy_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms="HS256")
        username: str = payload.get("sub")
        return username
    except JWTError:
        return False

async def verify_init_request(websocket: websockets.ServerConnection, rq: JsonRPCRequest):
    if rq.method != "init_session":
        # send error response and close connection
        await send_error_response(websocket, rq.id, -32600, "Invalid method")
        await websocket.close()
        return None, None
    user_token = rq.params.get(AUTH_TOKEN_KEY)
    if user_identifier := verfiy_token(user_token):
        pass
    else:
        await send_error_response(websocket, rq.id, -32602, "Invalid params")
        await websocket.close()
        return None, None
    return user_identifier, rq.params

async def handel_unack_worker(websocket: websockets.ServerConnection, 
                              resend_interval: int = 5,
                              heartbeat_interval: int = 1):
    import time
    resend_timestamp = {}
    while True:
        await asyncio.sleep(heartbeat_interval)
        for id, payload in un_ack_msg[websocket].items():
            if id not in resend_timestamp:
                resend_timestamp[id] = time.time()
            if time.time() - resend_timestamp[id] > resend_interval:
                await websocket.send(payload)
                resend_timestamp[id] = time.time()
        for id in resend_timestamp.keys():
            if id not in un_ack_msg[websocket]:
                resend_timestamp.pop(id)
        

async def read_stream(stream_name: str, start_id: str):
    while True:
        if bool(await CLIENT.exists(stream_name)):
            result = await CLIENT.xread(
                {stream_name: start_id},
                count=1,
                block=10000,
            )
            if result:
                return result
        else:
            return None
            

async def forwarding_send_stream(websocket: websockets.ServerConnection,
                              stream_identifier: str):
    send_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{stream_identifier}"
    
    start_id = "0"
    while True:
        result = await read_stream(send_stream_key, start_id)
        if not result:
            return
        msg_dict = result[0][1][0][1]
        start_id = result[0][1][0][0]
        msg_type:str = msg_dict[b"msg_type"].decode()
        msg = pickle.loads(msg_dict[b"msg"])
        msg_id = msg_dict[b"msg_id"]

        if not isinstance(msg, BaseModel):
            raise RuntimeError("Invalid msg type, should be pydantic.BaseModel")
        
        rq_id = str(uuid4())
        send_payload = JsonRPCRequest(
            id = rq_id,
            method = msg_type,
            params = {
                "msg_id": msg_id,
                "msg": msg.model_dump_json(),
            }
        )
        await websocket.send(send_payload.model_dump_json())
        un_ack_msg[websocket][rq_id] = send_payload
        

async def waiting_user_msg(websocket: websockets.ServerConnection,
                            stream_identifier: str):
    recv_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{stream_identifier}"
    
    while True:
        # ack send msg
        try:
            ws_payload = JsonRPCResponse.model_validate_json(await websocket.recv())
            if ws_payload.id in un_ack_msg[websocket] and ws_payload.result == "ack":
                un_ack_msg[websocket].pop(ws_payload.id)
                continue
        except ValidationError:
            pass
        # HIL response
        try:
            ws_payload = JsonRPCRequest.model_validate_json(await websocket.recv())
            if ws_payload.method == "HIL_interrupt_response" and ws_payload.params:
                msg_id = ws_payload.params.get("msg_id")
                msg = ws_payload.params.get("msg")
                if msg_id and msg:
                    await HIL_xadd_msg_with_expired(recv_stream_key,
                                                    HIL_RedisMsg(
                                                        msg_type = "HIL_interrupt_response",
                                                        msg = pickle.dumps(msg),
                                                        msg_id = msg_id,
                                                    ),
                                                    STREAM_EXPIRE_TIME)
                    # ack response
                    ack_response = JsonRPCResponse(
                        id = ws_payload.id,
                        result = "ack",
                    )
                    await websocket.send(ack_response.model_dump_json())
                else:
                    await send_error_response(websocket, ws_payload.id, -32603, "Invalid parameters, msg_id and msg are required")
            else:
                await send_error_response(websocket, ws_payload.id, -32601, "Method is not supported")
        except ValidationError:
            pass

        raise RuntimeError("Not implemented")

async def handle_connection(websocket: websockets.ServerConnection):
    try:
        un_ack_msg[websocket] = {}
        while True:
            # wait initial request
            message = await websocket.recv()
            rq = JsonRPCRequest.model_validate_json(message)
            user_identifier, init_params = await verify_init_request(websocket, rq)
            # check init params
            stream_identifier = init_params.get("stream_identifier")
            if not stream_identifier:
                await send_error_response(websocket, rq.id, -32602, "Invalid params")
                await websocket.close()
                return
            send_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{stream_identifier}"
            existed = bool(await CLIENT.exists(send_stream_key))
            if not existed:
                await send_error_response(websocket, rq.id, -32602, "Invalid stream_identifier")
                await websocket.close()
                return
            # ack response
            ack_response = JsonRPCResponse(
                id = rq.id,
                result = "ack",
            )
            await websocket.send(ack_response.model_dump_json())
            # create tasks
            tasks: list[asyncio.Task] = [
                asyncio.create_task(forwarding_send_stream(websocket, stream_identifier), 
                                    name="forwarding_send_stream"),
                asyncio.create_task(waiting_user_msg(websocket, stream_identifier), 
                                    name="waiting_user_msg"),
                asyncio.create_task(handel_unack_worker(websocket), 
                                    name="handel_unack_worker"),
            ]

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            
            await websocket.close()
            return

    except ConnectionClosed:
        pass

    finally:
        un_ack_msg.pop(websocket)

async def reporter():
    # report websocket connection number
    while True:
        await asyncio.sleep(5)
        logger.info(f"Websocket connection number: {len(un_ack_msg)}")
        

async def start_server():
    async with websockets.serve(handle_connection, "localhost", LISTEN_PORT, close_timeout=10) as server:
        await asyncio.gather(
            server.serve_forever(),
            reporter(),
        )

if __name__ == "__main__":
    un_ack_msg = {}
    asyncio.run(start_server())
