import os
from pathlib import Path

AUDIOGEN_OUTPUT_DIR = Path(os.getenv("AUDIOGEN_OUTPUT_DIR", ".piratepod/audio"))
AUDIOGEN_TIMEOUT = float(os.getenv("AUDIOGEN_TIMEOUT", "600"))
LLAMA_TTS_BIN = os.getenv("LLAMA_TTS_BIN", "llama-tts")
