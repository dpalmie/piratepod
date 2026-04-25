from pydantic import BaseModel, Field


class ScriptSource(BaseModel):
    title: str
    url: str
    markdown: str


class ScriptRequest(BaseModel):
    title: str
    sources: list[ScriptSource] = Field(min_length=1)


class StorySegment(BaseModel):
    title: str
    intro: str
    main: str
    outro: str


class ScriptResponse(BaseModel):
    intro: str
    segments: list[StorySegment]
    outro: str
    script: str
