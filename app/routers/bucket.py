from __future__ import annotations

from fastapi import APIRouter

from app.models.request import ListRequest
from app.models.response import ListResponse
from app.services.list_service import ListService


router = APIRouter(prefix="/api/v1/bucket", tags=["bucket"])


@router.post("/list", response_model=ListResponse)
async def list_bucket_files(request: ListRequest) -> ListResponse:
    """Lista archivos disponibles en el bucket origen según los filtros del usuario."""

    service = ListService()
    return await service.execute(request)


__all__ = ["router"]
