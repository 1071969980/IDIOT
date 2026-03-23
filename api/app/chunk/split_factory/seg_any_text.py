import httpx
from wtpsplit import SaT
from functools import lru_cache
from deprecation import deprecated

from api.core.env_config import llm_service_config

SAT_SERVICE_URL = llm_service_config.sat_service_url

async def _request_split(texts: list[str]) -> list[list[str]]:
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
    return _request_split(texts)
    
