import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

import orchestrate.service as service
from orchestrate.schemas import (
    AudioResponse,
    EpisodeResponse,
    GenerateRequest,
    IngestResponse,
    PodcastResponse,
)


def test_generate_podcast_uses_ingest_title_when_request_title_missing(
    monkeypatch,
) -> None:
    async def ingest(_client, _url: str) -> IngestResponse:
        return IngestResponse(
            title="Jina Title",
            url="https://example.com/",
            markdown="Markdown body",
        )

    async def scriptgen(_client, sources: list[IngestResponse], title: str) -> str:
        assert len(sources) == 1
        assert sources[0].markdown == "Markdown body"
        assert title == "Jina Title"
        return sources[0].markdown

    async def audiogen(_client, script: str, title: str) -> AudioResponse:
        assert script == "Markdown body"
        assert title == "Jina Title"
        return AudioResponse(
            audio_path=".piratepod/audio/jina-title.wav",
            audio_format="wav",
        )

    async def publish(_client, title: str, script: str, audio: AudioResponse):
        assert title == "Jina Title"
        assert script == "Markdown body"
        assert audio.audio_format == "wav"
        return (
            PodcastResponse(
                id="podcast-1",
                slug="feed",
                title="PiratePod",
                feed_url="http://localhost:8080/feeds/feed",
            ),
            EpisodeResponse(
                id="episode-1",
                audio_url="http://localhost:8080/media/feed/episode-1.wav",
            ),
        )

    monkeypatch.setattr(service, "_ingest", ingest)
    monkeypatch.setattr(service, "_scriptgen", scriptgen)
    monkeypatch.setattr(service, "_audiogen", audiogen)
    monkeypatch.setattr(service, "_publish_to_rss", publish)

    result = asyncio.run(
        service.generate_podcast(GenerateRequest(urls=["example.com"]))
    )

    assert result.title == "Jina Title"
    assert result.urls == ["https://example.com/"]
    assert result.sources[0].url == "https://example.com/"
    assert result.sources[0].markdown == "Markdown body"
    assert result.script == "Markdown body"
    assert result.audio_path == ".piratepod/audio/jina-title.wav"
    assert result.audio_format == "wav"
    assert result.feed_url == "http://localhost:8080/feeds/feed"
    assert result.episode_id == "episode-1"
    assert result.episode_audio_url == "http://localhost:8080/media/feed/episode-1.wav"


def test_generate_podcast_request_title_overrides_ingest_title(monkeypatch) -> None:
    async def ingest(_client, _url: str) -> IngestResponse:
        return IngestResponse(
            title="Jina Title",
            url="https://example.com/",
            markdown="Markdown body",
        )

    async def scriptgen(_client, sources: list[IngestResponse], title: str) -> str:
        assert title == "Manual Title"
        return sources[0].markdown

    async def audiogen(_client, script: str, title: str) -> AudioResponse:
        assert title == "Manual Title"
        return AudioResponse(
            audio_path=".piratepod/audio/manual-title.wav",
            audio_format="wav",
        )

    async def publish(_client, title: str, _script: str, _audio: AudioResponse):
        assert title == "Manual Title"
        return (
            PodcastResponse(
                id="podcast-1",
                slug="feed",
                title="PiratePod",
                feed_url="http://localhost:8080/feeds/feed",
            ),
            EpisodeResponse(
                id="episode-1",
                audio_url="http://localhost:8080/media/feed/episode-1.wav",
            ),
        )

    monkeypatch.setattr(service, "_ingest", ingest)
    monkeypatch.setattr(service, "_scriptgen", scriptgen)
    monkeypatch.setattr(service, "_audiogen", audiogen)
    monkeypatch.setattr(service, "_publish_to_rss", publish)

    result = asyncio.run(
        service.generate_podcast(
            GenerateRequest(urls=["example.com"], title="Manual Title")
        )
    )

    assert result.title == "Manual Title"


