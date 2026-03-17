from __future__ import annotations

from datetime import timezone
from unittest import mock

import pytest
from googleapiclient.errors import HttpError

from app.exceptions import FolderNotFoundError, InvalidCredentialsError, ProviderConnectionError, ProviderRateLimitError
from app.models.common import AssetType
from app.providers.google_drive.provider import GOOGLE_DRIVE_FOLDER_MIME, GoogleDriveProvider


def _make_http_error(status: int) -> HttpError:
    response = mock.Mock(status=status, reason="error")
    return HttpError(response, b"error")


@pytest.fixture
def provider(valid_google_drive_credentials):
    return GoogleDriveProvider(credentials=valid_google_drive_credentials)


@pytest.fixture
def provider_con_servicio(provider, mocker):
    service = mocker.MagicMock()
    files_resource = mocker.MagicMock()
    service.files.return_value = files_resource
    provider._service = service  # type: ignore[attr-defined]
    return provider


@pytest.fixture
def drive_timestamp() -> str:
    return "2025-03-10T14:30:00.000Z"


@pytest.mark.asyncio
async def test_construye_servicio_correctamente(provider, mocker):
    credentials_cls = mocker.patch("app.providers.google_drive.provider.Credentials", return_value=mocker.MagicMock())
    service_mock = mocker.MagicMock()
    mocker.patch("app.providers.google_drive.provider.build", return_value=service_mock)
    execute_async = mocker.patch.object(
        provider,
        "_execute_async",
        new=mocker.AsyncMock(side_effect=lambda func: func()),
    )

    await provider.validate_credentials()

    credentials_cls.assert_called_once()
    execute_async.assert_awaited_once()
    assert getattr(provider, "_service") is service_mock


