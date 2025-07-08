from pydantic import BaseModel
from enum import Enum


class RecognizeRequest(BaseModel):
    hot_words: list[str] | None = None
    json_schemaes: list[dict]

class RecognizeResponse(BaseModel):
    ocr_res: str
    json_res: str
