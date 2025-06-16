import uvicorn
from fastapi import FastAPI

from .chunk import router as chunk_router
from .document import router as document_router

app = FastAPI()
app.include_router(document_router)
app.include_router(chunk_router)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
