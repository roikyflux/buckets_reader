from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.common import AssetType, SourceType
from app.models.request import GoogleDriveCredentials, ListRequest
from app.models.response import FileInfo


@pytest.fixture
def valid_google_drive_credentials() -> GoogleDriveCredentials:
    """Credenciales válidas de prueba para GoogleDriveCredentials."""

    return GoogleDriveCredentials(access_token="ya29.test_token_ok")


@pytest.fixture
def valid_list_request(valid_google_drive_credentials: GoogleDriveCredentials) -> ListRequest:
    """ListRequest válido con source=google_drive y asset_types=['dataset']."""

    return ListRequest(
        source=SourceType.GOOGLE_DRIVE,
        credentials=valid_google_drive_credentials,
        folder_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
        asset_types=[AssetType.DATASET],
        max_depth=None,
    )


@pytest.fixture
def sample_file_info() -> FileInfo:
    """FileInfo de ejemplo para usar en tests de respuesta."""

    return FileInfo(
        id="abc123",
        name="datos.csv",
        extension="csv",
        asset_type=AssetType.DATASET,
        mime_type="text/csv",
        size_bytes=1024,
        modified_at=datetime.now(timezone.utc),
        preview_url=None,
        folder_path="",
        source=SourceType.GOOGLE_DRIVE.value,
    )
