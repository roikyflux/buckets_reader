# DOC-07 — Guía de Extensibilidad

**Proyecto:** ETL Bucket Service  
**Versión:** 1.0  
**Estado:** APROBADO  
**Fecha:** Marzo 2025  
**Depende de:** DOC-02 — Especificación de Componentes, DOC-04 — Modelo de Datos  

---

## Tabla de Contenidos

1. [Propósito de este Documento](#1-propósito-de-este-documento)
2. [Principio de Extensión](#2-principio-de-extensión)
3. [Cómo Agregar un Nuevo Provider de Bucket](#3-cómo-agregar-un-nuevo-provider-de-bucket)
   - [Paso 1 — Registrar el SourceType](#paso-1--registrar-el-sourcetype)
   - [Paso 2 — Definir el modelo de Credentials](#paso-2--definir-el-modelo-de-credentials)
   - [Paso 3 — Implementar el Provider](#paso-3--implementar-el-provider)
   - [Paso 4 — Registrar en la Factory](#paso-4--registrar-en-la-factory)
   - [Paso 5 — Agregar dependencias](#paso-5--agregar-dependencias)
   - [Paso 6 — Escribir los tests](#paso-6--escribir-los-tests)
   - [Paso 7 — Actualizar la documentación](#paso-7--actualizar-la-documentación)
4. [Ejemplo Completo — Provider AWS S3](#4-ejemplo-completo--provider-aws-s3)
5. [Cómo Agregar una Nueva Categoría de Activo](#5-cómo-agregar-una-nueva-categoría-de-activo)
6. [Cómo Agregar un Nuevo Endpoint](#6-cómo-agregar-un-nuevo-endpoint)
7. [Qué NO modificar al extender](#7-qué-no-modificar-al-extender)
8. [Checklist de Extensión](#8-checklist-de-extensión)
9. [Historial de Revisiones](#9-historial-de-revisiones)

---

## 1. Propósito de este Documento

Este documento es la guía operacional para extender el sistema en el futuro. Está dirigido a:

- **Agentes de programación** que implementen nuevos providers en Fase 2+
- **Desarrolladores** del equipo que agreguen funcionalidades al sistema
- **Arquitectos** que evalúen el impacto de cambios en el diseño

El sistema fue diseñado con el **Principio Open/Closed** como guía central (ADR-04): abierto para extensión, cerrado para modificación. Agregar un nuevo provider de bucket **no debe requerir modificar ningún componente existente** — solo agregar código nuevo.

---

## 2. Principio de Extensión

El sistema tiene **cuatro y solo cuatro puntos de extensión** para agregar un nuevo provider:

```
1. app/models/common.py      → registrar el nuevo SourceType
2. app/models/request.py     → definir el modelo de Credentials
3. app/providers/<nombre>/   → implementar el provider (código nuevo)
4. app/providers/factory.py  → registrar el provider en el registry
```

Todo el resto del sistema — `ListService`, routers, `main.py`, `FileInfo`, `ListResponse`, manejo de errores — **no se toca**. Si al agregar un provider se necesita modificar alguno de esos archivos, es una señal de que el diseño del provider no es correcto.

### Diagrama de puntos de extensión

```
app/models/common.py
  └── SourceType (enum)  ←────────────── PUNTO 1: agregar valor
        │
        ▼
app/models/request.py
  └── ProviderCredentials (union type) ←─ PUNTO 2: agregar modelo credentials
        │
        ▼
app/providers/
  ├── base.py (NO modificar)
  ├── factory.py  ←────────────────────── PUNTO 4: registrar en registry
  ├── google_drive/ (NO modificar)
  └── <nuevo_provider>/  ←─────────────── PUNTO 3: crear directorio e implementar
        ├── __init__.py
        └── provider.py
```

---

## 3. Cómo Agregar un Nuevo Provider de Bucket

Se describen todos los pasos para agregar un provider. Cada paso indica exactamente qué archivo modificar o crear y qué escribir.

---

### Paso 1 — Registrar el SourceType

**Archivo:** `app/models/common.py`  
**Acción:** Agregar el nuevo valor al enum `SourceType`.

```python
class SourceType(str, Enum):
    GOOGLE_DRIVE = "google_drive"
    AWS_S3       = "aws_s3"        # ← agregar
    AZURE_BLOB   = "azure_blob"    # ← agregar
    DROPBOX      = "dropbox"       # ← agregar
```

**Regla:** el valor del enum (string) es el que el frontend enviará en el campo `source` del request. Debe ser `snake_case`, descriptivo y estable — no cambiarlo una vez publicado porque rompe el contrato con el frontend.

---

### Paso 2 — Definir el modelo de Credentials

**Archivo:** `app/models/request.py`  
**Acción:** Crear una nueva clase Pydantic para las credenciales del provider y agregarla al tipo unión `ProviderCredentials`.

```python
# Credenciales para AWS S3
class S3Credentials(BaseModel):
    """
    Credenciales para el provider aws_s3.
    El frontend obtiene estas credenciales de su configuración de IAM.
    El microservicio las usa directamente — nunca las almacena.
    """
    access_key_id: str = Field(
        ...,
        description="AWS Access Key ID del usuario IAM.",
        min_length=16,
        max_length=128
    )
    secret_access_key: str = Field(
        ...,
        description="AWS Secret Access Key del usuario IAM.",
        min_length=16
    )
    region: str = Field(
        ...,
        description="Región AWS del bucket. Ejemplo: 'us-east-1'.",
        min_length=1
    )

# Actualizar el tipo unión — el type checker usará esto para discriminar
ProviderCredentials = GoogleDriveCredentials | S3Credentials
```

**Regla:** el modelo de credentials debe tener solo los campos estrictamente necesarios para autenticar con el provider. No incluir campos opcionales que el microservicio no usa.

---

### Paso 3 — Implementar el Provider

**Acción:** Crear el directorio `app/providers/<nombre>/` con dos archivos.

#### `app/providers/<nombre>/__init__.py`
Archivo vacío. Necesario para que Python reconozca el directorio como módulo.

```python
# vacío
```

#### `app/providers/<nombre>/provider.py`
Implementación completa de `BucketProvider`. **Todos los métodos abstractos deben estar implementados.**

```python
from __future__ import annotations

import asyncio
import logging
from functools import partial

from ..base import BucketProvider
from ...models.response import FileInfo
# Importar el modelo de credentials específico de este provider
# from ...models.request import S3Credentials

logger = logging.getLogger(__name__)


class NuevoProvider(BucketProvider):
    """
    Implementación de BucketProvider para <nombre del servicio>.

    Autenticación:
        Describir aquí cómo se autentica este provider.
        Qué credenciales usa y cómo se transmiten al SDK o API.

    SDK / Cliente HTTP utilizado:
        Indicar qué librería se usa para comunicarse con el provider.
        Si el SDK es síncrono, documentar el uso de run_in_executor (ADR-10).

    Rate limiting:
        Indicar los límites del provider y la estrategia de retry.
    """

    def __init__(self, credentials) -> None:
        """
        Inicializa el provider con las credenciales del request.
        No realiza ninguna llamada de red en el constructor.
        """
        self._credentials = credentials
        self._client = None  # Se inicializa en validate_credentials()

    async def validate_credentials(self) -> None:
        """
        Inicializa el cliente del provider usando las credenciales recibidas.
        No verifica el token externamente (Token Forwarding Pattern, ADR-03).

        Lanza:
            ProviderConnectionError: si hay error al inicializar el cliente.
        """
        # Implementar aquí
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
        Lista archivos en la carpeta indicada y subcarpetas, filtrados por extensión.

        Debe:
        - Manejar paginación interna del provider (retornar lista completa)
        - Ser recursivo hasta max_depth (None = sin límite)
        - Filtrar por extensiones antes de retornar
        - Construir folder_path acumulativo en cada nivel
        - Mapear cada archivo al schema FileInfo

        Lanza:
            FolderNotFoundError: si folder_id no existe o no es accesible.
            InvalidCredentialsError: si el provider rechaza las credenciales (401).
            ProviderRateLimitError: si el provider rechaza por rate limiting.
            ProviderConnectionError: si hay error de red.
        """
        # Implementar aquí
        ...

    async def get_file_metadata(self, file_id: str) -> FileInfo:
        """
        Obtiene metadata de un archivo individual por su ID.

        Lanza:
            FileNotFoundError: si file_id no existe o no es accesible.
        """
        # Implementar aquí
        ...

    # ── Métodos privados ──────────────────────────────────────────

    async def _execute_async(self, callable_):
        """
        Helper para ejecutar llamadas síncronas al SDK en un thread pool.
        Usar para TODA llamada al SDK si este es síncrono (ADR-10).

        Ejemplo:
            result = await self._execute_async(
                partial(self._client.some_method, param1, param2)
            )
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, callable_)

    def _map_to_file_info(self, raw_file: dict, folder_path: str) -> FileInfo | None:
        """
        Convierte el objeto nativo del provider al schema FileInfo interno.
        Retorna None si el archivo no tiene extensión reconocida.

        Responsabilidades:
        - Extraer extensión del nombre del archivo
        - Inferir asset_type desde ASSET_TYPES_EXTENSIONS
        - Normalizar modified_at a datetime UTC
        - Mapear preview_url si el provider la provee
        """
        # Implementar aquí
        ...
```

**Reglas obligatorias para la implementación:**

- Nunca lanzar excepciones crudas del SDK. Siempre envolver en las excepciones de `app/exceptions.py`.
- Nunca importar `GoogleDriveProvider` ni otro provider concreto desde este archivo.
- Nunca guardar estado de usuario entre llamadas (`self._user_data = ...` está prohibido).
- Si el SDK es síncrono, usar `_execute_async()` para toda llamada. Nunca llamar métodos síncronos directamente desde código async.
- Loggear al inicio de `list_files()`: `source`, `folder_id`, `extensions`, `current_depth`.
- Loggear al finalizar `list_files()`: `total_files` encontrados en este nivel y tiempo de ejecución.

---

### Paso 4 — Registrar en la Factory

**Archivo:** `app/providers/factory.py`  
**Acción:** Importar el nuevo provider y agregarlo al diccionario `PROVIDER_REGISTRY`.

```python
def get_provider(request: ListRequest) -> BucketProvider:
    from .google_drive.provider import GoogleDriveProvider
    from .aws_s3.provider import S3Provider              # ← agregar import
    from .azure_blob.provider import AzureBlobProvider   # ← agregar import

    PROVIDER_REGISTRY: dict[SourceType, type[BucketProvider]] = {
        SourceType.GOOGLE_DRIVE: GoogleDriveProvider,
        SourceType.AWS_S3:       S3Provider,             # ← agregar entrada
        SourceType.AZURE_BLOB:   AzureBlobProvider,      # ← agregar entrada
    }

    provider_class = PROVIDER_REGISTRY.get(request.source)

    if provider_class is None:
        raise UnsupportedProviderError(
            f"El provider '{request.source}' no está soportado."
        )

    return provider_class(credentials=request.credentials)
```

**Regla:** los imports son locales (dentro de la función) para evitar importaciones circulares y para que un error en un provider no impida cargar la aplicación.

---

### Paso 5 — Agregar dependencias

**Archivo:** `requirements.txt`  
**Acción:** Agregar el SDK o cliente HTTP del nuevo provider con versión exacta.

```
# AWS S3
boto3==1.35.0

# Azure Blob
azure-storage-blob==12.22.0

# Dropbox
dropbox==11.36.2
```

**Regla:** siempre versiones exactas (`==`), nunca rangos (`>=`). Garantiza builds reproducibles.

---

### Paso 6 — Escribir los tests

**Directorio:** `tests/providers/`  
**Acción:** Crear `test_<nombre>_provider.py` con cobertura mínima obligatoria.

```python
# tests/providers/test_s3_provider.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.providers.aws_s3.provider import S3Provider
from app.models.request import S3Credentials
from app.exceptions import InvalidCredentialsError, FolderNotFoundError

@pytest.fixture
def credentials():
    return S3Credentials(
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1"
    )

@pytest.fixture
def provider(credentials):
    return S3Provider(credentials=credentials)


class TestValidateCredentials:
    async def test_inicializa_cliente_correctamente(self, provider):
        """validate_credentials() no lanza excepción con credenciales válidas."""
        ...

    async def test_lanza_provider_connection_error_si_falla_red(self, provider):
        """validate_credentials() lanza ProviderConnectionError si hay error de red."""
        ...


class TestListFiles:
    async def test_retorna_lista_vacia_si_no_hay_coincidencias(self, provider):
        """list_files() retorna [] si no hay archivos con las extensiones dadas."""
        ...

    async def test_filtra_por_extension_correctamente(self, provider):
        """list_files() incluye solo archivos con extensiones en la lista."""
        ...

    async def test_recursion_en_subcarpetas(self, provider):
        """list_files() explora subcarpetas y retorna archivos de todos los niveles."""
        ...

    async def test_respeta_max_depth(self, provider):
        """list_files() no explora más allá de max_depth niveles."""
        ...

    async def test_maneja_paginacion_interna(self, provider):
        """list_files() consume todas las páginas y retorna lista completa."""
        ...

    async def test_lanza_folder_not_found_si_carpeta_no_existe(self, provider):
        """list_files() lanza FolderNotFoundError si folder_id no existe."""
        ...

    async def test_lanza_invalid_credentials_si_token_rechazado(self, provider):
        """list_files() lanza InvalidCredentialsError si el provider retorna 401."""
        ...

    async def test_construye_folder_path_correctamente(self, provider):
        """FileInfo.folder_path refleja la ruta relativa desde la raíz."""
        ...


class TestMapToFileInfo:
    def test_extrae_extension_en_minusculas(self, provider):
        """_map_to_file_info() extrae extensión en minúsculas sin punto."""
        ...

    def test_retorna_none_si_extension_no_reconocida(self, provider):
        """_map_to_file_info() retorna None para extensiones fuera de ASSET_TYPES_EXTENSIONS."""
        ...

    def test_infiere_asset_type_desde_extension(self, provider):
        """_map_to_file_info() infiere el asset_type correcto para cada extensión."""
        ...
```

**Cobertura mínima obligatoria:** los tests marcados arriba son el mínimo. No hacer deploy de un provider sin ellos.

---

### Paso 7 — Actualizar la documentación

Al agregar un nuevo provider, actualizar los siguientes documentos:

| Documento | Sección | Qué actualizar |
|---|---|---|
| DOC-04 — Modelo de Datos | Sección 3.3 | Agregar fila en tabla de `credentials` por `SourceType` |
| DOC-02 — Componentes | Sección 2 (estructura) | Agregar el nuevo directorio en el árbol |
| DOC-02 — Componentes | `common.py` | Agregar valor comentado en `SourceType` |
| Este documento (DOC-07) | Sección 4 | Agregar ejemplo del nuevo provider si aplica |
| ADR nuevo | — | Crear ADR documentando decisiones del nuevo provider (auth, SDK, etc.) |

---

## 4. Ejemplo Completo — Provider AWS S3

Este ejemplo ilustra cómo quedarían los cuatro puntos de extensión para AWS S3.

### `app/models/common.py`

```python
class SourceType(str, Enum):
    GOOGLE_DRIVE = "google_drive"
    AWS_S3       = "aws_s3"        # ← nuevo
```

### `app/models/request.py`

```python
class S3Credentials(BaseModel):
    """Credenciales IAM para acceder a un bucket S3."""
    access_key_id: str = Field(..., min_length=16, max_length=128)
    secret_access_key: str = Field(..., min_length=16)
    region: str = Field(..., min_length=1, example="us-east-1")

ProviderCredentials = GoogleDriveCredentials | S3Credentials
```

### `app/providers/aws_s3/provider.py` (estructura)

```python
class S3Provider(BucketProvider):
    """
    Implementación para AWS S3.

    SDK: boto3 (síncrono) con run_in_executor (ADR-10).
    Auth: Access Key + Secret Key pasados por el frontend.
    folder_id: nombre del bucket S3. Las "subcarpetas" son prefijos de objeto.

    Nota sobre recursión en S3:
        S3 no tiene carpetas reales — usa prefijos en los nombres de objeto.
        list_files() usa list_objects_v2 con Delimiter='/' para simular
        estructura de carpetas y recursión.
    """

    def __init__(self, credentials: S3Credentials) -> None:
        self._credentials = credentials
        self._client = None

    async def validate_credentials(self) -> None:
        # Inicializar cliente boto3 con las credenciales recibidas
        # boto3.client('s3', aws_access_key_id=..., aws_secret_access_key=..., region_name=...)
        ...

    async def list_files(self, folder_id, extensions, max_depth=None,
                         current_depth=0, current_path="") -> list[FileInfo]:
        # Usar list_objects_v2 con Prefix=current_path y Delimiter='/'
        # - Contents → archivos en el nivel actual
        # - CommonPrefixes → "subcarpetas" para recursión
        # Manejar paginación con NextContinuationToken
        ...

    async def get_file_metadata(self, file_id: str) -> FileInfo:
        # file_id formato: "bucket_name/path/to/file.csv"
        # Usar head_object para obtener metadata
        ...

    def _map_to_file_info(self, s3_object: dict, folder_path: str) -> FileInfo | None:
        # s3_object tiene: Key, Size, LastModified, ETag
        # preview_url: construir URL pre-firmada con generate_presigned_url
        ...
```

### `app/providers/factory.py`

```python
PROVIDER_REGISTRY = {
    SourceType.GOOGLE_DRIVE: GoogleDriveProvider,
    SourceType.AWS_S3:       S3Provider,           # ← nuevo
}
```

### `requirements.txt`

```
boto3==1.35.0     # ← agregar
```

---

## 5. Cómo Agregar una Nueva Categoría de Activo

Si en el futuro se necesita soportar nuevas extensiones (por ejemplo, `psd`, `ai` para diseño), el único archivo a modificar es:

**Archivo:** `app/models/common.py`

```python
class AssetType(str, Enum):
    AUDIO     = "audio"
    VIDEO     = "video"
    DATASET   = "dataset"
    DOCUMENTS = "documents"
    IMAGES    = "images"
    DESIGN    = "design"     # ← nueva categoría

ASSET_TYPES_EXTENSIONS: dict[AssetType, list[str]] = {
    AssetType.AUDIO:     ["mp3", "wav", "flac"],
    AssetType.VIDEO:     ["mp4", "avi", "mov"],
    AssetType.DATASET:   ["csv", "xlsx", "parquet"],
    AssetType.DOCUMENTS: ["pdf", "docx", "txt"],
    AssetType.IMAGES:    ["png", "jpeg", "jpg", "tiff"],
    AssetType.DESIGN:    ["psd", "ai", "sketch"],   # ← nuevas extensiones
}
```

Ningún otro archivo requiere cambios. El contrato de API acepta automáticamente el nuevo valor porque Pydantic valida contra el enum actualizado.

**Actualizar también:**
- DOC-04 — Modelo de Datos, sección 2.2: agregar fila en la tabla de `AssetType`
- DOC-03 — API REST, sección 4.2: actualizar tabla de expansión de `asset_types`

---

## 6. Cómo Agregar un Nuevo Endpoint

Para agregar un endpoint nuevo al microservicio (por ejemplo, `POST /api/v1/bucket/transfer`):

### Archivos a crear o modificar

| Archivo | Acción |
|---|---|
| `app/models/request.py` | Crear `TransferRequest` con sus campos y validaciones |
| `app/models/response.py` | Crear `TransferResponse` con su schema |
| `app/services/transfer_service.py` | Crear `TransferService` con la lógica de negocio |
| `app/providers/base.py` | Agregar método abstracto si el endpoint requiere nueva capacidad del provider |
| `app/providers/google_drive/provider.py` | Implementar el nuevo método abstracto |
| `app/routers/bucket.py` | Agregar el nuevo endpoint usando el nuevo servicio |

### Archivos que NO se tocan

- `app/main.py` — solo se toca si se necesita un nuevo router
- `app/config.py` — solo si se necesitan nuevas variables de entorno
- `app/exceptions.py` — solo si se necesitan nuevas excepciones específicas

### Regla para métodos abstractos en `BucketProvider`

Si el nuevo endpoint requiere una nueva operación sobre el bucket (por ejemplo, `download_file()`), agregar el método abstracto en `base.py` e implementarlo en **todos** los providers existentes. Un provider que no soporte la operación debe lanzar `NotImplementedError` con mensaje claro.

---

## 7. Qué NO modificar al extender

Esta sección es tan importante como las anteriores. Las siguientes modificaciones rompen el diseño del sistema:

| Acción prohibida | Por qué rompe el diseño |
|---|---|
| Agregar lógica de negocio en `factory.py` | La factory solo instancia — no procesa ni decide |
| Importar un provider concreto desde `list_service.py` | El servicio debe ser agnóstico al provider |
| Agregar campos específicos de un provider en `FileInfo` | `FileInfo` es el contrato común — no puede tener campos de Drive, S3, etc. |
| Modificar `GoogleDriveProvider` al agregar S3 | Cada provider es independiente — cambios en uno no deben afectar a otros |
| Agregar `if source == "google_drive"` en el servicio | Eso es lógica de discriminación — pertenece a la factory o al provider |
| Guardar estado de usuario en el provider (`self._user_cache`) | Los providers son stateless por diseño (ADR-03) |
| Llamar métodos síncronos del SDK directamente en código async | Bloquea el event loop — usar siempre `_execute_async()` (ADR-10) |

---

## 8. Checklist de Extensión

Usar este checklist antes de hacer merge de un nuevo provider.

### Código

- [ ] `SourceType` actualizado en `app/models/common.py`
- [ ] Modelo de `Credentials` creado en `app/models/request.py`
- [ ] `ProviderCredentials` (union type) actualizado en `app/models/request.py`
- [ ] Directorio `app/providers/<nombre>/` creado con `__init__.py` y `provider.py`
- [ ] Los tres métodos abstractos implementados: `validate_credentials`, `list_files`, `get_file_metadata`
- [ ] Helper `_execute_async()` presente si el SDK es síncrono
- [ ] Helper `_map_to_file_info()` implementado
- [ ] Todas las excepciones son de `app/exceptions.py` — ninguna excepción cruda del SDK
- [ ] Provider registrado en `PROVIDER_REGISTRY` de `factory.py`
- [ ] Dependencia agregada en `requirements.txt` con versión exacta

### Tests

- [ ] Tests de `validate_credentials()` — caso exitoso y error de red
- [ ] Tests de `list_files()` — lista vacía, filtrado, recursión, max_depth, paginación, folder_not_found, invalid_credentials
- [ ] Tests de `_map_to_file_info()` — extensión, asset_type, None para extensión desconocida
- [ ] Ningún test hace llamadas reales a APIs externas

### Documentación

- [ ] DOC-04 actualizado — tabla de `credentials` por `SourceType`
- [ ] DOC-02 actualizado — árbol de directorios y `SourceType` en `common.py`
- [ ] ADR nuevo creado con decisiones de autenticación y SDK del provider
- [ ] Este documento (DOC-07) actualizado si hay particularidades del nuevo provider

### Infraestructura

- [ ] `docker-compose.yml` sin cambios (el nuevo provider no requiere servicios adicionales)
- [ ] `.env.example` actualizado solo si el nuevo provider requiere variables de entorno de sistema

---

## 9. Historial de Revisiones

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | Marzo 2025 | Versión inicial — guía para agregar providers, categorías y endpoints |
| 1.1 | Por definir | Actualizar con ejemplo de provider S3 una vez implementado en Fase 2 |

---

*Documento generado por el equipo de Arquitectura de Sistemas.*  
*Para preguntas, referirse a DOC-02 — Especificación de Componentes y ADR-04 — Patrón Abstract Provider + Factory.*
