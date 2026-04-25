import asyncio
import json
from typing import Any, TypeVar

from fastapi import HTTPException
from openai import AsyncOpenAI, OpenAIError
from piratepod_core.logging import get_logger
from pydantic import BaseModel, ValidationError

from .config import (
    SCRIPTGEN_LLM_API_KEY,
    SCRIPTGEN_LLM_BASE_URL,
    SCRIPTGEN_LLM_MAX_TOKENS,
    SCRIPTGEN_LLM_MODEL,
    SCRIPTGEN_LLM_TEMPERATURE,
    SCRIPTGEN_LLM_TIMEOUT,
    SCRIPTGEN_MAX_INPUT_CHARS,
)
from .prompts import (
    SYSTEM_PROMPT,
    intro_prompt,
    outro_prompt,
    segment_prompt,
    source_context,
    sources_context,
)
from .schemas import ScriptRequest, ScriptResponse, ScriptSource, StorySegment

log = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


async def generate_script(req: ScriptRequest) -> ScriptResponse:
    sources = [_truncate_source(source) for source in req.sources]
    all_sources = sources_context(
        [(source.title, source.url, source.markdown) for source in sources]
    )
    client = _client()

    log.info(
        "scriptgen.start",
        title=req.title,
        source_count=len(req.sources),
        input_chars=sum(len(source.markdown) for source in req.sources),
        prompt_chars=sum(len(source.markdown) for source in sources),
    )
    results = await asyncio.gather(
        _generate_intro(client, req.title, all_sources),
        *(
            _generate_segment(client, req.title, source, index)
            for index, source in enumerate(sources, start=1)
        ),
        _generate_outro(client, req.title, all_sources),
    )
    intro = results[0]
    segments = list(results[1:-1])
    outro = results[-1]
    script = _compose_script(intro, segments, outro)
    log.info("scriptgen.done", title=req.title, script_chars=len(script))

    return ScriptResponse(
        intro=intro,
        segments=segments,
        outro=outro,
        script=script,
    )


class IntroOutput(BaseModel):
    intro: str


class OutroOutput(BaseModel):
    outro: str


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=SCRIPTGEN_LLM_BASE_URL,
        api_key=SCRIPTGEN_LLM_API_KEY,
        timeout=SCRIPTGEN_LLM_TIMEOUT,
    )


async def _generate_intro(client: AsyncOpenAI, title: str, sources: str) -> str:
    data = await _chat_json(
        client,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": intro_prompt(title, sources)},
        ],
        "intro",
    )
    return _validate(IntroOutput, data, "intro").intro.strip()


async def _generate_segment(
    client: AsyncOpenAI, title: str, source: ScriptSource, index: int
) -> StorySegment:
    context = source_context(index, source.title, source.url, source.markdown)
    data = await _chat_json(
        client,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": segment_prompt(title, context)},
        ],
        "segment",
    )
    return _validate(StorySegment, data, "segment")


async def _generate_outro(client: AsyncOpenAI, title: str, sources: str) -> str:
    data = await _chat_json(
        client,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": outro_prompt(title, sources)},
        ],
        "outro",
    )
    return _validate(OutroOutput, data, "outro").outro.strip()


async def _chat_json(
    client: AsyncOpenAI, messages: list[dict[str, str]], label: str
) -> dict[str, Any]:
    try:
        response = await client.chat.completions.create(
            model=SCRIPTGEN_LLM_MODEL,
            messages=messages,
            max_tokens=SCRIPTGEN_LLM_MAX_TOKENS,
            temperature=SCRIPTGEN_LLM_TEMPERATURE,
        )
    except OpenAIError as e:
        raise HTTPException(502, f"scriptgen llm {label} call failed") from e

    content = response.choices[0].message.content
    if not content:
        raise HTTPException(502, f"scriptgen llm returned empty {label}")
    return _parse_json_object(content, label)


def _parse_json_object(content: str, label: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise HTTPException(502, f"scriptgen llm returned invalid {label} json")
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            raise HTTPException(502, f"scriptgen llm returned invalid {label} json") from e

    if not isinstance(parsed, dict):
        raise HTTPException(502, f"scriptgen llm returned non-object {label} json")
    return parsed


def _validate(model: type[T], data: dict[str, Any], label: str) -> T:
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise HTTPException(502, f"scriptgen llm returned malformed {label}") from e


def _compose_script(intro: str, segments: list[StorySegment], outro: str) -> str:
    parts = [intro]
    for segment in segments:
        parts.extend([segment.intro, segment.main, segment.outro])
    parts.append(outro)
    return "\n\n".join(part.strip() for part in parts if part.strip())


def _truncate(markdown: str) -> str:
    return markdown[:SCRIPTGEN_MAX_INPUT_CHARS]


def _truncate_source(source: ScriptSource) -> ScriptSource:
    return ScriptSource(
        title=source.title,
        url=source.url,
        markdown=_truncate(source.markdown),
    )
