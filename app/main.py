from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.exceptions import (
    InvalidCredentialsError,
    UnsupportedProviderError,
    FolderNotFoundError,
    ProviderRateLimitError,
    ProviderConnectionError,
)
from app.models.response import ErrorDetail, ErrorResponse, HealthResponse

app = FastAPI(
    title="ETL Bucket Service",
    version="1.0.0",
    description="Microservicio para listado y transferencia de archivos desde buckets externos.",
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url="/redoc" if settings.APP_ENV == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError) -> JSONResponse:
    error = ErrorResponse(
        error=ErrorDetail(
            code="INVALID_TOKEN",
            message=(
                "El access_token fue rechazado por Google Drive. Puede estar expirado o ser inválido. "
                "El frontend debe refrescar el token y reintentar."
            ),
            field="credentials.access_token",
        )
    )
    return JSONResponse(status_code=401, content=error.model_dump())


@app.exception_handler(UnsupportedProviderError)
async def unsupported_provider_handler(request: Request, exc: UnsupportedProviderError) -> JSONResponse:
    error = ErrorResponse(
        error=ErrorDetail(
            code="UNSUPPORTED_PROVIDER",
            message="El provider solicitado no está soportado en esta versión.",
            field="source",
        )
    )
    return JSONResponse(status_code=400, content=error.model_dump())


@app.exception_handler(FolderNotFoundError)
async def folder_not_found_handler(request: Request, exc: FolderNotFoundError) -> JSONResponse:
    error = ErrorResponse(
        error=ErrorDetail(
            code="FOLDER_NOT_FOUND",
            message="La carpeta solicitada no existe o no es accesible.",
            field="folder_id",
        )
    )
    return JSONResponse(status_code=404, content=error.model_dump())


@app.exception_handler(ProviderRateLimitError)
async def provider_rate_limit_handler(request: Request, exc: ProviderRateLimitError) -> JSONResponse:
    error = ErrorResponse(
        error=ErrorDetail(
            code="PROVIDER_RATE_LIMIT",
            message="Se alcanzó el límite de llamadas api del provider externo. Reintentar en unos segundos.",
            field=None,
        )
    )
    return JSONResponse(status_code=429, content=error.model_dump())


@app.exception_handler(ProviderConnectionError)
async def provider_connection_handler(request: Request, exc: ProviderConnectionError) -> JSONResponse:
    error = ErrorResponse(
        error=ErrorDetail(
            code="PROVIDER_CONNECTION_ERROR",
            message="Error de red o timeout al conectar con el provider externo.",
            field=None,
        )
    )
    return JSONResponse(status_code=502, content=error.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    field = ".".join(str(loc) for loc in errors[0]["loc"] if loc != "body") if errors else None
    error = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message=errors[0]["msg"] if errors else "Error de validación",
            field=field,
        )
    )
    return JSONResponse(status_code=422, content=error.model_dump())


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    error = ErrorResponse(
        error=ErrorDetail(
            code="INTERNAL_ERROR",
            message="Error interno del servidor. Contacte al equipo de desarrollo.",
            field=None,
        )
    )
    return JSONResponse(status_code=500, content=error.model_dump())


@app.get("/health")
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok", version=app.version)
