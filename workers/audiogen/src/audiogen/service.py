import re
import shutil
import subprocess
from uuid import uuid4

from fastapi import HTTPException
from piratepod_core.logging import get_logger

from .config import AUDIOGEN_OUTPUT_DIR, AUDIOGEN_TIMEOUT, LLAMA_TTS_BIN
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
    cmd = [
        binary,
        "--tts-oute-default",
        "-p",
        req.script,
        "-o",
        str(out_path),
    ]

    log.info(
        "audiogen.start",
        chars=len(req.script),
        title=req.title,
        voice=req.voice,
        output=str(out_path),
    )
    try:
        subprocess.run(
            cmd,
            check=True,
            timeout=AUDIOGEN_TIMEOUT,
            capture_output=True,
            text=True,
        )
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


def _safe_stem(title: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    return stem[:80] or "episode"
