from pydantic import BaseModel


class ScriptRequest(BaseModel):
    markdown: str
    title: str | None = None


class ScriptResponse(BaseModel):
    script: str
