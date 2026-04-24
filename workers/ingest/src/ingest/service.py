import os

import httpx
from fastapi import HTTPException

from piratepod_core.logging import get_logger

from .config import JINA_READER

log = get_logger(__name__)


async def fetch_url(url: str, *, timeout: float = 30.0) -> str:
    """Retrieve URL contents and return as markdown string."""
    headers = {}
    if key := os.getenv("JINA_API_KEY"):
        headers["Authorization"] = f"Bearer {key}"

    log.info("fetch_url.start", url=url)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            resp = await client.get(JINA_READER + url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(502, f"jina returned {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise HTTPException(502, f"fetch failed: {e}") from e

    log.info("fetch_url.done", url=url, bytes=len(resp.content))
    return resp.text
