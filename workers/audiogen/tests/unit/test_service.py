import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

import audiogen.service as service
from audiogen.schemas import AudioRequest


def test_generate_audio_runs_llama_tts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "LLAMA_TTS_BIN", "llama-tts")
    monkeypatch.setattr(service, "AUDIOGEN_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(service.shutil, "which", lambda _bin: "/usr/local/bin/llama-tts")
    seen_cmds: list[list[str]] = []
    seen_prompts: list[str] = []

    def run(cmd, **kwargs):
        seen_cmds.append(cmd)
        prompt_path = Path(cmd[cmd.index("-f") + 1])
        seen_prompts.append(prompt_path.read_text())
        Path(cmd[-1]).write_bytes(b"wav")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(service.subprocess, "run", run)

    resp = service.generate_audio(
        AudioRequest(title="Example Domain", script="Hello from PiratePod.")
    )

    assert resp.audio_format == "wav"
    assert resp.audio_path.endswith(".wav")
    assert Path(resp.audio_path).exists()
    assert "--tts-use-guide-tokens" in seen_cmds[0]
    assert "--predict" in seen_cmds[0]
    assert "-p" not in seen_cmds[0]
    assert seen_prompts == ["Hello from PiratePod."]


def test_generate_audio_returns_503_when_llama_tts_missing(monkeypatch) -> None:
    monkeypatch.setattr(service.shutil, "which", lambda _bin: None)

    with pytest.raises(HTTPException) as exc:
        service.generate_audio(AudioRequest(title="Example", script="Hello"))

    assert exc.value.status_code == 503
    assert "brew install llama.cpp" in exc.value.detail


def test_generate_audio_returns_504_on_timeout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "AUDIOGEN_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(service.shutil, "which", lambda _bin: "/usr/local/bin/llama-tts")

    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, timeout=1)

    monkeypatch.setattr(service.subprocess, "run", run)

    with pytest.raises(HTTPException) as exc:
        service.generate_audio(AudioRequest(title="Example", script="Hello"))

    assert exc.value.status_code == 504


def test_generate_audio_returns_502_on_llama_failure(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(service, "AUDIOGEN_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(service.shutil, "which", lambda _bin: "/usr/local/bin/llama-tts")

    def run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, stderr="boom")

    monkeypatch.setattr(service.subprocess, "run", run)

    with pytest.raises(HTTPException) as exc:
        service.generate_audio(AudioRequest(title="Example", script="Hello"))

    assert exc.value.status_code == 502


def test_safe_stem_falls_back_for_blank_title() -> None:
    assert service._safe_stem("   ") == "episode"


def test_script_chunks_preserve_order_and_split_long_text() -> None:
    chunks = service._script_chunks(
        (
            "First sentence stays with enough room. "
            "Second sentence is intentionally long enough to force a split. "
            "Third sentence follows."
        ),
        80,
    )

    assert chunks == [
        "First sentence stays with enough room.",
        "Second sentence is intentionally long enough to force a split.",
        "Third sentence follows.",
    ]


def test_predict_tokens_scales_with_words(monkeypatch) -> None:
    monkeypatch.setattr(service, "AUDIOGEN_TTS_MIN_PREDICT", 100)
    monkeypatch.setattr(service, "AUDIOGEN_TTS_MAX_PREDICT", 1000)
    monkeypatch.setattr(service, "AUDIOGEN_TTS_TOKENS_PER_WORD", 10)

    assert service._predict_tokens("one two three") == 100
    assert service._predict_tokens(" ".join(["word"] * 50)) == 500
    assert service._predict_tokens(" ".join(["word"] * 200)) == 1000
