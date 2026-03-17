from __future__ import annotations

from app.models.request import GoogleDriveCredentials
from app.models.response import FileInfo
from app.providers.base import BucketProvider


class GoogleDriveProvider(BucketProvider):
    """Implementación de BucketProvider para Google Drive (estructura sin lógica)."""

    def __init__(self, credentials: GoogleDriveCredentials) -> None:
        self._credentials = credentials

    async def validate_credentials(self) -> None:  # pragma: no cover - Bloque 4 implementará
        raise NotImplementedError

    async def list_files(
        self,
        folder_id: str,
        extensions: list[str],
        max_depth: int | None = None,
        *,
        current_depth: int = 0,
        current_path: str = "",
    ) -> list[FileInfo]:  # pragma: no cover
        raise NotImplementedError

    async def get_file_metadata(self, file_id: str) -> FileInfo:  # pragma: no cover
        raise NotImplementedError


__all__ = ["GoogleDriveProvider"]
