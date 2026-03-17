from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import AssetType


class FileInfo(BaseModel):
    """Metadata de un archivo encontrado en el bucket origen."""

    id: str = Field(..., description="Identificador único del archivo en el provider de origen.")
    name: str = Field(..., description="Nombre del archivo incluyendo extensión.")
    extension: str = Field(..., description="Extensión del archivo en minúsculas, sin punto.")
    asset_type: AssetType = Field(..., description="Categoría del activo inferida desde la extensión.")
    mime_type: str = Field(..., description="MIME type del archivo reportado por el provider.")
    size_bytes: int = Field(..., description="Tamaño del archivo en bytes.", ge=0)
    modified_at: datetime = Field(
        ...,
        description="Fecha y hora de la última modificación en UTC ISO 8601.",
    )
    preview_url: str | None = Field(
        default=None,
        description="URL de vista previa o descarga directa en el provider de origen.",
    )
    folder_path: str = Field(
        ...,
        description="Ruta relativa de la carpeta contenedora desde la carpeta raíz solicitada.",
    )
    source: str = Field(..., description="Identificador del provider de origen.")

    @field_validator("modified_at")
    @classmethod
    def ensure_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("modified_at debe incluir información de zona horaria")
        return value.astimezone(timezone.utc)

    @field_validator("preview_url")
    @classmethod
    def normalize_preview_url(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value


class ListResponse(BaseModel):
    """Respuesta del endpoint POST /api/v1/bucket/list."""

    source: str = Field(..., description="Provider consultado.")
    folder_id: str = Field(..., description="ID de la carpeta raíz consultada.")
    total_files: int = Field(..., description="Total de archivos encontrados que coinciden con los filtros.", ge=0)
    asset_types_requested: list[AssetType] = Field(..., description="Categorías solicitadas por el usuario.")
    extensions_searched: list[str] = Field(..., description="Extensiones buscadas, expandidas desde asset_types_requested.")
    files: list[FileInfo] = Field(..., description="Lista plana de archivos encontrados.")

    @model_validator(mode="after")
    def sync_total_files(self) -> "ListResponse":
        self.total_files = len(self.files)
        return self


class ErrorDetail(BaseModel):
    """Detalle estructurado de un error."""

    code: str = Field(..., description="Código de error interno.")
    message: str = Field(..., description="Descripción legible del error.")
    field: str | None = Field(default=None, description="Campo del request asociado al error, si aplica.")


class ErrorResponse(BaseModel):
    """Respuesta de error estándar para todos los endpoints."""

    error: ErrorDetail


class HealthResponse(BaseModel):
    """Respuesta del endpoint GET /health."""

    status: str = Field(..., description="Estado actual del servicio.")
    version: str = Field(..., description="Versión desplegada del servicio.")


__all__ = [
    "FileInfo",
    "ListResponse",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
]
