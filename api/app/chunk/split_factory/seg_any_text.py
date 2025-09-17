import os
import httpx
from wtpsplit import SaT
from functools import lru_cache
from deprecation import deprecated

SAT_SERVICE_URL = os.environ.get("SAT_SERVICE_URL")

async def _request_split(texts: list[str]) -> list[list[str]]:
    if not SAT_SERVICE_URL:
        raise ValueError("SAT_SERVICE_URL is not set")
    if texts == []:
        return []
    if not isinstance(texts, list):
        texts = [texts]
    async with httpx.AsyncClient() as client:
        res = await client.post(
            SAT_SERVICE_URL,
            json={"texts": texts},
        )
        res.raise_for_status()
        return res.json().get("results")


async def split_into_sentences(texts: list[str]) -> list[str]:
    """Single paragraph (str) will be split into one sentences list.
    Multiple paragraphs (list[str]) will be split into one sentences list too, which is
      as joined split res list for each paragraph.
    """
    if not SAT_SERVICE_URL:
        raise ValueError("SAT_SERVICE_URL is not set")
    
    return _request_split(texts)
    
