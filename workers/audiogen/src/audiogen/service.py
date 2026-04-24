from piratepod_core.logging import get_logger

from .config import SILENCE_PATH
from .schemas import AudioRequest, AudioResponse

log = get_logger(__name__)


def generate_audio(req: AudioRequest) -> AudioResponse:
    log.info("audiogen.stub", chars=len(req.script), voice=req.voice)
    return AudioResponse(audio_path=str(SILENCE_PATH))
