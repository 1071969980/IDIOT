"""
Human In The Loop Client Example

This client demonstrates how to interact with the human_in_loop module
using WebSocket and JSON-RPC 2.0 protocol.
"""

import asyncio
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed
from jose import jwt
from pydantic import BaseModel, Field, field_validator, ValidationError


# JSON-RPC 2.0 Pydantic Models
class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 Error object"""
    code: int
    message: str
    data: dict[str, Any] | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: int) -> int:
        valid_codes = [-32700, -32600, -32601, -32602, -32603]
        if v not in valid_codes:
            raise ValueError(f"Error code must be one of {valid_codes}")
        return v


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 Request object"""
    jsonrpc: str = Field(default="2.0", pattern="^2\\.0$")
    id: str | None = None
    method: str
    params: dict[str, Any] | None = None

    @field_validator("params")
    @classmethod
    def validate_params(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and not isinstance(v, dict):
            raise ValueError("params must be a dict")
        return v


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 Response object"""
    jsonrpc: str = Field(default="2.0", pattern="^2\\.0$")
    id: str | None = None
    result: Any = None
    error: JsonRpcError | None = None

    @field_validator("error")
    @classmethod
    def validate_error(cls, v: JsonRpcError | None) -> JsonRpcError | None:
        return v

    @field_validator("result")
    @classmethod
    def validate_result(cls, v: Any, info: dict[str, Any]) -> Any:
        if info.data.get("error") is not None and v is not None:
            raise ValueError("result and error cannot both be set")
        return v


@dataclass
class ClientConfig:
    """Configuration for the Human In The Loop client"""
    websocket_url: str = "ws://localhost:8000"
    jwt_secret_key: str = "your-secret-key"
    jwt_algorithm: str = "HS256"
    token_expiry_hours: int = 24


class HumanInLoopClient:
    """
    WebSocket client for Human In The Loop interactions
    
    This client handles:
    - JWT token authentication
    - WebSocket connection management
    - JSON-RPC 2.0 message protocol
    - Interrupt request/response handling
    - Notification processing
    - Message acknowledgment
    """
    
    def __init__(self, config: ClientConfig, username: str) -> None:
        self.config = config
        self.username = username
        self.websocket: websockets.ClientConnection | None = None
        self.connected = False
        self.stream_identifier: str | None = None
        self.interrupt_callback: Callable | None = None
        self._tasks: list[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
        self._login_validated = asyncio.Event()
        self._pending_request_ids: set[str] = set()
        
    def generate_jwt_token(self) -> str:
        """Generate JWT token for authentication"""
        raise NotImplementedError("JWT token generation is provided by other application code")
    
    def generate_session_id(self, stream_identifier: str) -> str:
        """Generate session ID from stream identifier"""
        raise NotImplementedError("Session ID generation is provided by other application code")
    
    def create_json_rpc_request(self, method: str, params: dict[str, Any], request_id: str | None = None) -> JsonRpcRequest:
        """Create JSON-RPC 2.0 request"""
        return JsonRpcRequest(
            id=request_id or str(uuid.uuid4()),
            method=method,
            params=params,
        )
    
    def create_json_rpc_response(self, request_id: str, result: Any = None, error: JsonRpcError | None = None) -> JsonRpcResponse:
        """Create JSON-RPC 2.0 response"""
        return JsonRpcResponse(
            id=request_id,
            result=result,
            error=error,
        )
    
    def create_json_rpc_error(self, code: int, message: str, data: dict[str, Any] | None = None) -> JsonRpcError:
        """Create JSON-RPC 2.0 error"""
        return JsonRpcError(code=code, message=message, data=data)
    
    async def connect(self, stream_identifier: str) -> bool:
        """Connect to WebSocket server and initialize session"""
        if self.connected:
            return True
            
        try:
            # Generate session ID
            self.stream_identifier = self.generate_session_id(stream_identifier)
            
            # Connect to WebSocket
            self.websocket = await websockets.connect(self.config.websocket_url)
            self.connected = True
            
            # Send initialization request
            init_params = {
                "auth_token": self.generate_jwt_token(),
                "stream_identifier": stream_identifier,
            }
            init_request = self.create_json_rpc_request("initialize", init_params)
            await self.websocket.send(init_request.model_dump_json())
            
            # Wait for initialization response
            response_data = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            response = JsonRpcResponse.model_validate_json(response_data)
            
            if response.result == "ack":
                # Set login validated event and start message handler
                self._login_validated.set()
                self._tasks = [
                    asyncio.create_task(self._message_handler(), name="message_handler")
                ]
                return True
            else:
                print(f"Initialization failed: {response}")
                await self.disconnect()
                return False
                
        except Exception as e:
            print(f"Connection failed: {e}")
            await self.disconnect()
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from WebSocket server"""
        self._shutdown_event.set()
        
        # Cancel all background tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Close WebSocket connection
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
        
        self.connected = False
        self.websocket = None
        self._tasks = []
    
    async def _message_handler(self) -> None:
        """Handle incoming WebSocket messages"""
        # Wait for login validation before processing messages
        await self._login_validated.wait()
        
        while self.connected and not self._shutdown_event.is_set():
            try:
                message = await self.websocket.recv()
                await self._process_message(message)
            except TimeoutError:
                continue
            except ConnectionClosed:
                break
            except Exception as e:
                print(f"Message handler error: {e}")
                break
    
    async def _process_message(self, message: str) -> None:
        """Process incoming JSON-RPC message"""
        # Try to parse as response first
        try:
            response = JsonRpcResponse.model_validate_json(message)
            if response.id is not None:
                # This is a response, remove from pending list
                self._pending_request_ids.discard(response.id)
                print(f"Received response for request {response.id}")
                return
        except ValidationError:
            # Not a response, try parsing as request
            pass
        
        # Parse as request
        try:
            request = JsonRpcRequest.model_validate_json(message)
            if request.id is None:
                # This is an invalid request - all requests should have an ID
                raise ValueError("Server request must have an ID")
            # This is a request from server, handle concurrently
            asyncio.create_task(self._handle_server_request_concurrently(request))
        except ValidationError as e:
            print(f"Error parsing message: {e}")
    
    async def _handle_server_request_concurrently(self, request: JsonRpcRequest) -> None:
        """Handle server request concurrently and send response without waiting"""
        try:
            # Send ack first
            ack_response = self.create_json_rpc_response(request.id, "ack")
            await self.websocket.send(ack_response.model_dump_json())
            print(f"Sent ack for request {request.id}")
            
            # Handle different request types
            if request.method == "HIL_interrupt_request":
                # Handle interrupt request
                if self.interrupt_callback:
                    # Extract msg_id and msg from params
                    msg_id = request.params.get("msg_id")
                    msg_data = request.params.get("msg")
                    
                    if msg_id and msg_data:
                        # Process the request
                        result = await self.interrupt_callback(msg_data, msg_id)
                        
                        # Send HIL_interrupt_response
                        response = self.create_json_rpc_request(
                            "HIL_interrupt_response",
                            {
                                "msg_id": msg_id,
                                "msg": result
                            }
                        )
                        # Add to pending requests when sending our own request
                        self._pending_request_ids.add(response.id)
                        await self.websocket.send(response.model_dump_json())
                        print(f"Sent response for interrupt request {msg_id}")
                        
            elif request.method == "Notification":
                # Handle notification
                print(f"Notification: {request.params}")
                # No further action needed for notifications
                
        except Exception as e:
            print(f"Error handling server request {request.id}: {e}")
    
    
    def register_interrupt_callback(self, callback: Callable) -> None:
        """Register callback for interrupt requests"""
        self.interrupt_callback = callback
    
    def unregister_interrupt_callback(self) -> None:
        """Unregister interrupt callback"""
        self.interrupt_callback = None


async def example_usage() -> None:
    """Example usage of the HumanInLoopClient"""
    
    # Configuration
    config = ClientConfig(
        websocket_url="ws://localhost:8000",
        jwt_secret_key="your-secret-key-here",  # Use same secret as server
        token_expiry_hours=24
    )
    
    # Create client
    client = HumanInLoopClient(config, username="example_user")
    
    try:
        # Connect to server
        stream_id = "example_session_123"
        if await client.connect(stream_id):
            print("Connected successfully!")
            
            # Register custom callback for interrupts
            async def custom_interrupt_handler(msg_data: dict[str, Any], msg_id: str) -> dict[str, Any]:
                print(f"Custom handler received interrupt: {msg_data}")
                return {"response": "Processed by custom handler", "confidence": 0.95}
            
            client.register_interrupt_callback(custom_interrupt_handler)
            
            # Keep client running
            print("Client is running. Press Ctrl+C to stop...")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\nShutting down...")
        else:
            print("Failed to connect")
            
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(example_usage())