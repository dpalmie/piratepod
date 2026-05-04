import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from piratepod_core.logging import get_logger

from .config import (
    AUDIOGEN_MAX_CHARS_PER_CHUNK,
    AUDIOGEN_OUTPUT_DIR,
    AUDIOGEN_TIMEOUT,
    AUDIOGEN_TTS_MAX_PREDICT,
    AUDIOGEN_TTS_MIN_PREDICT,
    AUDIOGEN_TTS_TOKENS_PER_WORD,
    LLAMA_TTS_BIN,
)
from .schemas import AudioRequest, AudioResponse

log = get_logger(__name__)


def generate_audio(req: AudioRequest) -> AudioResponse:
    binary = shutil.which(LLAMA_TTS_BIN)
    if binary is None:
        raise HTTPException(
            503,
            "llama-tts not found. Install llama.cpp with: brew install llama.cpp",
        )

    output_dir = AUDIOGEN_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{_safe_stem(req.title)}-{uuid4().hex[:8]}.wav"
    chunks = _script_chunks(req.script, AUDIOGEN_MAX_CHARS_PER_CHUNK)

    log.info(
        "audiogen.start",
        chars=len(req.script),
        chunks=len(chunks),
        title=req.title,
        voice=req.voice,
        output=str(out_path),
    )
    try:
        _generate_chunks(binary, chunks, out_path)
    except subprocess.TimeoutExpired as e:
        raise HTTPException(504, "llama-tts timed out") from e
    except subprocess.CalledProcessError as e:
        log.error(
            "audiogen.failed",
            returncode=e.returncode,
            stderr_chars=len(e.stderr or ""),
        )
        raise HTTPException(502, "llama-tts failed") from e

    if not out_path.exists():
        raise HTTPException(502, "llama-tts did not write output audio")

    log.info("audiogen.done", output=str(out_path))
    return AudioResponse(audio_path=str(out_path), audio_format="wav")


def _generate_chunks(binary: str, chunks: list[str], out_path: Path) -> None:
    part_paths = [
        out_path.with_name(f"{out_path.stem}.part-{index:03d}.wav")
        for index in range(1, len(chunks) + 1)
    ]
    try:
        for chunk, part_path in zip(chunks, part_paths, strict=True):
            _run_llama_tts(binary, chunk, part_path)
        if len(part_paths) == 1:
            part_paths[0].replace(out_path)
        else:
            _concat_wavs(part_paths, out_path)
    finally:
        for path in part_paths:
            path.unlink(missing_ok=True)


def _run_llama_tts(binary: str, text: str, out_path: Path) -> None:
    prompt_path = _write_prompt_file(text)
    try:
        subprocess.run(
            [
                binary,
                "--tts-oute-default",
                "--tts-use-guide-tokens",
                "--predict",
                str(_predict_tokens(text)),
                "-f",
                str(prompt_path),
                "-o",
                str(out_path),
            ],
            check=True,
            timeout=AUDIOGEN_TIMEOUT,
            capture_output=True,
            text=True,
        )
    finally:
        prompt_path.unlink(missing_ok=True)


def _write_prompt_file(text: str) -> Path:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix="piratepod-tts-",
        suffix=".txt",
        delete=False,
    ) as f:
        f.write(text)
        return Path(f.name)


def _concat_wavs(part_paths: list[Path], out_path: Path) -> None:
    params = None
    with wave.open(str(out_path), "wb") as out:
        for part_path in part_paths:
            with wave.open(str(part_path), "rb") as part:
                if params is None:
                    params = part.getparams()
                    out.setparams(params)
                elif part.getparams() != params:
                    raise HTTPException(502, "llama-tts produced incompatible wav chunks")
                out.writeframes(part.readframes(part.getnframes()))


def _script_chunks(script: str, max_chars: int) -> list[str]:
    max_chars = max(max_chars, 80)
    chunks: list[str] = []
    current = ""
    for unit in _script_units(script):
        if len(unit) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_unit(unit, max_chars))
            continue
        candidate = f"{current} {unit}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = unit
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [script.strip()]


def _script_units(script: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", script) if p.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        units.extend(
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
            if sentence.strip()
        )
    return units


def _split_long_unit(unit: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for word in unit.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _predict_tokens(text: str) -> int:
    words = len(text.split())
    estimate = max(AUDIOGEN_TTS_MIN_PREDICT, words * AUDIOGEN_TTS_TOKENS_PER_WORD)
    return min(estimate, AUDIOGEN_TTS_MAX_PREDICT)


def _safe_stem(title: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    return stem[:80] or "episode"
