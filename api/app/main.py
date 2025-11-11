import os


DEBUG = bool(int(os.environ.get("API_DEBUG", "0")))
if DEBUG:
    import debugpy
    DEBUG_PORT = int(os.environ.get("API_DEBUG_PORT", "5678"))
    print(f"Debugger listening on port {DEBUG_PORT}")
    debugpy.listen(("0.0.0.0", DEBUG_PORT))
    debugpy.wait_for_client()
    
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import json

# from api.app.chunk import router as chunk_router
# from api.app.document import router as document_router
# from api.app.contract_review import router as contract_review_router
# from api.app.receipt_recognize import router as receipt_recognize_router
from api.app.vector_db import router as vector_db_router
from api.logger import init_logger
from api.app.auth import router as auth_router
from api.app.chat import router as chat_router

# from api.human_in_loop.http_worker.router import router as hil_router
# from api.human_in_loop.test.router_declare import router as hil_test_router

async def init_db():
    from api.authentication import create_table as authentication_create_table
    await authentication_create_table()

    from api.chat import create_table as chat_create_table
    await chat_create_table()

    from api.agent import create_table as agent_create_table
    await agent_create_table()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing database...")
    await init_db()

    print("Starting server...")
    init_logger()

    # code before yield will be executed before the server starts
    yield
    # code after yield will be executed after the server stops
    pass

app = FastAPI(lifespan=lifespan)
# app.include_router(document_router)
# app.include_router(chunk_router)
# app.include_router(contract_review_router)
# app.include_router(receipt_recognize_router)
app.include_router(vector_db_router)
app.include_router(auth_router)
app.include_router(chat_router)

# app.include_router(hil_router)
# app.include_router(hil_test_router)

if DEBUG:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        try:
            exc_json = json.loads(str(exc))
            content = {
                "errors": exc_json,
                "request.body": await request.body(),
            }
        except Exception:
            content = {
                "errors": str(exc),
                "request.body": await request.body(),
            }
            
        return JSONResponse(content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

if __name__ == "__main__":
    # Run the server
    uvicorn.run("api.app.main:app", host="127.0.0.1", port=8000, reload=True)
