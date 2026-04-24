from fastapi import APIRouter

from .schemas import ScriptRequest, ScriptResponse
from .service import generate_script

router = APIRouter()


@router.post("/scriptgen/script", response_model=ScriptResponse)
async def scriptgen_script(req: ScriptRequest) -> ScriptResponse:
    return generate_script(req)
