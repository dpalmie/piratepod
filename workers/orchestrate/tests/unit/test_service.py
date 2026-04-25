import asyncio

import orchestrate.service as service
from orchestrate.schemas import AudioResponse, GenerateRequest, IngestResponse


def test_generate_podcast_uses_ingest_title_when_request_title_missing(
    monkeypatch,
) -> None:
    async def ingest(_client, _url: str) -> IngestResponse:
        return IngestResponse(
            title="Jina Title",
            url="https://example.com/",
            markdown="Markdown body",
        )

    async def scriptgen(_client, markdown: str, title: str) -> str:
        assert markdown == "Markdown body"
        assert title == "Jina Title"
        return markdown

    async def audiogen(_client, script: str, title: str) -> AudioResponse:
        assert script == "Markdown body"
        assert title == "Jina Title"
        return AudioResponse(
            audio_path=".piratepod/audio/jina-title.wav",
            audio_format="wav",
        )

    monkeypatch.setattr(service, "_ingest", ingest)
    monkeypatch.setattr(service, "_scriptgen", scriptgen)
    monkeypatch.setattr(service, "_audiogen", audiogen)

    result = asyncio.run(service.generate_podcast(GenerateRequest(url="example.com")))

    assert result.title == "Jina Title"
    assert result.url == "https://example.com/"
    assert result.markdown == "Markdown body"
    assert result.script == "Markdown body"
    assert result.audio_path == ".piratepod/audio/jina-title.wav"
    assert result.audio_format == "wav"


def test_generate_podcast_request_title_overrides_ingest_title(monkeypatch) -> None:
    async def ingest(_client, _url: str) -> IngestResponse:
        return IngestResponse(
            title="Jina Title",
            url="https://example.com/",
            markdown="Markdown body",
        )

    async def scriptgen(_client, markdown: str, title: str) -> str:
        assert title == "Manual Title"
        return markdown

    async def audiogen(_client, script: str, title: str) -> AudioResponse:
        assert title == "Manual Title"
        return AudioResponse(
            audio_path=".piratepod/audio/manual-title.wav",
            audio_format="wav",
        )

    monkeypatch.setattr(service, "_ingest", ingest)
    monkeypatch.setattr(service, "_scriptgen", scriptgen)
    monkeypatch.setattr(service, "_audiogen", audiogen)

    result = asyncio.run(
        service.generate_podcast(
            GenerateRequest(url="example.com", title="Manual Title")
        )
    )

    assert result.title == "Manual Title"
