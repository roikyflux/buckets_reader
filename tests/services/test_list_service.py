from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.exceptions import FolderNotFoundError, InvalidCredentialsError, ProviderConnectionError
from app.models.common import AssetType, SourceType
from app.models.request import ListRequest
from app.models.response import FileInfo
from app.providers.base import BucketProvider
from app.services.list_service import ListService


class MockProvider(BucketProvider):
    """Provider falso para tests del servicio."""

    def __init__(self, files_to_return=None, error_to_raise=None):
        self.files_to_return = files_to_return or []
        self.error_to_raise = error_to_raise
        self.validate_called = False
        self.list_files_called = False
        self.last_list_files_args: dict[str, object] | None = None

    async def validate_credentials(self):  # type: ignore[override]
        self.validate_called = True
        if self.error_to_raise:
            raise self.error_to_raise

    async def list_files(  # type: ignore[override]
        self,
        folder_id,
        extensions,
        max_depth=None,
        *,
        current_depth=0,
        current_path="",
    ):
        self.list_files_called = True
        self.last_list_files_args = {
            "folder_id": folder_id,
            "extensions": extensions,
            "max_depth": max_depth,
            "current_depth": current_depth,
            "current_path": current_path,
        }
        if self.error_to_raise:
            raise self.error_to_raise
        return self.files_to_return

    async def get_file_metadata(self, file_id):  # type: ignore[override]
        return self.files_to_return[0] if self.files_to_return else None


@pytest.fixture
def list_request(valid_google_drive_credentials):
    return ListRequest(
        source=SourceType.GOOGLE_DRIVE,
        credentials=valid_google_drive_credentials,
        folder_id="folder",
        asset_types=[AssetType.DATASET],
        max_depth=None,
    )


def _build_file_info(file_id: str = "1") -> FileInfo:
    return FileInfo(
        id=file_id,
        name="dataset.csv",
        extension="csv",
        asset_type=AssetType.DATASET,
        mime_type="text/csv",
        size_bytes=1024,
        modified_at=datetime.now(timezone.utc),
        preview_url="https://example.com",
        folder_path="",
        source=SourceType.GOOGLE_DRIVE.value,
    )


@pytest.mark.asyncio
async def test_retorna_list_response_con_archivos_encontrados(list_request, mocker):
    files = [_build_file_info()]
    provider = MockProvider(files_to_return=files)
    mocker.patch("app.services.list_service.get_provider", return_value=provider)

    service = ListService()
    response = await service.execute(list_request)

    assert response.files == files
    assert response.total_files == 1
    assert response.source == list_request.source.value


@pytest.mark.asyncio
async def test_llama_validate_credentials_antes_de_list_files(list_request, mocker):
    provider = MockProvider(files_to_return=[_build_file_info()])
    mocker.patch("app.services.list_service.get_provider", return_value=provider)

    service = ListService()
    await service.execute(list_request)

    assert provider.validate_called is True
    assert provider.list_files_called is True


@pytest.mark.asyncio
async def test_expande_asset_types_a_extensiones_correctas(list_request, mocker):
    provider = MockProvider(files_to_return=[_build_file_info()])
    mocker.patch("app.services.list_service.get_provider", return_value=provider)

    service = ListService()
    await service.execute(list_request)

    assert provider.last_list_files_args is not None
    assert provider.last_list_files_args["extensions"] == ["csv", "xlsx", "parquet"]


@pytest.mark.asyncio
async def test_total_files_coincide_con_len_files(list_request, mocker):
    files = [_build_file_info("1"), _build_file_info("2")]
    provider = MockProvider(files_to_return=files)
    mocker.patch("app.services.list_service.get_provider", return_value=provider)

    service = ListService()
    response = await service.execute(list_request)

    assert response.total_files == len(files)


@pytest.mark.asyncio
async def test_propaga_invalid_credentials_error(list_request, mocker):
    provider = MockProvider(error_to_raise=InvalidCredentialsError())
    mocker.patch("app.services.list_service.get_provider", return_value=provider)

    service = ListService()

    with pytest.raises(InvalidCredentialsError):
        await service.execute(list_request)


@pytest.mark.asyncio
async def test_propaga_folder_not_found_error(list_request, mocker):
    provider = MockProvider(error_to_raise=FolderNotFoundError())
    mocker.patch("app.services.list_service.get_provider", return_value=provider)

    service = ListService()

    with pytest.raises(FolderNotFoundError):
        await service.execute(list_request)


@pytest.mark.asyncio
async def test_propaga_provider_connection_error(list_request, mocker):
    provider = MockProvider(error_to_raise=ProviderConnectionError())
    mocker.patch("app.services.list_service.get_provider", return_value=provider)

    service = ListService()

    with pytest.raises(ProviderConnectionError):
        await service.execute(list_request)


@pytest.mark.asyncio
async def test_list_response_incluye_extensions_searched(list_request, mocker):
    provider = MockProvider(files_to_return=[_build_file_info()])
    mocker.patch("app.services.list_service.get_provider", return_value=provider)

    service = ListService()
    response = await service.execute(list_request)

    assert response.extensions_searched == ["csv", "xlsx", "parquet"]


@pytest.mark.asyncio
async def test_pasa_max_depth_al_provider(list_request, mocker):
    provider = MockProvider(files_to_return=[_build_file_info()])
    mocker.patch("app.services.list_service.get_provider", return_value=provider)

    request_with_depth = list_request.model_copy(update={"max_depth": 3})

    service = ListService()
    await service.execute(request_with_depth)

    assert provider.last_list_files_args is not None
    assert provider.last_list_files_args["max_depth"] == 3
