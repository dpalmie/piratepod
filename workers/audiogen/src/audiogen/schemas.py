from pydantic import BaseModel


class AudioRequest(BaseModel):
    script: str
    voice: str | None = None


class AudioResponse(BaseModel):
    audio_path: str
