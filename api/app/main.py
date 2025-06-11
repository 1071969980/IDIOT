from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from .models import sqllite_engine, UploadedFile
from sqlalchemy.orm import Session
from .document import router as document_router

app = FastAPI()
app.include_router(document_router)

@app.get("/")
async def root():
    return HTMLResponse('''
        <html>
            <body>
                <form action="/document/upload" method="post" enctype="multipart/form-data">
                    <input type="file" name="file">
                    <input type="submit" value="Upload">
                </form>
            </body>
        </html>
    ''')