@pytest.mark.asyncio
async def test_lanza_provider_connection_error_si_falla_build(provider, mocker):
    mocker.patch("app.providers.google_drive.provider.Credentials", return_value=mocker.MagicMock())
    mocker.patch("app.providers.google_drive.provider.build")
    mocker.patch.object(
        provider,
        "_execute_async",
        new=mocker.AsyncMock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(ProviderConnectionError):
        await provider.validate_credentials()


@pytest.mark.asyncio
async def test_retorna_lista_vacia_si_no_hay_coincidencias(provider_con_servicio, mocker):
    provider = provider_con_servicio
    request = mocker.MagicMock()
    request.execute = mocker.Mock()
    provider._service.files.return_value.list.return_value = request  # type: ignore[attr-defined]
    execute_mock = mocker.patch.object(
        provider,
        "_execute_with_retry",
        new=mocker.AsyncMock(return_value={"files": []}),
    )

    result = await provider.list_files("folder", ["csv"])

    assert result == []
    execute_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_filtra_archivos_por_extension(provider_con_servicio, mocker, drive_timestamp):
    provider = provider_con_servicio
    request = mocker.MagicMock()
    request.execute = mocker.Mock()
    provider._service.files.return_value.list.return_value = request  # type: ignore[attr-defined]
    response = {
        "files": [
            {
                "id": "1",
                "name": "dataset.csv",
                "mimeType": "text/csv",
                "size": "1024",
                "modifiedTime": drive_timestamp,
                "webViewLink": "https://example.com",
            },
            {
                "id": "2",
                "name": "song.mp3",
                "mimeType": "audio/mpeg",
                "size": "2048",
                "modifiedTime": drive_timestamp,
            },
        ]
    }
    mocker.patch.object(provider, "_execute_with_retry", new=mocker.AsyncMock(return_value=response))

    files = await provider.list_files("folder", ["csv"])

    assert len(files) == 1
    assert files[0].extension == "csv"
    assert files[0].asset_type == AssetType.DATASET


@pytest.mark.asyncio
async def test_recursion_en_subcarpetas(provider_con_servicio, mocker, drive_timestamp):
    provider = provider_con_servicio
    request_root = mocker.MagicMock()
    request_root.execute = mocker.Mock()
    request_child = mocker.MagicMock()
    request_child.execute = mocker.Mock()
    provider._service.files.return_value.list.side_effect = [request_root, request_child]  # type: ignore[attr-defined]

    response_root = {
        "files": [
            {
                "id": "folder-2",
                "name": "Sub",
                "mimeType": GOOGLE_DRIVE_FOLDER_MIME,
            },
            {
                "id": "root-file",
                "name": "root.csv",
                "mimeType": "text/csv",
                "size": "10",
                "modifiedTime": drive_timestamp,
            },
        ]
    }
    response_child = {
        "files": [
            {
                "id": "child-file",
                "name": "child.csv",
                "mimeType": "text/csv",
                "size": "20",
                "modifiedTime": drive_timestamp,
            }
        ]
    }
    mocker.patch.object(
        provider,
        "_execute_with_retry",
        new=mocker.AsyncMock(side_effect=[response_root, response_child]),
    )

    files = await provider.list_files("folder", ["csv"])

    assert {file.id for file in files} == {"root-file", "child-file"}
    assert any(file.folder_path == "Sub" for file in files if file.id == "child-file")


@pytest.mark.asyncio
async def test_respeta_max_depth(provider_con_servicio, mocker, drive_timestamp):
    provider = provider_con_servicio
    request_root = mocker.MagicMock()
    request_root.execute = mocker.Mock()
    provider._service.files.return_value.list.return_value = request_root  # type: ignore[attr-defined]

    response_root = {
        "files": [
            {
                "id": "folder-2",
                "name": "Sub",
                "mimeType": GOOGLE_DRIVE_FOLDER_MIME,
            }
        ]
    }

    execute_mock = mocker.patch.object(
        provider,
        "_execute_with_retry",
        new=mocker.AsyncMock(return_value=response_root),
    )

    files = await provider.list_files("folder", ["csv"], max_depth=1)

    assert files == []
    execute_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_maneja_paginacion_interna(provider_con_servicio, mocker, drive_timestamp):
    provider = provider_con_servicio
    request_page_one = mocker.MagicMock()
    request_page_one.execute = mocker.Mock()
    request_page_two = mocker.MagicMock()
    request_page_two.execute = mocker.Mock()
    provider._service.files.return_value.list.side_effect = [request_page_one, request_page_two]  # type: ignore[attr-defined]

    page_one = {
        "files": [
            {
                "id": "file-1",
                "name": "a.csv",
                "mimeType": "text/csv",
                "size": "10",
                "modifiedTime": drive_timestamp,
            }
        ],
        "nextPageToken": "token",
    }
    page_two = {
        "files": [
            {
                "id": "file-2",
                "name": "b.csv",
                "mimeType": "text/csv",
                "size": "20",
                "modifiedTime": drive_timestamp,
            }
        ],
    }

    execute_mock = mocker.patch.object(
        provider,
        "_execute_with_retry",
        new=mocker.AsyncMock(side_effect=[page_one, page_two]),
    )

    files = await provider.list_files("folder", ["csv"])

    assert len(files) == 2
    execute_mock.assert_awaited()


@pytest.mark.asyncio
async def test_lanza_invalid_credentials_error_en_401(provider_con_servicio, mocker):
    provider = provider_con_servicio
    request = mocker.MagicMock()
    request.execute = mocker.Mock()
    provider._service.files.return_value.list.return_value = request  # type: ignore[attr-defined]
    mocker.patch.object(
        provider,
        "_execute_with_retry",
        new=mocker.AsyncMock(side_effect=_make_http_error(401)),
    )

    with pytest.raises(InvalidCredentialsError):
        await provider.list_files("folder", ["csv"])


@pytest.mark.asyncio
async def test_lanza_folder_not_found_en_404(provider_con_servicio, mocker):
    provider = provider_con_servicio
    request = mocker.MagicMock()
    request.execute = mocker.Mock()
    provider._service.files.return_value.list.return_value = request  # type: ignore[attr-defined]
    mocker.patch.object(
        provider,
        "_execute_with_retry",
        new=mocker.AsyncMock(side_effect=_make_http_error(404)),
    )

    with pytest.raises(FolderNotFoundError):
        await provider.list_files("folder", ["csv"])


@pytest.mark.asyncio
async def test_lanza_provider_rate_limit_en_429(provider_con_servicio, mocker):
    provider = provider_con_servicio
    request = mocker.MagicMock()
    request.execute = mocker.Mock()
    provider._service.files.return_value.list.return_value = request  # type: ignore[attr-defined]
    mocker.patch.object(
        provider,
        "_execute_with_retry",
        new=mocker.AsyncMock(side_effect=_make_http_error(429)),
    )

    with pytest.raises(ProviderRateLimitError):
        await provider.list_files("folder", ["csv"])


@pytest.mark.asyncio
async def test_construye_folder_path_correctamente(provider_con_servicio, mocker, drive_timestamp):
    provider = provider_con_servicio
    request_root = mocker.MagicMock()
    request_root.execute = mocker.Mock()
    request_child = mocker.MagicMock()
    request_child.execute = mocker.Mock()
    provider._service.files.return_value.list.side_effect = [request_root, request_child]  # type: ignore[attr-defined]

    response_root = {
        "files": [
            {
                "id": "folder-2",
                "name": "Reports",
                "mimeType": GOOGLE_DRIVE_FOLDER_MIME,
            }
        ]
    }
    response_child = {
        "files": [
            {
                "id": "child-file",
                "name": "report.csv",
                "mimeType": "text/csv",
                "size": "10",
                "modifiedTime": drive_timestamp,
            }
        ]
    }
    mocker.patch.object(
        provider,
        "_execute_with_retry",
        new=mocker.AsyncMock(side_effect=[response_root, response_child]),
    )

    files = await provider.list_files("folder", ["csv"])

    assert len(files) == 1
    assert files[0].folder_path == "Reports"


def test_extrae_extension_en_minusculas(provider, drive_timestamp):
    file_info = provider._map_to_file_info(
        {
            "id": "1",
            "name": "REPORT.CSV",
            "mimeType": "text/csv",
            "size": "100",
            "modifiedTime": drive_timestamp,
            "webViewLink": "https://example.com",
        },
        folder_path="datos",
    )

    assert file_info is not None
    assert file_info.extension == "csv"
    assert file_info.asset_type == AssetType.DATASET


def test_retorna_none_para_extension_desconocida(provider, drive_timestamp):
    result = provider._map_to_file_info(
        {
            "id": "1",
            "name": "diseño.psd",
            "mimeType": "image/psd",
            "modifiedTime": drive_timestamp,
        },
        folder_path="",
    )

    assert result is None


def test_infiere_asset_type_desde_extension(provider, drive_timestamp):
    file_info = provider._map_to_file_info(
        {
            "id": "1",
            "name": "video.mp4",
            "mimeType": "video/mp4",
            "size": "1024",
            "modifiedTime": drive_timestamp,
        },
        folder_path="videos",
    )

    assert file_info is not None
    assert file_info.asset_type == AssetType.VIDEO


def test_size_bytes_es_cero_si_drive_no_reporta_size(provider, drive_timestamp):
    file_info = provider._map_to_file_info(
        {
            "id": "1",
            "name": "doc.pdf",
            "mimeType": "application/pdf",
            "modifiedTime": drive_timestamp,
        },
        folder_path="docs",
    )

    assert file_info is not None
    assert file_info.size_bytes == 0


def test_modified_at_es_datetime_utc(provider, drive_timestamp):
    file_info = provider._map_to_file_info(
        {
            "id": "1",
            "name": "sheet.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": "10",
            "modifiedTime": drive_timestamp,
        },
        folder_path="",
    )

    assert file_info is not None
    assert file_info.modified_at.tzinfo == timezone.utc


def test_retorna_none_si_archivo_sin_extension(provider, drive_timestamp):
    result = provider._map_to_file_info(
        {
            "id": "1",
            "name": "README",
            "mimeType": "text/plain",
            "modifiedTime": drive_timestamp,
        },
        folder_path="",
    )

    assert result is None
