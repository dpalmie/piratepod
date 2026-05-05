import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from piratepod_core.logging import get_logger

from .config import (
    AUDIOGEN_URL,
    DEFAULT_PODCAST_AUTHOR,
    DEFAULT_PODCAST_DESCRIPTION,
    DEFAULT_PODCAST_LANGUAGE,
    DEFAULT_PODCAST_TITLE,
    HTTP_TIMEOUT,
    INGEST_URL,
    RSS_URL,
    SCRIPTGEN_URL,
)
from .schemas import (
    AudioResponse,
    EpisodeResponse,
    FeedResponse,
    GenerateRequest,
    GenerateResponse,
    IngestResponse,
    PodcastResponse,
    ScriptgenResponse,
    SourceResponse,
)

log = get_logger(__name__)

StageFunc = Callable[[str, str], Awaitable[None]]
_podcast_lock = asyncio.Lock()


async def generate_podcast(req: GenerateRequest) -> GenerateResponse:
    return await run_pipeline(req)


async def run_pipeline(
    req: GenerateRequest,
    set_stage: StageFunc | None = None,
) -> GenerateResponse:
    urls = [str(url) for url in req.urls]
    log.info("orchestrate.start", urls=urls, url_count=len(urls), title=req.title)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        await _set_stage(set_stage, "ingest", "ingesting source URLs")
        sources = list(await asyncio.gather(*(_ingest(client, url) for url in urls)))
        title = _episode_title(req.title, sources)
        await _set_stage(set_stage, "script", "generating podcast script")
        script = await _scriptgen(client, sources, title)
        await _set_stage(set_stage, "audio", "generating audio")
        audio = await _audiogen(client, script, title)
        await _set_stage(set_stage, "publish", "publishing episode to RSS")
        podcast, episode = await _publish_to_rss(client, title, script, audio)

    log.info(
        "orchestrate.done",
        urls=[source.url for source in sources],
        source_count=len(sources),
        script_chars=len(script),
        audio_path=audio.audio_path,
        feed_url=podcast.feed_url,
        episode_id=episode.id,
    )
    return GenerateResponse(
        urls=[source.url for source in sources],
        sources=list(sources),
        title=title,
        script=script,
        audio_path=audio.audio_path,
        audio_format=audio.audio_format,
        feed_url=podcast.feed_url,
        episode_id=episode.id,
        episode_audio_url=episode.audio_url,
    )


async def fetch_feed() -> FeedResponse:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        podcast = await _ensure_self_host_podcast(client)
        episodes = await _list_episodes(client, podcast.id)
    return FeedResponse(podcast=podcast, episodes=episodes)


async def _set_stage(set_stage: StageFunc | None, stage: str, message: str) -> None:
    if set_stage is not None:
        await set_stage(stage, message)


async def _ingest(client: httpx.AsyncClient, url: str) -> IngestResponse:
    try:
        resp = await client.post(f"{INGEST_URL}/ingest/url", json={"url": url})
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"ingest failed: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"ingest unreachable: {e}") from e

    try:
        data = resp.json()
    except ValueError as e:
        raise HTTPException(502, "ingest returned invalid json") from e
    try:
        return IngestResponse.model_validate(data)
    except ValidationError as e:
        raise HTTPException(502, "ingest returned malformed response") from e


def _episode_title(request_title: str | None, sources: list[SourceResponse]) -> str:
    if request_title and request_title.strip():
        return request_title
    if len(sources) == 1:
        return sources[0].title
    return f"Digest: {sources[0].title} + {len(sources) - 1} more"


