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

from api.app.chunk import router as chunk_router
from api.app.document import router as document_router
from api.app.contract_review import router as contract_review_router
from api.app.receipt_recognize import router as receipt_recognize_router
from api.app.logger import init_logger

print("Starting server...")

init_logger()
app = FastAPI()
app.include_router(document_router)
app.include_router(chunk_router)
app.include_router(contract_review_router)
app.include_router(receipt_recognize_router)

if __name__ == "__main__":
    uvicorn.run("api.app.main:app", host="127.0.0.1", port=8000, reload=True)
