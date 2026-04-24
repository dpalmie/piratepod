import httpx
from fastapi import HTTPException

from piratepod_core.logging import get_logger

from .config import HTTP_TIMEOUT, INGEST_URL, SCRIPTGEN_URL
from .schemas import GenerateRequest, GenerateResponse

log = get_logger(__name__)


async def generate_podcast(req: GenerateRequest) -> GenerateResponse:
    url = str(req.url)
    log.info("orchestrate.start", url=url, title=req.title)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        markdown = await _ingest(client, url)
        script = await _scriptgen(client, markdown, req.title)

    log.info("orchestrate.done", url=url, script_chars=len(script))
    return GenerateResponse(url=url, title=req.title, markdown=markdown, script=script)


async def _ingest(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.post(f"{INGEST_URL}/ingest/url", json={"url": url})
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"ingest failed: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"ingest unreachable: {e}") from e
    return resp.text


async def _scriptgen(
    client: httpx.AsyncClient, markdown: str, title: str | None
) -> str:
    try:
        resp = await client.post(
            f"{SCRIPTGEN_URL}/scriptgen/script",
            json={"markdown": markdown, "title": title},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"scriptgen failed: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"scriptgen unreachable: {e}") from e
    return resp.json()["script"]
