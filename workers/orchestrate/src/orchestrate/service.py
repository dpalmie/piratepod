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
    GenerateRequest,
    GenerateResponse,
    IngestResponse,
    PodcastResponse,
)

log = get_logger(__name__)


async def generate_podcast(req: GenerateRequest) -> GenerateResponse:
    url = str(req.url)
    log.info("orchestrate.start", url=url, title=req.title)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        ingest = await _ingest(client, url)
        title = req.title or ingest.title
        script = await _scriptgen(client, ingest.markdown, title)
        audio = await _audiogen(client, script, title)
        podcast, episode = await _publish_to_rss(client, title, script, audio)

    log.info(
        "orchestrate.done",
        url=url,
        script_chars=len(script),
        audio_path=audio.audio_path,
        feed_url=podcast.feed_url,
        episode_id=episode.id,
    )
    return GenerateResponse(
        url=ingest.url,
        title=title,
        markdown=ingest.markdown,
        script=script,
        audio_path=audio.audio_path,
        audio_format=audio.audio_format,
        feed_url=podcast.feed_url,
        episode_id=episode.id,
        episode_audio_url=episode.audio_url,
    )


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


async def _scriptgen(client: httpx.AsyncClient, markdown: str, title: str) -> str:
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
        raise HTTPException(502, f"audiogen failed: {e.response.status_code}") from e
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
