from __future__ import annotations

import logging

from app.models.common import get_extensions_for_asset_types
from app.models.request import ListRequest
from app.models.response import ListResponse
from app.providers.factory import get_provider


logger = logging.getLogger(__name__)


class ListService:
    """Orquesta el flujo de listado de archivos desde un bucket externo."""

    async def execute(self, request: ListRequest) -> ListResponse:
        extensions = get_extensions_for_asset_types(request.asset_types)

        provider = get_provider(request)
        await provider.validate_credentials()

        files = await provider.list_files(
            folder_id=request.folder_id,
            extensions=extensions,
            max_depth=request.max_depth,
        )

        logger.debug(
            "ListService.execute completed: source=%s folder_id=%s total_files=%s",
            request.source.value,
            request.folder_id,
            len(files),
        )

        return ListResponse(
            source=request.source.value,
            folder_id=request.folder_id,
            total_files=len(files),
            asset_types_requested=request.asset_types,
            extensions_searched=extensions,
            files=files,
        )


__all__ = ["ListService"]
