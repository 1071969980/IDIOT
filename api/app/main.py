import os

DEBUG = bool(int(os.environ.get("API_DEBUG", "0")))
if DEBUG:
    import debugpy
    DEBUG_PORT = int(os.environ.get("API_DEBUG_PORT", "5678"))
    print(f"Debugger listening on port {DEBUG_PORT}")
    debugpy.listen(("0.0.0.0", DEBUG_PORT))
    debugpy.wait_for_client()
    
import uvicorn
from fastapi import FastAPI

# from api.app.chunk import router as chunk_router
# from api.app.document import router as document_router
# from api.app.contract_review import router as contract_review_router
# from api.app.receipt_recognize import router as receipt_recognize_router
from api.app.vector_db import router as vector_db_router
from api.logger import init_logger
from api.app.auth import router as auth_router

# from api.human_in_loop.http_worker.router import router as hil_router
# from api.human_in_loop.test.router_declare import router as hil_test_router

def init_db():
    from api.authentication import create_table as authentication_create_table
    authentication_create_table()
    from api.agent import create_table as agent_create_table
    agent_create_table()
    from api.chat import create_table as chat_create_table
    chat_create_table()

print("Initializing database...")
init_db()

print("Starting server...")

init_logger()
app = FastAPI()
# app.include_router(document_router)
# app.include_router(chunk_router)
# app.include_router(contract_review_router)
# app.include_router(receipt_recognize_router)
app.include_router(vector_db_router)
app.include_router(auth_router)

# app.include_router(hil_router)
# app.include_router(hil_test_router)

if __name__ == "__main__":
    # Run the server
    uvicorn.run("api.app.main:app", host="127.0.0.1", port=8000, reload=True)
