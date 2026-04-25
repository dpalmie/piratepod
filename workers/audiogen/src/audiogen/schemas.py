from pydantic import BaseModel


class AudioRequest(BaseModel):
    script: str
    title: str
    voice: str | None = None


class AudioResponse(BaseModel):
    audio_path: str
    audio_format: str = "wav"
