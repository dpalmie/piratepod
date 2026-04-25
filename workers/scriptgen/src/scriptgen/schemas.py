from pydantic import BaseModel


class ScriptRequest(BaseModel):
    markdown: str
    title: str


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
