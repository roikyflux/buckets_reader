from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from functools import partial
from typing import Any, Callable, cast

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_fixed

from app.exceptions import (
    FolderNotFoundError,
    InvalidCredentialsError,
    ProviderConnectionError,
    ProviderRateLimitError,
)
from app.models.common import ASSET_TYPES_EXTENSIONS, AssetType, SourceType
from app.models.request import GoogleDriveCredentials
from app.models.response import FileInfo
from app.providers.base import BucketProvider


GOOGLE_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
DRIVE_FILE_FIELDS = "id,name,mimeType,size,modifiedTime,webViewLink,parents"
DRIVE_PAGE_SIZE = 1000
RETRY_MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 2.0

logger = logging.getLogger(__name__)


class GoogleDriveProvider(BucketProvider):
    """Implementación de BucketProvider para Google Drive."""

    def __init__(self, credentials: GoogleDriveCredentials) -> None:
        self._credentials = credentials
        self._service: Any | None = None

    async def validate_credentials(self) -> None:
        credentials = Credentials(token=self._credentials.access_token)
        build_callable = partial(build, "drive", "v3", credentials=credentials, cache_discovery=False)

        try:
            self._service = await self._execute_async(build_callable)
        except Exception as exc:  # noqa: BLE001
            raise ProviderConnectionError("No fue posible inicializar el cliente de Google Drive.") from exc

    async def list_files(
        self,
        folder_id: str,
        extensions: list[str],
        max_depth: int | None = None,
        *,
        current_depth: int = 0,
        current_path: str = "",
    ) -> list[FileInfo]:
        if max_depth is not None and current_depth >= max_depth:
            return []

        service = self._ensure_service()
        allowed_extensions = {ext.lower() for ext in extensions}

        start_time = time.monotonic()
        logger.info(
            "GoogleDriveProvider.list_files start: folder_id=%s extensions=%s current_depth=%s max_depth=%s",
            folder_id,
            sorted(allowed_extensions),
            current_depth,
            max_depth,
        )

        files_resource = service.files()
        page_token: str | None = None
        items: list[FileInfo] = []

        try:
            while True:
                request = files_resource.list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields=f"nextPageToken, files({DRIVE_FILE_FIELDS})",
                    pageSize=DRIVE_PAGE_SIZE,
                    pageToken=page_token,
                    supportsAllDrives=False,
                )
                response = await self._execute_with_retry(request.execute)

                raw_files = response.get("files", [])
                subfolders: list[dict[str, Any]] = []

                for entry in raw_files:
                    if entry.get("mimeType") == GOOGLE_DRIVE_FOLDER_MIME:
                        subfolders.append(entry)
                        continue

                    file_info = self._map_to_file_info(entry, folder_path=current_path)
                    if file_info is None:
                        continue
                    if file_info.extension not in allowed_extensions:
                        continue
                    items.append(file_info)

                for folder in subfolders:
                    folder_id_value = folder.get("id")
                    folder_name = folder.get("name")
                    if not folder_id_value or not folder_name:
                        continue
                    child_path = folder_name if not current_path else f"{current_path}/{folder_name}"
                    sub_items = await self.list_files(
                        folder_id=folder_id_value,
                        extensions=extensions,
                        max_depth=max_depth,
                        current_depth=current_depth + 1,
                        current_path=child_path,
                    )
                    items.extend(sub_items)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as http_error:
            self._handle_http_error(http_error, folder_id)

        duration_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "GoogleDriveProvider.list_files done: folder_id=%s total_files=%s duration_ms=%.2f",
            folder_id,
            len(items),
            duration_ms,
        )
        return items

    async def get_file_metadata(self, file_id: str) -> FileInfo:
        service = self._ensure_service()
        request = service.files().get(fileId=file_id, fields=DRIVE_FILE_FIELDS)

        raw_file: dict[str, Any] = {}
        try:
            raw_file = await self._execute_with_retry(request.execute)
        except HttpError as http_error:
            status = self._extract_status(http_error)
            if status == 404:
                raise FolderNotFoundError(f"El archivo '{file_id}' no existe o no es accesible.") from http_error
            self._handle_http_error(http_error, file_id)
            raise ProviderConnectionError("Error al obtener metadata del archivo de Google Drive.") from http_error

        file_info = self._map_to_file_info(raw_file, folder_path="")
        if file_info is None:
            raise FolderNotFoundError(f"El archivo '{file_id}' no está disponible con una extensión válida.")
        return file_info

    async def _execute_async(self, callable_: Callable[[], Any]) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, callable_)

    async def _execute_with_retry(self, callable_: Callable[[], Any]) -> Any:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(self._should_retry_error),
            stop=stop_after_attempt(RETRY_MAX_ATTEMPTS),
            wait=wait_fixed(RETRY_WAIT_SECONDS),
            reraise=True,
            before_sleep=self._log_retry_attempt,
        ):
            with attempt:
                return await self._execute_async(callable_)

    @staticmethod
    def _log_retry_attempt(retry_state: RetryCallState) -> None:
        exception = retry_state.outcome.exception() if retry_state.outcome else None
        if exception is None:
            return
        wait = retry_state.next_action.sleep if retry_state.next_action else 0.0
        logger.warning(
            "Reintentando llamada a Google Drive (intento %s/%s, espera=%.1fs): %s",
            retry_state.attempt_number,
            RETRY_MAX_ATTEMPTS,
            wait,
            exception,
        )

    @staticmethod
    def _should_retry_error(exception: BaseException) -> bool:
        if isinstance(exception, HttpError):
            status = GoogleDriveProvider._extract_status(exception)
            return status in {429, 500, 502, 503, 504}
        return False

    @staticmethod
    def _extract_status(error: HttpError) -> int:
        if hasattr(error, "status_code") and error.status_code is not None:
            return int(error.status_code)
        if error.resp is not None and getattr(error.resp, "status", None) is not None:
            return int(error.resp.status)
        return 0

    def _handle_http_error(self, error: HttpError, resource_id: str) -> None:
        status = self._extract_status(error)
        if status == 401:
            raise InvalidCredentialsError("El token de acceso fue rechazado por Google Drive.") from error
        if status == 404:
            raise FolderNotFoundError(f"El recurso '{resource_id}' no existe o no es accesible.") from error
        if status == 429:
            raise ProviderRateLimitError("Google Drive impuso un límite de peticiones.") from error
        raise ProviderConnectionError("Error al comunicarse con Google Drive.") from error

    def _ensure_service(self) -> Any:
        if self._service is None:
            raise ProviderConnectionError("El cliente de Google Drive no está inicializado. Llama a validate_credentials() primero.")
        return self._service

    def _map_to_file_info(self, drive_file: dict, folder_path: str) -> FileInfo | None:
        name = drive_file.get("name") or ""
        if "." not in name:
            return None

        extension = name.rsplit(".", 1)[-1].lower()
        asset_type = self._resolve_asset_type(extension)
        if asset_type is None:
            return None

        modified_time = drive_file.get("modifiedTime")
        modified_at = self._parse_modified_time(modified_time) if modified_time else datetime.now(timezone.utc)

        size_raw = cast(int | float | str | None, drive_file.get("size"))
        if isinstance(size_raw, (int, float)):
            size_bytes = int(size_raw)
        elif isinstance(size_raw, str):
            try:
                size_bytes = int(size_raw)
            except ValueError:
                size_bytes = 0
        else:
            size_bytes = 0

        preview_url = drive_file.get("webViewLink") or None
        if preview_url == "":
            preview_url = None

        return FileInfo(
            id=drive_file.get("id", ""),
            name=name,
            extension=extension,
            asset_type=asset_type,
            mime_type=drive_file.get("mimeType", ""),
            size_bytes=size_bytes,
            modified_at=modified_at,
            preview_url=preview_url,
            folder_path=folder_path,
            source=SourceType.GOOGLE_DRIVE.value,
        )

    @staticmethod
    def _resolve_asset_type(extension: str) -> AssetType | None:
        for asset_type, extensions in ASSET_TYPES_EXTENSIONS.items():
            if extension in extensions:
                return asset_type
        return None

    @staticmethod
    def _parse_modified_time(value: str) -> datetime:
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).astimezone(timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)


__all__ = ["GoogleDriveProvider"]
