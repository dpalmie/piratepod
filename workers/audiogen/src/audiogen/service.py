import re
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from piratepod_core.logging import get_logger

from .config import (
    AUDIOGEN_CHUNK_MAX_ATTEMPTS,
    AUDIOGEN_MAX_CHARS_PER_CHUNK,
    AUDIOGEN_MIN_SECONDS_PER_WORD,
    AUDIOGEN_MIN_VOICED_RATIO,
    AUDIOGEN_OUTPUT_DIR,
    AUDIOGEN_SILENCE_RMS_THRESHOLD,
    AUDIOGEN_TIMEOUT,
    AUDIOGEN_TTS_MAX_PREDICT,
    AUDIOGEN_TTS_MIN_PREDICT,
    AUDIOGEN_TTS_TOKENS_PER_WORD,
    LLAMA_TTS_BIN,
)
from .schemas import AudioRequest, AudioResponse

log = get_logger(__name__)


@dataclass(frozen=True)
class AudioStats:
    duration_sec: float
    rms: int
    voiced_ratio: float


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
        for index, (chunk, part_path) in enumerate(
            zip(chunks, part_paths, strict=True), start=1
        ):
            _generate_valid_chunk(binary, chunk, part_path, index, len(chunks))
        if len(part_paths) == 1:
            part_paths[0].replace(out_path)
        else:
            _concat_wavs(part_paths, out_path)
    finally:
        for path in part_paths:
            path.unlink(missing_ok=True)


def _generate_valid_chunk(
    binary: str,
    text: str,
    part_path: Path,
    index: int,
    total: int,
) -> None:
    for attempt in range(1, AUDIOGEN_CHUNK_MAX_ATTEMPTS + 1):
        part_path.unlink(missing_ok=True)
        _run_llama_tts(binary, text, part_path)
        try:
            stats = _validate_chunk_audio(part_path, text)
        except HTTPException as e:
            failed_path = _preserve_failed_chunk(part_path, attempt)
            log.warning(
                "audiogen.chunk.invalid",
                chunk=index,
                chunks=total,
                attempt=attempt,
                error=e.detail,
                failed_audio=str(failed_path) if failed_path else "",
                preview=_preview(text),
            )
            if attempt >= AUDIOGEN_CHUNK_MAX_ATTEMPTS:
                raise HTTPException(
                    502,
                    (
                        f"audiogen chunk {index}/{total} failed audio QA after "
                        f"{attempt} attempts: {e.detail}; preview={_preview(text)!r}"
                    ),
                ) from e
            continue

        log.info(
            "audiogen.chunk.ok",
            chunk=index,
            chunks=total,
            attempt=attempt,
            chars=len(text),
            words=len(text.split()),
            duration_sec=round(stats.duration_sec, 2),
            rms=stats.rms,
            voiced_ratio=round(stats.voiced_ratio, 3),
        )
        return


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


def _validate_chunk_audio(path: Path, text: str) -> AudioStats:
    stats = _audio_stats(path)
    words = len(text.split())
    min_duration = max(0.5, words * AUDIOGEN_MIN_SECONDS_PER_WORD)
    if stats.duration_sec < min_duration:
        raise HTTPException(
            502,
            (
                "chunk audio too short "
                f"({stats.duration_sec:.2f}s for {words} words; "
                f"min {min_duration:.2f}s)"
            ),
        )
    if stats.rms < AUDIOGEN_SILENCE_RMS_THRESHOLD:
        raise HTTPException(502, f"chunk audio is silent (rms={stats.rms})")
    if stats.duration_sec >= 2 and stats.voiced_ratio < AUDIOGEN_MIN_VOICED_RATIO:
        raise HTTPException(
            502,
            (
                "chunk audio is mostly silent "
                f"(voiced_ratio={stats.voiced_ratio:.3f}, rms={stats.rms})"
            ),
        )
    return stats


def _audio_stats(path: Path) -> AudioStats:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        framerate = wav.getframerate()
        sample_width = wav.getsampwidth()
        channels = wav.getnchannels()
        raw = wav.readframes(frames)

    duration = frames / framerate if framerate > 0 else 0
    if not raw or sample_width <= 0 or channels <= 0:
        return AudioStats(duration_sec=duration, rms=0, voiced_ratio=0)

    samples = _pcm_samples(raw, sample_width)
    rms = _rms(samples)
    window_size = max(1, int(framerate * channels * 0.25))
    windows = [
        samples[offset : offset + window_size]
        for offset in range(0, len(samples), window_size)
    ]
    voiced = sum(1 for window in windows if _rms(window) >= AUDIOGEN_SILENCE_RMS_THRESHOLD)
    voiced_ratio = voiced / len(windows) if windows else 0
    return AudioStats(duration_sec=duration, rms=rms, voiced_ratio=voiced_ratio)


def _pcm_samples(raw: bytes, sample_width: int) -> list[int]:
    if sample_width == 1:
        return [sample - 128 for sample in raw]
    if sample_width == 2:
        return [
            int.from_bytes(raw[i : i + 2], "little", signed=True)
            for i in range(0, len(raw) - 1, 2)
        ]
    if sample_width == 4:
        return [
            int.from_bytes(raw[i : i + 4], "little", signed=True) >> 16
            for i in range(0, len(raw) - 3, 4)
        ]
    raise HTTPException(502, f"unsupported wav sample width: {sample_width}")


def _rms(samples: list[int]) -> int:
    if not samples:
        return 0
    return int((sum(sample * sample for sample in samples) / len(samples)) ** 0.5)


def _preserve_failed_chunk(path: Path, attempt: int) -> Path | None:
    if not path.exists():
        return None
    failed_path = path.with_name(f"failed-{path.stem}-attempt-{attempt}{path.suffix}")
    path.replace(failed_path)
    return failed_path


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
    expected_format = None
    with wave.open(str(out_path), "wb") as out:
        for part_path in part_paths:
            with wave.open(str(part_path), "rb") as part:
                current_format = _wav_format(part)
                if expected_format is None:
                    expected_format = current_format
                    out.setnchannels(part.getnchannels())
                    out.setsampwidth(part.getsampwidth())
                    out.setframerate(part.getframerate())
                    out.setcomptype(part.getcomptype(), part.getcompname())
                elif current_format != expected_format:
                    raise HTTPException(502, "llama-tts produced incompatible wav chunks")
                out.writeframes(part.readframes(part.getnframes()))


def _wav_format(wav: wave.Wave_read) -> tuple[int, int, int, str, str]:
    return (
        wav.getnchannels(),
        wav.getsampwidth(),
        wav.getframerate(),
        wav.getcomptype(),
        wav.getcompname(),
    )


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


def _preview(text: str) -> str:
    return " ".join(text.split())[:160]


def _safe_stem(title: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    return stem[:80] or "episode"
