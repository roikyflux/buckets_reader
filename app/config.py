from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Configuración del microservicio cargada desde variables de entorno.
    Todos los valores sensibles vienen de .env, nunca hardcodeados.
    
    Las variables de entorno se documentan en .env.example.
    El archivo .env real nunca se sube a control de versiones.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── Servidor ────────────────────────────────────────────────
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_ENV: str = "production"           # "development" | "production"
    LOG_LEVEL: str = "INFO"

    # ── Seguridad ───────────────────────────────────────────────
    # Lista de orígenes permitidos para CORS.
    # En producción: URL exacta del frontend. En desarrollo: "*"
    CORS_ALLOWED_ORIGINS: list[str] = ["*"]

    # ── Límites operacionales ───────────────────────────────────
    # Tiempo máximo en segundos que el microservicio espera
    # una respuesta de la API del provider externo.
    PROVIDER_REQUEST_TIMEOUT_SECONDS: int = 30

    # Número máximo de archivos retornados en un ListResponse.
    # Previene respuestas excesivamente grandes.
    MAX_FILES_PER_LIST: int = 5000

# Instancia singleton usada en toda la aplicación.
# Importar así: from app.config import settings
settings = Settings()
