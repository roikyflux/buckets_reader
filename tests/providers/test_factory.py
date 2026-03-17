from __future__ import annotations

import unittest.mock as mock

import pytest

from app.exceptions import UnsupportedProviderError
from app.models.common import SourceType
from app.models.request import GoogleDriveCredentials, ListRequest
from app.providers.factory import get_provider
from app.providers.google_drive.provider import GoogleDriveProvider


class TestGetProvider:
    def test_retorna_google_drive_provider_para_source_correcto(
        self, valid_list_request: ListRequest
    ) -> None:
        provider = get_provider(valid_list_request)

        assert isinstance(provider, GoogleDriveProvider)

    def test_lanza_unsupported_provider_error_para_source_desconocido(self) -> None:
        request = mock.MagicMock()
        request.source = "dropbox"
        request.credentials = GoogleDriveCredentials(access_token="ya29.test_token_ok")

        with pytest.raises(UnsupportedProviderError):
            get_provider(request)  # type: ignore[arg-type]

    def test_mensaje_de_error_cita_el_source_invalido(self) -> None:
        request = mock.MagicMock()
        request.source = "unknown_source"
        request.credentials = GoogleDriveCredentials(access_token="ya29.test_token_ok")

        with pytest.raises(UnsupportedProviderError) as exc_info:
            get_provider(request)  # type: ignore[arg-type]

        assert "unknown_source" in str(exc_info.value)

    def test_provider_instanciado_con_credenciales_del_request(self, valid_list_request: ListRequest) -> None:
        provider = get_provider(valid_list_request)

        assert getattr(provider, "_credentials") == valid_list_request.credentials
