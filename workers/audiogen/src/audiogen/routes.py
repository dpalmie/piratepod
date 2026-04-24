from fastapi import APIRouter

from .schemas import AudioRequest, AudioResponse
from .service import generate_audio

router = APIRouter()


@router.post("/audiogen/audio", response_model=AudioResponse)
async def audiogen_audio(req: AudioRequest) -> AudioResponse:
    return generate_audio(req)
