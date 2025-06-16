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

from .chunk import router as chunk_router
from .document import router as document_router

print("Starting server...")

app = FastAPI()
app.include_router(document_router)
app.include_router(chunk_router)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
