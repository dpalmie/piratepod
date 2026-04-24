from fastapi import APIRouter

from .schemas import GenerateRequest, GenerateResponse
from .service import generate_podcast

router = APIRouter()


@router.post("/orchestrate/generate", response_model=GenerateResponse)
async def orchestrate_generate(req: GenerateRequest) -> GenerateResponse:
    return await generate_podcast(req)
