from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.models.common import AssetType, SourceType


class GoogleDriveCredentials(BaseModel):
    """Credenciales OAuth2 de Google Drive provistas por el frontend."""

    access_token: str = Field(
        ...,
        description="Access token OAuth2 emitido por Google. Expira en 1 hora.",
        min_length=10,
    )


ProviderCredentials = GoogleDriveCredentials


class ListRequest(BaseModel):
    """Schema del request para listar archivos desde un bucket externo."""

    source: SourceType = Field(
        ...,
        description="Identificador del provider de bucket.",
    )
    credentials: ProviderCredentials = Field(
        ...,
        description="Credenciales de autenticación para el provider indicado en 'source'.",
    )
    folder_id: str = Field(
        ...,
        description="ID de la carpeta raíz en el provider.",
        min_length=1,
    )
    asset_types: list[AssetType] = Field(
        ...,
        description="Categorías de activos a listar. Se expanden a extensiones internamente.",
        min_length=1,
    )
    max_depth: int | None = Field(
        default=None,
        description="Profundidad máxima de recursión en subcarpetas. None = sin límite.",
        ge=1,
        le=20,
    )

    @field_validator("asset_types")
    @classmethod
    def asset_types_no_duplicates(cls, value: list[AssetType]) -> list[AssetType]:
        seen: set[AssetType] = set()
        unique: list[AssetType] = []
        for asset_type in value:
            if asset_type not in seen:
                seen.add(asset_type)
                unique.append(asset_type)
        return unique


__all__ = [
    "GoogleDriveCredentials",
    "ProviderCredentials",
    "ListRequest",
]