def test_generate_podcast_combines_multiple_urls_into_one_episode(monkeypatch) -> None:
    ingest_calls: list[str] = []
    publish_calls: list[str] = []

    async def ingest(_client, url: str) -> IngestResponse:
        ingest_calls.append(url)
        if "example.org" in url:
            return IngestResponse(
                title="Second Title",
                url="https://example.org/",
                markdown="Second markdown",
            )
        return IngestResponse(
            title="First Title",
            url="https://example.com/",
            markdown="First markdown",
        )

    async def scriptgen(_client, sources: list[IngestResponse], title: str) -> str:
        assert title == "Digest: First Title + 1 more"
        assert [source.title for source in sources] == ["First Title", "Second Title"]
        assert [source.markdown for source in sources] == [
            "First markdown",
            "Second markdown",
        ]
        return "Combined script"

    async def audiogen(_client, script: str, title: str) -> AudioResponse:
        assert script == "Combined script"
        assert title == "Digest: First Title + 1 more"
        return AudioResponse(
            audio_path=".piratepod/audio/digest.wav",
            audio_format="wav",
        )

    async def publish(_client, title: str, script: str, audio: AudioResponse):
        publish_calls.append(title)
        assert script == "Combined script"
        assert audio.audio_format == "wav"
        return (
            PodcastResponse(
                id="podcast-1",
                slug="feed",
                title="PiratePod",
                feed_url="http://localhost:8080/feeds/feed",
            ),
            EpisodeResponse(
                id="episode-1",
                audio_url="http://localhost:8080/media/feed/episode-1.wav",
            ),
        )

    monkeypatch.setattr(service, "_ingest", ingest)
    monkeypatch.setattr(service, "_scriptgen", scriptgen)
    monkeypatch.setattr(service, "_audiogen", audiogen)
    monkeypatch.setattr(service, "_publish_to_rss", publish)

    result = asyncio.run(
        service.generate_podcast(
            GenerateRequest(urls=["example.com", "https://example.org"])
        )
    )

    assert ingest_calls == ["https://example.com/", "https://example.org/"]
    assert publish_calls == ["Digest: First Title + 1 more"]
    assert result.urls == ["https://example.com/", "https://example.org/"]
    assert [source.title for source in result.sources] == [
        "First Title",
        "Second Title",
    ]
    assert result.script == "Combined script"


def test_run_pipeline_reports_stage_progress(monkeypatch) -> None:
    stages: list[tuple[str, str]] = []

    async def ingest(_client, _url: str) -> IngestResponse:
        return IngestResponse(
            title="Jina Title",
            url="https://example.com/",
            markdown="Markdown body",
        )

    async def scriptgen(_client, _sources: list[IngestResponse], _title: str) -> str:
        return "Script"

    async def audiogen(_client, _script: str, _title: str) -> AudioResponse:
        return AudioResponse(audio_path=".piratepod/audio/episode.wav", audio_format="wav")

    async def publish(_client, _title: str, _script: str, _audio: AudioResponse):
        return (
            PodcastResponse(
                id="podcast-1",
                slug="feed",
                title="PiratePod",
                feed_url="http://localhost:8080/feeds/feed",
            ),
            EpisodeResponse(
                id="episode-1",
                audio_url="http://localhost:8080/media/feed/episode-1.wav",
            ),
        )

    async def set_stage(stage: str, message: str) -> None:
        stages.append((stage, message))

    monkeypatch.setattr(service, "_ingest", ingest)
    monkeypatch.setattr(service, "_scriptgen", scriptgen)
    monkeypatch.setattr(service, "_audiogen", audiogen)
    monkeypatch.setattr(service, "_publish_to_rss", publish)

    asyncio.run(service.run_pipeline(GenerateRequest(urls=["example.com"]), set_stage))

    assert [stage for stage, _message in stages] == [
        "ingest",
        "script",
        "audio",
        "publish",
    ]


