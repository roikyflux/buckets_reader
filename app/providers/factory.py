from __future__ import annotations

from typing import Type

from app.exceptions import UnsupportedProviderError
from app.models.common import SourceType
from app.models.request import ListRequest
from app.providers.base import BucketProvider


def get_provider(request: ListRequest) -> BucketProvider:
    from app.providers.google_drive.provider import GoogleDriveProvider

    provider_registry: dict[SourceType, Type[BucketProvider]] = {
        SourceType.GOOGLE_DRIVE: GoogleDriveProvider,
        # SourceType.AWS_S3: S3Provider,
        # SourceType.AZURE_BLOB: AzureBlobProvider,
        # SourceType.DROPBOX: DropboxProvider,
    }

    provider_class = provider_registry.get(request.source)
    if provider_class is None:
        raise UnsupportedProviderError(f"El provider '{request.source}' no está soportado en esta versión.")

    return provider_class(credentials=request.credentials)


__all__ = ["get_provider"]
