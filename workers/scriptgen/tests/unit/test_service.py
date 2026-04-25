import asyncio

import pytest
from fastapi import HTTPException

import scriptgen.service as service
from scriptgen.schemas import ScriptRequest


def test_generate_script_calls_intro_segment_outro_and_flattens(monkeypatch) -> None:
    calls: list[str] = []

    async def chat_json(_client, _messages, label: str):
        calls.append(label)
        if label == "intro":
            return {"intro": "Welcome to the show."}
        if label == "segment":
            return {
                "title": "Example Domain",
                "intro": "Here is why this page exists.",
                "main": "Example Domain is reserved for documentation examples.",
                "outro": "That makes it safe for demos.",
            }
        if label == "outro":
            return {"outro": "Thanks for listening."}
        raise AssertionError(label)

    monkeypatch.setattr(service, "_client", lambda: object())
    monkeypatch.setattr(service, "_chat_json", chat_json)

    resp = asyncio.run(
        service.generate_script(
            ScriptRequest(title="Example Domain", markdown="Article body")
        )
    )

    assert sorted(calls) == ["intro", "outro", "segment"]
    assert resp.intro == "Welcome to the show."
    assert resp.segments[0].main == "Example Domain is reserved for documentation examples."
    assert resp.outro == "Thanks for listening."
    assert resp.script == (
        "Welcome to the show.\n\n"
        "Here is why this page exists.\n\n"
        "Example Domain is reserved for documentation examples.\n\n"
        "That makes it safe for demos.\n\n"
        "Thanks for listening."
    )


def test_parse_json_object_accepts_code_fence() -> None:
    got = service._parse_json_object('```json\n{"intro":"hello"}\n```', "intro")

    assert got == {"intro": "hello"}


def test_parse_json_object_rejects_malformed_json() -> None:
    with pytest.raises(HTTPException) as exc:
        service._parse_json_object("not json", "intro")

    assert exc.value.status_code == 502


def test_generate_script_rejects_malformed_segment(monkeypatch) -> None:
    async def chat_json(_client, _messages, label: str):
        if label == "intro":
            return {"intro": "Intro"}
        if label == "segment":
            return {"title": "Missing fields"}
        return {"outro": "Outro"}

    monkeypatch.setattr(service, "_client", lambda: object())
    monkeypatch.setattr(service, "_chat_json", chat_json)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service.generate_script(ScriptRequest(title="Example", markdown="Article"))
        )

    assert exc.value.status_code == 502
    assert "malformed segment" in exc.value.detail


def test_generate_script_truncates_article_before_prompting(monkeypatch) -> None:
    seen_user_prompts: list[str] = []

    async def chat_json(_client, messages, label: str):
        seen_user_prompts.append(messages[-1]["content"])
        if label == "intro":
            return {"intro": "Intro"}
        if label == "segment":
            return {
                "title": "Segment",
                "intro": "Segment intro",
                "main": "Segment main",
                "outro": "Segment outro",
            }
        return {"outro": "Outro"}

    monkeypatch.setattr(service, "SCRIPTGEN_MAX_INPUT_CHARS", 10)
    monkeypatch.setattr(service, "_client", lambda: object())
    monkeypatch.setattr(service, "_chat_json", chat_json)

    asyncio.run(
        service.generate_script(
            ScriptRequest(title="Example", markdown="0123456789SHOULD_NOT_APPEAR")
        )
    )

    assert seen_user_prompts
    assert all("0123456789" in prompt for prompt in seen_user_prompts)
    assert all("SHOULD_NOT_APPEAR" not in prompt for prompt in seen_user_prompts)