def test_scriptgen_sends_all_sources(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"script": "Combined script"})

    monkeypatch.setattr(service, "SCRIPTGEN_URL", "http://scriptgen.test")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        script = asyncio.run(
            service._scriptgen(
                client,
                [
                    IngestResponse(
                        title="First",
                        url="https://example.com/",
                        markdown="First markdown",
                    ),
                    IngestResponse(
                        title="Second",
                        url="https://example.org/",
                        markdown="Second markdown",
                    ),
                ],
                "Digest",
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert script == "Combined script"
    assert requests[0].url == "http://scriptgen.test/scriptgen/script"
    payload = json.loads(requests[0].content)
    assert payload == {
        "title": "Digest",
        "sources": [
            {
                "title": "First",
                "url": "https://example.com/",
                "markdown": "First markdown",
            },
            {
                "title": "Second",
                "url": "https://example.org/",
                "markdown": "Second markdown",
            },
        ],
    }


def test_audio_content_type_supports_wav_and_mp3() -> None:
    assert service._audio_content_type("wav", ".wav") == "audio/wav"
    assert service._audio_content_type("mp3", ".mp3") == "audio/mpeg"


def test_audio_content_type_rejects_unknown_format() -> None:
    with pytest.raises(HTTPException) as exc:
        service._audio_content_type("flac", ".flac")

    assert exc.value.status_code == 502


def test_publish_episode_uploads_audio_file(tmp_path: Path, monkeypatch) -> None:
    audio_path = tmp_path / "episode.wav"
    audio_path.write_bytes(b"RIFFfakeWAVE")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": "episode-1",
                "audio_url": "http://localhost:8080/media/feed/episode-1.wav",
            },
        )

    monkeypatch.setattr(service, "RSS_URL", "http://rss.test")
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        result = asyncio.run(
            service._publish_episode(
                client,
                "podcast-1",
                "Episode",
                "Script body",
                AudioResponse(audio_path=str(audio_path), audio_format="wav"),
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert result.id == "episode-1"
    assert requests[0].url == "http://rss.test/podcasts/podcast-1/episodes"
    assert b'name="title"' in requests[0].content
    assert b'filename="episode.wav"' in requests[0].content
    assert b"audio/wav" in requests[0].content


def test_publish_episode_requires_audio_file() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _req: httpx.Response(500))
    )
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                service._publish_episode(
                    client,
                    "podcast-1",
                    "Episode",
                    "Script body",
                    AudioResponse(audio_path="/nope.wav", audio_format="wav"),
                )
            )
    finally:
        asyncio.run(client.aclose())

    assert exc.value.status_code == 502


def test_ensure_self_host_podcast_creates_default_when_missing(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(
            201,
            json={
                "id": "podcast-1",
                "slug": "feed",
                "title": "PiratePod",
                "feed_url": "http://localhost:8080/feeds/feed",
            },
        )

    monkeypatch.setattr(service, "RSS_URL", "http://rss.test")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        podcast = asyncio.run(service._ensure_self_host_podcast(client))
    finally:
        asyncio.run(client.aclose())

    assert podcast.id == "podcast-1"
    assert [r.method for r in requests] == ["GET", "POST"]


def test_ensure_self_host_podcast_rejects_multiple_podcasts(monkeypatch) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "podcast-1",
                    "slug": "one",
                    "title": "One",
                    "feed_url": "http://localhost:8080/feeds/one",
                },
                {
                    "id": "podcast-2",
                    "slug": "two",
                    "title": "Two",
                    "feed_url": "http://localhost:8080/feeds/two",
                },
            ],
        )

    monkeypatch.setattr(service, "RSS_URL", "http://rss.test")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(service._ensure_self_host_podcast(client))
    finally:
        asyncio.run(client.aclose())

    assert exc.value.status_code == 502
    assert "expected exactly one podcast" in exc.value.detail