async def _scriptgen(
    client: httpx.AsyncClient, sources: list[SourceResponse], title: str
) -> str:
    try:
        resp = await client.post(
            f"{SCRIPTGEN_URL}/scriptgen/script",
            json={
                "sources": [source.model_dump() for source in sources],
                "title": title,
            },
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"scriptgen failed: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"scriptgen unreachable: {e}") from e

    try:
        data = resp.json()
    except ValueError as e:
        raise HTTPException(502, "scriptgen returned invalid json") from e
    try:
        return ScriptgenResponse.model_validate(data).script
    except ValidationError as e:
        raise HTTPException(502, "scriptgen returned malformed response") from e


async def _audiogen(
    client: httpx.AsyncClient, script: str, title: str
) -> AudioResponse:
    try:
        resp = await client.post(
            f"{AUDIOGEN_URL}/audiogen/audio",
            json={"script": script, "title": title},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = _upstream_error("audiogen failed", e.response)
        raise HTTPException(502, detail) from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"audiogen unreachable: {e}") from e

    try:
        data = resp.json()
    except ValueError as e:
        raise HTTPException(502, "audiogen returned invalid json") from e
    try:
        return AudioResponse.model_validate(data)
    except ValidationError as e:
        raise HTTPException(502, "audiogen returned malformed response") from e


async def _publish_to_rss(
    client: httpx.AsyncClient, title: str, script: str, audio: AudioResponse
) -> tuple[PodcastResponse, EpisodeResponse]:
    podcast = await _ensure_self_host_podcast(client)
    episode = await _publish_episode(client, podcast.id, title, script, audio)
    return podcast, episode


async def _ensure_self_host_podcast(client: httpx.AsyncClient) -> PodcastResponse:
    async with _podcast_lock:
        return await _ensure_self_host_podcast_locked(client)


async def _ensure_self_host_podcast_locked(
    client: httpx.AsyncClient,
) -> PodcastResponse:
    try:
        resp = await client.get(f"{RSS_URL}/podcasts")
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            502,
            f"rss list podcasts failed: {e.response.status_code}",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"rss unreachable: {e}") from e

    try:
        data = resp.json()
    except ValueError as e:
        raise HTTPException(502, "rss returned invalid podcasts json") from e
    if not isinstance(data, list):
        raise HTTPException(502, "rss returned malformed podcasts response")

    try:
        podcasts = [PodcastResponse.model_validate(item) for item in data]
    except ValidationError as e:
        raise HTTPException(502, "rss returned malformed podcast") from e

    if len(podcasts) == 1:
        return podcasts[0]
    if len(podcasts) > 1:
        raise HTTPException(
            502,
            f"rss self-host expected exactly one podcast, found {len(podcasts)}",
        )
    return await _create_default_podcast(client)


async def _list_episodes(
    client: httpx.AsyncClient, podcast_id: str
) -> list[EpisodeResponse]:
    try:
        resp = await client.get(f"{RSS_URL}/podcasts/{podcast_id}/episodes")
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            502,
            f"rss list episodes failed: {e.response.status_code}",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"rss unreachable: {e}") from e

    try:
        data = resp.json()
    except ValueError as e:
        raise HTTPException(502, "rss returned invalid episodes json") from e
    if not isinstance(data, list):
        raise HTTPException(502, "rss returned malformed episodes response")
    try:
        return [EpisodeResponse.model_validate(item) for item in data]
    except ValidationError as e:
        raise HTTPException(502, "rss returned malformed episode") from e


async def _create_default_podcast(client: httpx.AsyncClient) -> PodcastResponse:
    try:
        resp = await client.post(
            f"{RSS_URL}/podcasts",
            json={
                "title": DEFAULT_PODCAST_TITLE,
                "description": DEFAULT_PODCAST_DESCRIPTION,
                "author": DEFAULT_PODCAST_AUTHOR,
                "language": DEFAULT_PODCAST_LANGUAGE,
            },
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            502,
            f"rss create podcast failed: {e.response.status_code}",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(502, f"rss unreachable: {e}") from e

    try:
        data = resp.json()
    except ValueError as e:
        raise HTTPException(502, "rss returned invalid podcast json") from e
    try:
        return PodcastResponse.model_validate(data)
    except ValidationError as e:
        raise HTTPException(502, "rss returned malformed podcast") from e


async def _publish_episode(
    client: httpx.AsyncClient,
    podcast_id: str,
    title: str,
    script: str,
    audio: AudioResponse,
) -> EpisodeResponse:
    audio_path = Path(audio.audio_path)
    if not audio_path.is_file():
        raise HTTPException(502, f"audiogen output not found: {audio.audio_path}")

    content_type = _audio_content_type(audio.audio_format, audio_path.suffix)
    with audio_path.open("rb") as f:
        try:
            resp = await client.post(
                f"{RSS_URL}/podcasts/{podcast_id}/episodes",
                data={"title": title, "description": script},
                files={"audio": (audio_path.name, f, content_type)},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                502,
                f"rss create episode failed: {e.response.status_code}",
            ) from e
        except httpx.RequestError as e:
            raise HTTPException(502, f"rss unreachable: {e}") from e

    try:
        data = resp.json()
    except ValueError as e:
        raise HTTPException(502, "rss returned invalid episode json") from e
    try:
        return EpisodeResponse.model_validate(data)
    except ValidationError as e:
        raise HTTPException(502, "rss returned malformed episode") from e


def _audio_content_type(audio_format: str, suffix: str) -> str:
    normalized = audio_format.lower().strip().lstrip(".")
    suffix = suffix.lower().strip().lstrip(".")
    if normalized == "wav" or suffix == "wav":
        return "audio/wav"
    if normalized == "mp3" or suffix == "mp3":
        return "audio/mpeg"
    raise HTTPException(502, f"unsupported generated audio format: {audio_format}")


def _upstream_error(prefix: str, response: httpx.Response) -> str:
    body = response.text.strip()
    message = f"{prefix}: {response.status_code}"
    if body:
        message += f": {body[:500]}"
    return message
