from fastapi import FastAPI
from .document import router as document_router
from .document import upload, markdown
from .chunk import router as chunk_router
from .chunk import hierarchical_chunk

app = FastAPI()
app.include_router(document_router)
app.include_router(chunk_router)