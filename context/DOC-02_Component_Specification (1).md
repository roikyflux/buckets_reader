# DOC-02 — Especificación de Componentes e Interfaces Internas

**Proyecto:** ETL Bucket Service  
**Versión:** 1.0  
**Estado:** APROBADO  
**Fecha:** Marzo 2025  
**Depende de:** DOC-01 — Architecture Decision Records  
**Siguiente documento:** DOC-03 — Especificación de API REST  

---

## Tabla de Contenidos

1. [Visión General de Componentes](#1-visión-general-de-componentes)
2. [Estructura de Directorios](#2-estructura-de-directorios)
3. [Capa de Modelos — `app/models/`](#3-capa-de-modelos--appmodels)
4. [Capa de Providers — `app/providers/`](#4-capa-de-providers--appproviders)
5. [Capa de Servicios — `app/services/`](#5-capa-de-servicios--appservices)
6. [Capa de Configuración — `app/config.py`](#6-capa-de-configuración--appconfigpy)
7. [Punto de Entrada — `app/main.py`](#7-punto-de-entrada--appmainpy)
8. [Contratos entre Componentes](#8-contratos-entre-componentes)
9. [Reglas de Implementación](#9-reglas-de-implementación)
10. [Dependencias del Proyecto](#10-dependencias-del-proyecto)

---

## 1. Visión General de Componentes

El microservicio se organiza en cuatro capas con dependencias unidireccionales. Ninguna capa inferior conoce a las capas superiores.

```
┌─────────────────────────────────────────────────────────┐
│                    CAPA HTTP (FastAPI)                   │
│              app/main.py  +  app/routers/               │
│   Recibe requests HTTP, valida con Pydantic, responde   │
└────────────────────────┬────────────────────────────────┘
                         │ llama a
┌────────────────────────▼────────────────────────────────┐
│                  CAPA DE SERVICIOS                       │
│                  app/services/                           │
│   Lógica de negocio: filtrado, paginación, agregación   │
└────────────────────────┬────────────────────────────────┘
                         │ llama a
┌────────────────────────▼────────────────────────────────┐
│                  CAPA DE PROVIDERS                       │
│                  app/providers/                          │
│   Abstracción de fuentes externas (Drive, S3, Azure)    │
│   Interface ABC + implementaciones concretas + factory  │
└────────────────────────┬────────────────────────────────┘
                         │ usa
┌────────────────────────▼────────────────────────────────┐
│                  CAPA DE MODELOS                         │
│                  app/models/                             │
│   Schemas Pydantic: request, response, entidades        │
└─────────────────────────────────────────────────────────┘
```

### Principios que gobiernan el diseño

- **Dependencia hacia adentro:** las capas externas conocen a las internas, nunca al revés.
- **Providers son intercambiables:** la capa de servicios opera exclusivamente sobre la interfaz `BucketProvider`, nunca sobre una implementación concreta.
- **Stateless por diseño:** ningún componente guarda estado entre requests (ADR-03).
- **Fallo explícito:** todo error se lanza como excepción tipada, nunca se retorna silenciosamente.

---

## 2. Estructura de Directorios

```
bucket-etl-service/
│
├── app/
│   ├── main.py                        # Punto de entrada FastAPI
│   ├── config.py                      # Settings con pydantic-settings
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── common.py                  # Tipos compartidos: AssetType, SourceType
│   │   ├── request.py                 # ListRequest, TransferRequest
│   │   └── response.py                # FileInfo, ListResponse, ErrorResponse
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                    # BucketProvider (ABC)
│   │   ├── factory.py                 # get_provider() — función factory
│   │   └── google_drive/
│   │       ├── __init__.py
│   │       └── provider.py            # GoogleDriveProvider(BucketProvider)
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   └── list_service.py            # ListService — lógica de listado y filtrado
│   │
│   └── routers/
│       ├── __init__.py
│       └── bucket.py                  # Endpoints: /api/v1/bucket/list
│
├── tests/
│   ├── conftest.py
│   ├── providers/
│   │   └── test_google_drive.py
│   └── services/
│       └── test_list_service.py
│
├── .env.example                       # Variables de entorno documentadas
├── .env                               # Variables reales — NUNCA en git
├── .gitignore
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 3. Capa de Modelos — `app/models/`

### 3.1 `app/models/common.py`

Define los tipos enumerados compartidos por toda la aplicación.

```python
from enum import Enum

class SourceType(str, Enum):
    """
    Identificadores de las fuentes de bucket soportadas.
    Al agregar un nuevo provider, se añade aquí y en la factory.
    """
    GOOGLE_DRIVE = "google_drive"
    # Fase 2+:
    # AWS_S3      = "aws_s3"
    # AZURE_BLOB  = "azure_blob"
    # DROPBOX     = "dropbox"

class AssetType(str, Enum):
    """
    Categorías de activos digitales soportadas.
    Corresponde a las claves de ASSET_TYPES_EXTENSIONS.
    """
    AUDIO     = "audio"
    VIDEO     = "video"
    DATASET   = "dataset"
    DOCUMENTS = "documents"
    IMAGES    = "images"

# Mapa canónico de extensiones por categoría.
# Es la única fuente de verdad para extensiones válidas en todo el sistema.
ASSET_TYPES_EXTENSIONS: dict[AssetType, list[str]] = {
    AssetType.AUDIO:     ["mp3", "wav", "flac"],
    AssetType.VIDEO:     ["mp4", "avi", "mov"],
    AssetType.DATASET:   ["csv", "xlsx", "parquet"],
    AssetType.DOCUMENTS: ["pdf", "docx", "txt"],
    AssetType.IMAGES:    ["png", "jpeg", "jpg", "tiff"],
}

def get_extensions_for_asset_types(asset_types: list[AssetType]) -> list[str]:
    """
    Retorna la lista plana de extensiones correspondientes
    a las categorías solicitadas. Sin duplicados.
    
    Ejemplo:
        get_extensions_for_asset_types([AssetType.AUDIO, AssetType.IMAGES])
        → ["mp3", "wav", "flac", "png", "jpeg", "jpg", "tiff"]
    """
    ...
```

---

### 3.2 `app/models/request.py`

Define los schemas de entrada validados por Pydantic en cada endpoint.

```python
from pydantic import BaseModel, Field, field_validator
from .common import SourceType, AssetType

class GoogleDriveCredentials(BaseModel):
    """
    Credenciales OAuth2 de Google Drive provistas por el frontend.
    El access_token es emitido por Google tras el flujo OAuth2 en el frontend.
    """
    access_token: str = Field(
        ...,
        description="Access token OAuth2 emitido por Google. Expira en 1 hora.",
        min_length=10
    )
    # Nota: el token_type siempre es "Bearer" para Google OAuth2.
    # No se incluye refresh_token: el frontend es responsable del refresh (ADR-03).

# Unión de credenciales por provider.
# Al agregar un nuevo provider, se extiende este tipo.
ProviderCredentials = GoogleDriveCredentials  # | S3Credentials | AzureCredentials

class ListRequest(BaseModel):
    """
    Request para el endpoint POST /api/v1/bucket/list.
    
    El frontend envía:
    - La fuente del bucket (qué sistema de almacenamiento).
    - Las credenciales para autenticarse en ese sistema.
    - El ID de la carpeta raíz a explorar.
    - Las categorías de activos que el usuario desea listar.
    """
    source: SourceType = Field(
        ...,
        description="Identificador del provider de bucket.",
        example="google_drive"
    )
    credentials: GoogleDriveCredentials = Field(
        ...,
        description="Credenciales de autenticación para el provider indicado en 'source'."
    )
    folder_id: str = Field(
        ...,
        description="ID de la carpeta raíz en el provider. Para Google Drive, es el ID de la carpeta en la URL.",
        min_length=1,
        example="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
    )
    asset_types: list[AssetType] = Field(
        ...,
        description="Categorías de activos a listar. El sistema expande cada categoría a sus extensiones correspondientes.",
        min_length=1,
        example=["dataset", "documents"]
    )
    max_depth: int | None = Field(
        default=None,
        description="Profundidad máxima de recursión en subcarpetas. None = sin límite.",
        ge=1,
        le=20
    )

    @field_validator("asset_types")
    @classmethod
    def asset_types_no_duplicates(cls, v: list[AssetType]) -> list[AssetType]:
        """Elimina duplicados preservando el orden."""
        ...
```

---

### 3.3 `app/models/response.py`

Define los schemas de salida de todos los endpoints.

```python
from pydantic import BaseModel, Field
from datetime import datetime
from .common import AssetType

class FileInfo(BaseModel):
    """
    Metadata de un archivo encontrado en el bucket origen.
    Este es el objeto atómico que el frontend recibe por cada archivo.
    """
    id: str = Field(
        ...,
        description="Identificador único del archivo en el provider de origen. Usado en TransferRequest.",
        example="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
    )
    name: str = Field(
        ...,
        description="Nombre del archivo incluyendo extensión.",
        example="ventas_Q1_2025.csv"
    )
    extension: str = Field(
        ...,
        description="Extensión del archivo en minúsculas, sin punto.",
        example="csv"
    )
    asset_type: AssetType = Field(
        ...,
        description="Categoría del activo inferida desde la extensión.",
        example="dataset"
    )
    mime_type: str = Field(
        ...,
        description="MIME type del archivo reportado por el provider.",
        example="text/csv"
    )
    size_bytes: int = Field(
        ...,
        description="Tamaño del archivo en bytes.",
        ge=0,
        example=204800
    )
    modified_at: datetime = Field(
        ...,
        description="Fecha y hora de la última modificación en UTC ISO 8601.",
        example="2025-03-10T14:30:00Z"
    )
    preview_url: str | None = Field(
        default=None,
        description="URL de vista previa o descarga directa en el provider de origen. Puede ser None si el provider no la provee.",
        example="https://drive.google.com/file/d/1BxiM.../view"
    )
    folder_path: str = Field(
        ...,
        description="Ruta relativa de la carpeta contenedora desde la carpeta raíz solicitada.",
        example="datos/2025/Q1"
    )
    source: str = Field(
        ...,
        description="Identificador del provider de origen. Útil cuando el frontend agrega resultados de múltiples fuentes.",
        example="google_drive"
    )

class ListResponse(BaseModel):
    """
    Respuesta del endpoint POST /api/v1/bucket/list.
    Contiene la lista completa y plana de archivos encontrados.
    """
    source: str = Field(..., description="Provider consultado.", example="google_drive")
    folder_id: str = Field(..., description="ID de la carpeta raíz consultada.")
    total_files: int = Field(..., description="Total de archivos encontrados que coinciden con los filtros.", ge=0)
    asset_types_requested: list[AssetType] = Field(..., description="Categorías solicitadas por el usuario.")
    extensions_searched: list[str] = Field(..., description="Extensiones buscadas, expandidas desde asset_types_requested.")
    files: list[FileInfo] = Field(..., description="Lista plana de archivos encontrados.")

class ErrorDetail(BaseModel):
    """Detalle estructurado de un error."""
    code: str = Field(..., description="Código de error interno.", example="INVALID_TOKEN")
    message: str = Field(..., description="Descripción legible del error.", example="El access_token proporcionado ha expirado.")
    field: str | None = Field(default=None, description="Campo del request que causó el error, si aplica.")

class ErrorResponse(BaseModel):
    """
    Respuesta de error estándar para todos los endpoints.
    Todos los errores del sistema retornan este schema.
    """
    error: ErrorDetail
```

---

## 4. Capa de Providers — `app/providers/`

### 4.1 `app/providers/base.py` — Interfaz Abstracta

Esta es la interfaz que **todo provider debe implementar**. La capa de servicios opera exclusivamente sobre este contrato.

```python
from abc import ABC, abstractmethod
from ..models.response import FileInfo

class BucketProvider(ABC):
    """
    Interfaz abstracta para providers de bucket.
    
    Contrato:
    - Cada método abstracto DEBE ser implementado por los providers concretos.
    - Un provider NO DEBE guardar estado de usuario entre llamadas.
    - Un provider DEBE lanzar excepciones del módulo app.exceptions, nunca
      propagar excepciones crudas del SDK del provider.
    - Un provider DEBE ser instanciable con las credenciales recibidas en el request.
    
    Para agregar un nuevo provider:
    1. Crear app/providers/<nombre>/provider.py
    2. Implementar esta interfaz completa
    3. Registrar en app/providers/factory.py
    4. Agregar el SourceType en app/models/common.py
    Ver DOC-07 — Guía de Extensibilidad para el proceso completo.
    """

    @abstractmethod
    async def validate_credentials(self) -> None:
        """
        Prepara el cliente del provider usando las credenciales recibidas.
        No verifica el token externamente (Token Forwarding Pattern, ADR-03).

        El token se asume válido: es responsabilidad del frontend enviarlo vigente.
        Si el token es inválido, el primer método que lo use lanzará InvalidCredentialsError
        al recibir HTTP 401 del provider externo.

        Lanza:
            ProviderConnectionError: si hay error de red al inicializar el cliente.
        """
        ...

    @abstractmethod
    async def list_files(
        self,
        folder_id: str,
        extensions: list[str],
        max_depth: int | None = None,
        current_depth: int = 0,
        current_path: str = ""
    ) -> list[FileInfo]:
        """
        Lista todos los archivos en la carpeta indicada y sus subcarpetas,
        filtrando por las extensiones proporcionadas.
        
        Parámetros:
            folder_id:     ID de la carpeta raíz en el provider.
            extensions:    Lista de extensiones en minúsculas sin punto. Ej: ["csv", "pdf"]
            max_depth:     Profundidad máxima de recursión. None = sin límite.
            current_depth: Profundidad actual (uso interno recursivo). No debe pasarse externamente.
            current_path:  Ruta relativa acumulada (uso interno recursivo). No debe pasarse externamente.
        
        Retorna:
            Lista plana de FileInfo. Vacía si no hay coincidencias.
        
        Lanza:
            FolderNotFoundError: si folder_id no existe o no es accesible.
            ProviderRateLimitError: si el provider rechaza por exceso de llamadas.
            ProviderConnectionError: si hay error de red durante el listado.
        
        Comportamiento esperado:
            - La recursión procesa primero los archivos de la carpeta actual,
              luego itera sobre las subcarpetas.
            - Los archivos que no coincidan con ninguna extensión se ignoran silenciosamente.
            - La paginación interna del provider se maneja dentro de este método.
              El llamador recibe siempre una lista completa.
        """
        ...

    @abstractmethod
    async def get_file_metadata(self, file_id: str) -> FileInfo:
        """
        Obtiene la metadata de un archivo individual por su ID.
        
        Parámetros:
            file_id: ID único del archivo en el provider.
        
        Retorna:
            FileInfo con todos los campos completos.
        
        Lanza:
            FileNotFoundError: si el file_id no existe o no es accesible.
        
        Nota: este método es utilizado para verificar archivos antes de transferirlos
        en el endpoint TRANSFER (Fase 1.1).
        """
        ...
```

---

### 4.2 `app/providers/factory.py` — Función Factory

```python
from ..models.common import SourceType
from ..models.request import ListRequest
from .base import BucketProvider

def get_provider(request: ListRequest) -> BucketProvider:
    """
    Factory que instancia el provider correcto según el campo source del request.
    
    Parámetros:
        request: ListRequest completo. La factory extrae source y credentials.
    
    Retorna:
        Instancia de BucketProvider lista para usar. No autenticada aún —
        el llamador debe invocar validate_credentials() antes de list_files().
    
    Lanza:
        UnsupportedProviderError (HTTP 400): si request.source no tiene
        un provider registrado.
    
    Registro de providers:
        Para agregar un nuevo provider, importarlo aquí y agregarlo al diccionario
        PROVIDER_REGISTRY. No modificar la lógica de la función.
    
    Ejemplo de uso:
        provider = get_provider(request)
        await provider.validate_credentials()
        files = await provider.list_files(...)
    """
    from .google_drive.provider import GoogleDriveProvider
    # Fase 2+:
    # from .aws_s3.provider import S3Provider
    # from .azure_blob.provider import AzureBlobProvider

    PROVIDER_REGISTRY: dict[SourceType, type[BucketProvider]] = {
        SourceType.GOOGLE_DRIVE: GoogleDriveProvider,
        # SourceType.AWS_S3:      S3Provider,
        # SourceType.AZURE_BLOB:  AzureBlobProvider,
    }

    provider_class = PROVIDER_REGISTRY.get(request.source)

    if provider_class is None:
        # Lanzar UnsupportedProviderError — definida en app/exceptions.py
        ...

    return provider_class(credentials=request.credentials)
```

---

### 4.3 `app/providers/google_drive/provider.py` — Implementación Google Drive

```python
from ..base import BucketProvider
from ...models.request import GoogleDriveCredentials
from ...models.response import FileInfo

# MIME type que Google Drive usa internamente para carpetas.
GOOGLE_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"

# Campos que se solicitan a la API de Drive para minimizar transferencia de datos.
# Ver: https://developers.google.com/drive/api/reference/rest/v3/files
DRIVE_FILE_FIELDS = "id,name,mimeType,size,modifiedTime,webViewLink,parents"

class GoogleDriveProvider(BucketProvider):
    """
    Implementación de BucketProvider para Google Drive.
    
    Autenticación:
        Usa el access_token OAuth2 provisto por el frontend (ADR-03).
        El token se pasa como Bearer en el header Authorization de cada
        llamada a la API de Drive v3.
    
    SDK utilizado:
        google-api-python-client con googleapiclient.discovery.build()
        en modo async usando run_in_executor para no bloquear el event loop.

        Decisión de implementación (ADR-10):
        El SDK es síncrono. Cada llamada a Drive API se envuelve con:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, callable)
        Esta es la estrategia de Fase 1. En Fase 2 se evaluará migrar a
        httpx directo (arquitectura completamente async) si el thread pool
        se convierte en cuello de botella bajo carga alta.
    
    Rate limiting:
        Google Drive API permite 1000 requests/100s por usuario.
        Implementar retry con backoff exponencial usando tenacity.
        Ver constantes RETRY_MAX_ATTEMPTS y RETRY_WAIT_SECONDS.
    
    Paginación:
        La API de Drive pagina resultados con pageToken.
        list_files() consume todas las páginas internamente.
        Tamaño de página configurado en DRIVE_PAGE_SIZE (máximo: 1000).
    """

    DRIVE_PAGE_SIZE: int = 1000
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_WAIT_SECONDS: float = 2.0

    def __init__(self, credentials: GoogleDriveCredentials) -> None:
        """
        Inicializa el provider con las credenciales del request.
        No realiza ninguna llamada de red en el constructor.
        """
        self._credentials = credentials
        self._service = None  # Se construye en validate_credentials()

    async def validate_credentials(self) -> None:
        """
        Construye el cliente de Drive API usando el access_token provisto.
        No realiza ninguna llamada de verificación externa (Token Forwarding Pattern).

        El token se usa directamente como Bearer en cada llamada a Drive API.
        Si el token es inválido o ha expirado, Drive API retornará HTTP 401,
        que el provider captura y convierte en InvalidCredentialsError.

        Responsabilidad del frontend (ADR-03, Modelo 1):
            - Garantizar que el token enviado está vigente.
            - Ejecutar el refresh flow de OAuth2 antes de llamar al microservicio
              si el token está próximo a expirar.
            - El microservicio nunca refresca tokens ni llama a tokeninfo.

        Lanza:
            ProviderConnectionError: si hay error de red al construir el cliente.
        """
        ...

    async def list_files(
        self,
        folder_id: str,
        extensions: list[str],
        max_depth: int | None = None,
        current_depth: int = 0,
        current_path: str = ""
    ) -> list[FileInfo]:
        """
        Implementación recursiva para Google Drive.
        
        Estrategia de consulta:
            Se usa una única query a la API de Drive por carpeta:
            f"'{folder_id}' in parents and trashed = false"
            
            La respuesta incluye tanto archivos como subcarpetas.
            La clasificación entre archivo y carpeta se hace por mimeType:
            - mimeType == GOOGLE_DRIVE_FOLDER_MIME → subcarpeta, recursar
            - mimeType != GOOGLE_DRIVE_FOLDER_MIME → archivo, filtrar por extensión
        
        Filtrado por extensión:
            La extensión se extrae del campo name del archivo (parte después del
            último punto), convertida a minúsculas.
            Si la extensión está en la lista extensions → incluir en resultado.
        
        Construcción de folder_path:
            current_path se acumula en cada nivel recursivo.
            Nivel raíz: current_path = ""
            Primer nivel: current_path = nombre_subcarpeta
            Segundo nivel: current_path = nombre_subcarpeta/nombre_sub_subcarpeta
        
        Paginación interna:
            Usar pageToken de la respuesta para obtener todas las páginas
            antes de retornar. No cortar el listado por límite de página.
        """
        ...

    async def get_file_metadata(self, file_id: str) -> FileInfo:
        """
        Llama a drive.files.get(fileId=file_id, fields=DRIVE_FILE_FIELDS).
        Mapea la respuesta al schema FileInfo.
        """
        ...

    def _map_to_file_info(
        self,
        drive_file: dict,
        folder_path: str
    ) -> FileInfo | None:
        """
        Método privado. Convierte un objeto de archivo de la Drive API al
        schema FileInfo interno.
        
        Retorna None si el archivo no tiene extensión reconocida
        (no debería ocurrir si el filtro funciona correctamente,
        pero se maneja defensivamente).
        
        Responsabilidades:
            - Extraer extensión del nombre del archivo.
            - Inferir asset_type desde la extensión usando ASSET_TYPES_EXTENSIONS.
            - Convertir modifiedTime (string ISO) a datetime con timezone UTC.
            - Usar webViewLink como preview_url.
            - Convertir size (string en Drive API) a int.
        """
        ...
```

---

## 5. Capa de Servicios — `app/services/`

### 5.1 `app/services/list_service.py`

```python
from ..models.request import ListRequest
from ..models.response import ListResponse
from ..models.common import get_extensions_for_asset_types
from ..providers.factory import get_provider

class ListService:
    """
    Servicio responsable de orquestar el flujo de listado de archivos.
    
    Responsabilidades:
        1. Expandir asset_types a extensiones concretas.
        2. Obtener el provider correcto desde la factory.
        3. Validar credenciales antes de operar.
        4. Invocar list_files() en el provider.
        5. Construir y retornar el ListResponse.
    
    Lo que este servicio NO hace:
        - No conoce ningún provider concreto (solo habla con BucketProvider).
        - No realiza llamadas HTTP directamente.
        - No transforma ni filtra los resultados del provider
          (ese filtrado ocurre dentro del provider).
    
    Uso:
        service = ListService()
        response = await service.execute(request)
    """

    async def execute(self, request: ListRequest) -> ListResponse:
        """
        Ejecuta el flujo completo de listado.
        
        Flujo:
            1. Expandir request.asset_types → lista de extensiones
               usando get_extensions_for_asset_types()
            2. Obtener provider: get_provider(request)
            3. Validar credenciales: await provider.validate_credentials()
            4. Listar archivos: await provider.list_files(
                   folder_id=request.folder_id,
                   extensions=extensions,
                   max_depth=request.max_depth
               )
            5. Construir ListResponse con los resultados
        
        Manejo de excepciones:
            Las excepciones del provider se propagan sin capturar.
            El router HTTP (app/routers/bucket.py) es responsable de
            traducirlas a respuestas HTTP con el schema ErrorResponse.
        
        Parámetros:
            request: ListRequest validado por Pydantic en el router.
        
        Retorna:
            ListResponse con la lista completa de archivos encontrados.
        """
        ...
```

---

## 6. Capa de Configuración — `app/config.py`

```python
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
```

---

## 7. Punto de Entrada — `app/main.py`

```python
"""
Punto de entrada del microservicio ETL Bucket Service.

Responsabilidades de este módulo:
    - Crear la aplicación FastAPI con metadata correcta.
    - Registrar los routers versionados.
    - Configurar CORS con los orígenes del settings.
    - Registrar los exception handlers globales.
    - Exponer el endpoint de health check.

Lo que NO debe estar aquí:
    - Lógica de negocio.
    - Llamadas directas a providers.
    - Configuración de base de datos u otros servicios externos.
"""

# Estructura esperada del módulo:

# 1. Crear instancia FastAPI con:
#    - title="ETL Bucket Service"
#    - version="1.0.0"
#    - description="Microservicio para listado y transferencia de archivos desde buckets externos."
#    - docs_url="/docs" (solo en APP_ENV == "development")
#    - redoc_url="/redoc" (solo en APP_ENV == "development")

# 2. Agregar CORSMiddleware con settings.CORS_ALLOWED_ORIGINS

# 3. Registrar routers:
#    app.include_router(bucket_router, prefix="/api/v1")

# 4. Registrar exception handlers para:
#    - InvalidCredentialsError    → HTTP 401
#    - UnsupportedProviderError   → HTTP 400
#    - FolderNotFoundError        → HTTP 404
#    - ProviderRateLimitError     → HTTP 429
#    - ProviderConnectionError    → HTTP 502
#    - RequestValidationError     → HTTP 422 (Pydantic, ya manejado por FastAPI)
#    - Exception (catch-all)      → HTTP 500

# 5. Endpoint de health check:
#    GET /health → { "status": "ok", "version": "1.0.0" }
#    No requiere autenticación. Usado por Docker health check.
```

---

## 8. Contratos entre Componentes

Esta sección define qué puede y qué no puede hacer cada componente al interactuar con otros.

### 8.1 Router → Service

| Aspecto | Regla |
|---|---|
| El router **puede** | Recibir el request HTTP, validar con Pydantic, llamar al servicio, capturar excepciones y retornar ErrorResponse |
| El router **no puede** | Llamar directamente a providers, contener lógica de negocio |
| El router **debe** | Retornar siempre un schema Pydantic (nunca dicts crudos) |

### 8.2 Service → Provider

| Aspecto | Regla |
|---|---|
| El servicio **puede** | Llamar a `get_provider()`, invocar métodos de `BucketProvider`, construir el response |
| El servicio **no puede** | Importar `GoogleDriveProvider` directamente, manejar lógica específica de Drive |
| El servicio **debe** | Llamar a `validate_credentials()` siempre antes de `list_files()` para inicializar el cliente del provider |

### 8.3 Provider → API Externa

| Aspecto | Regla |
|---|---|
| El provider **puede** | Llamar a la API del bucket externo, usar retry con backoff, manejar paginación |
| El provider **no puede** | Lanzar excepciones crudas del SDK (siempre envolver en excepciones propias) |
| El provider **debe** | Ser stateless: no guardar datos de usuario entre llamadas |

---

## 9. Reglas de Implementación

Las siguientes reglas son **obligatorias** para el agente de programación. No son sugerencias.

### 9.1 Excepciones

Crear el módulo `app/exceptions.py` con las siguientes excepciones antes de implementar cualquier provider:

```python
class ETLBucketServiceError(Exception):
    """Base de todas las excepciones del sistema."""
    pass

class InvalidCredentialsError(ETLBucketServiceError):
    """Token inválido, expirado o sin permisos."""
    pass

class UnsupportedProviderError(ETLBucketServiceError):
    """El campo source no tiene un provider registrado."""
    pass

class FolderNotFoundError(ETLBucketServiceError):
    """La carpeta solicitada no existe o no es accesible."""
    pass

class ProviderRateLimitError(ETLBucketServiceError):
    """El provider rechazó la llamada por rate limiting."""
    pass

class ProviderConnectionError(ETLBucketServiceError):
    """Error de red o timeout al conectar con el provider."""
    pass
```

### 9.2 Async

- Todos los métodos que realizan I/O (llamadas a APIs externas) **deben** ser `async`.
- Las librerías de Google que no son nativas async se deben ejecutar con `asyncio.get_event_loop().run_in_executor(None, fn)`.

### 9.3 Tipado

- Todos los módulos deben usar **type hints completos** en funciones y variables.
- No se permite `Any` de typing salvo en adaptadores de SDK de terceros con tipos mal definidos.
- Usar `from __future__ import annotations` en todos los módulos.

### 9.4 Logging

- Usar el módulo estándar `logging` de Python, configurado en `main.py`.
- Nivel de log configurable via `settings.LOG_LEVEL`.
- **Nunca** loggear access tokens, credenciales ni datos de usuario.
- Loggear al inicio de cada `list_files()`: `source`, `folder_id`, `extensions`, `max_depth`.
- Loggear al finalizar: `total_files` encontrados y tiempo de ejecución en ms.

### 9.5 Testing

- Cada método público de `BucketProvider` debe tener tests unitarios con mocks del SDK de Drive.
- El `ListService` debe tener tests con un `MockProvider` que implementa `BucketProvider`.
- Los tests no deben hacer llamadas reales a ninguna API externa.

---

## 10. Dependencias del Proyecto

### `requirements.txt`

```
# Framework HTTP
fastapi==0.115.0
uvicorn[standard]==0.30.0

# Validación y configuración
pydantic==2.8.0
pydantic-settings==2.4.0

# Google Drive
# Nota ADR-10: SDK síncrono usado con run_in_executor en Fase 1.
# Evaluación de migración a httpx async prevista para Fase 2.
google-api-python-client==2.140.0
google-auth==2.34.0
google-auth-httplib2==0.2.0

# HTTP async client
httpx==0.27.0

# Retry con backoff
tenacity==9.0.0

# Testing
pytest==8.3.0
pytest-asyncio==0.23.0
pytest-mock==3.14.0
```

### `.env.example`

```dotenv
# ── Servidor ────────────────────────────────────────────────────
APP_HOST=0.0.0.0
APP_PORT=8000
APP_ENV=production
LOG_LEVEL=INFO

# ── Seguridad ────────────────────────────────────────────────────
# En producción reemplazar con la URL exacta del frontend
CORS_ALLOWED_ORIGINS=["*"]

# ── Límites operacionales ────────────────────────────────────────
PROVIDER_REQUEST_TIMEOUT_SECONDS=30
MAX_FILES_PER_LIST=5000
```

---

## Historial de Revisiones

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | Marzo 2025 | Versión inicial — cubre Funcionalidad LIST con Google Drive |
| 1.0.1 | Marzo 2025 | Corrección: eliminado `auth.py` y `TokenNearExpiryError`. Adoptado Token Forwarding Pattern (ADR-03). |
| 1.0.2 | Marzo 2025 | Agregada nota ADR-10: SDK síncrono con `run_in_executor` en Fase 1, revisión async con `httpx` en Fase 2. |
| 1.1 | Por definir | Agregar especificación de `TransferService` y `TransferRequest` |

---

*Documento generado por el equipo de Arquitectura de Sistemas.*  
*Para preguntas sobre este documento, referirse a DOC-01 — Architecture Decision Records.*
