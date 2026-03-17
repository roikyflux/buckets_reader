from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    """Identificadores de las fuentes de bucket soportadas."""

    GOOGLE_DRIVE = "google_drive"
    # AWS_S3 = "aws_s3"
    # AZURE_BLOB = "azure_blob"
    # DROPBOX = "dropbox"


class AssetType(str, Enum):
    """Categorías de activos digitales soportadas."""

    AUDIO = "audio"
    VIDEO = "video"
    DATASET = "dataset"
    DOCUMENTS = "documents"
    IMAGES = "images"


ASSET_TYPES_EXTENSIONS: dict[AssetType, list[str]] = {
    AssetType.AUDIO: ["mp3", "wav", "flac"],
    AssetType.VIDEO: ["mp4", "avi", "mov"],
    AssetType.DATASET: ["csv", "xlsx", "parquet"],
    AssetType.DOCUMENTS: ["pdf", "docx", "txt"],
    AssetType.IMAGES: ["png", "jpeg", "jpg", "tiff"],
}


def get_extensions_for_asset_types(asset_types: list[AssetType]) -> list[str]:
    """Retorna la lista plana de extensiones asociadas sin duplicados."""

    seen: set[str] = set()
    extensions: list[str] = []
    for asset_type in asset_types:
        for extension in ASSET_TYPES_EXTENSIONS.get(asset_type, []):
            if extension not in seen:
                seen.add(extension)
                extensions.append(extension)
    return extensions


__all__ = [
    "SourceType",
    "AssetType",
    "ASSET_TYPES_EXTENSIONS",
    "get_extensions_for_asset_types",
]
