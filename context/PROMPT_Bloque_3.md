# Prompt — Bloque 3: Provider Interface + Factory

## Contexto del proyecto

Estás implementando el **ETL Bucket Service**. La especificación completa está en `context/`. Las instrucciones de trabajo están en `AGENTS.md`.

Este es el **Bloque 3 de 6**. Los bloques anteriores están completos:
- Bloque 1: infraestructura, config, excepciones, main.py ✅
- Bloque 2: modelos Pydantic (common, request, response) ✅

En este bloque implementas la interfaz abstracta `BucketProvider` y la función factory `get_provider`. Son los contratos que gobiernan todos los providers actuales y futuros.

---

## Documentos que debes leer ANTES de escribir código

1. `context/DOC-02_Component_Specification.md` — Sección 4.1 (`base.py`) y Sección 4.2 (`factory.py`) completas. Leer cada docstring con atención — son contratos de implementación.
2. `context/DOC-07_Extensibility_Guide.md` — Sección 2 (principio de extensión) y Sección 3 (pasos 1 y 4). Para entender el rol de la factory en el diseño.
3. `context/ADR-10_Drive_Client_SDK_vs_httpx.md` — Completo. La interfaz abstracta debe reflejar esta decisión en sus docstrings.

---

## Qué implementar en este bloque

### 1. `app/providers/base.py`

Implementar la clase abstracta `BucketProvider` exactamente como especifica DOC-02 Sección 4.1.

Tres métodos abstractos obligatorios:

**`validate_credentials(self) -> None`**
- Prepara el cliente del provider con las credenciales recibidas
- No verifica el token externamente — Token Forwarding Pattern (ADR-03)
- Si hay error de red al inicializar: lanzar `ProviderConnectionError`

**`list_files(self, folder_id, extensions, max_depth, current_depth, current_path) -> list[FileInfo]`**
- Lista archivos recursivamente filtrando por extensiones
- Maneja paginación interna — el llamador recibe lista completa
- Errores posibles: `FolderNotFoundError`, `InvalidCredentialsError`, `ProviderRateLimitError`, `ProviderConnectionError`
- Ver DOC-02 Sección 4.1 para el comportamiento esperado completo

**`get_file_metadata(self, file_id) -> FileInfo`**
- Obtiene metadata de un archivo individual por su ID
- Errores posibles: `FolderNotFoundError`

Requisitos adicionales del ABC:
- El docstring de clase debe incluir el contrato completo: qué debe y qué no debe hacer un provider
- Incluir instrucciones de cómo agregar un nuevo provider (referencia a DOC-07)
- Todos los type hints completos — sin `Any`

### 2. `app/providers/factory.py`

Implementar la función `get_provider(request: ListRequest) -> BucketProvider` exactamente como especifica DOC-02 Sección 4.2.

Comportamiento requerido:
- Importar providers de forma **local** (dentro de la función) — no en el nivel del módulo
- Mantener `PROVIDER_REGISTRY` como dict `{SourceType: type[BucketProvider]}`
- En Fase 1 solo `SourceType.GOOGLE_DRIVE` registrado — los demás comentados
- Si `request.source` no está en el registry: lanzar `UnsupportedProviderError` con mensaje que cite el valor de `request.source`
- Retornar `provider_class(credentials=request.credentials)` — instancia lista, no autenticada

---

## Tests a implementar

### `tests/providers/test_factory.py` (archivo nuevo)

Crear este archivo con los siguientes tests:

```python
# Tests obligatorios:

class TestGetProvider:
    def test_retorna_google_drive_provider_para_source_correcto(self):
        """get_provider() retorna instancia de GoogleDriveProvider para GOOGLE_DRIVE."""
        ...

    def test_lanza_unsupported_provider_error_para_source_desconocido(self):
        """get_provider() lanza UnsupportedProviderError si source no está registrado."""
        ...

    def test_mensaje_de_error_cita_el_source_invalido(self):
        """El mensaje de UnsupportedProviderError menciona el valor de source recibido."""
        ...

    def test_provider_instanciado_con_credenciales_del_request(self):
        """El provider retornado tiene las credenciales del request."""
        ...
```

---

## Criterio de aceptación

El bloque está completo cuando se cumple todo lo siguiente con el venv activo:

```bash
# 1. Importaciones sin error
python -c "
from app.providers.base import BucketProvider
from app.providers.factory import get_provider
print('Importaciones: OK')
"

# 2. BucketProvider es una clase abstracta — no se puede instanciar directamente
python -c "
from app.providers.base import BucketProvider
try:
    BucketProvider()
    print('ERROR: debió fallar')
except TypeError:
    print('ABC no instanciable: OK')
"

# 3. Factory retorna provider correcto para google_drive
python -c "
from app.providers.factory import get_provider
from app.providers.google_drive.provider import GoogleDriveProvider
from app.models.request import ListRequest, GoogleDriveCredentials
from app.models.common import SourceType, AssetType

req = ListRequest(
    source=SourceType.GOOGLE_DRIVE,
    credentials=GoogleDriveCredentials(access_token='ya29.test_token_ok'),
    folder_id='abc123',
    asset_types=[AssetType.DATASET]
)
provider = get_provider(req)
assert isinstance(provider, GoogleDriveProvider), f'Tipo incorrecto: {type(provider)}'
print('Factory google_drive: OK')
"

# 4. Factory lanza UnsupportedProviderError para source no registrado
python -c "
from app.providers.factory import get_provider
from app.exceptions import UnsupportedProviderError
from app.models.request import ListRequest, GoogleDriveCredentials
from app.models.common import SourceType, AssetType

# Forzar source inválido saltando la validación Pydantic
import unittest.mock as mock
req = mock.MagicMock()
req.source = 'dropbox'
req.credentials = GoogleDriveCredentials(access_token='ya29.test_token_ok')

try:
    get_provider(req)
    print('ERROR: debió fallar')
except UnsupportedProviderError as e:
    assert 'dropbox' in str(e).lower(), f'Mensaje no cita el source: {e}'
    print('UnsupportedProviderError: OK')
"

# 5. GoogleDriveProvider implementa todos los métodos abstractos
python -c "
from app.providers.google_drive.provider import GoogleDriveProvider
from app.providers.base import BucketProvider
from app.models.request import GoogleDriveCredentials

creds = GoogleDriveCredentials(access_token='ya29.test_token_ok')
provider = GoogleDriveProvider(credentials=creds)
assert isinstance(provider, BucketProvider), 'No es instancia de BucketProvider'

# Verificar que los métodos existen
assert hasattr(provider, 'validate_credentials'), 'Falta validate_credentials'
assert hasattr(provider, 'list_files'), 'Falta list_files'
assert hasattr(provider, 'get_file_metadata'), 'Falta get_file_metadata'
print('GoogleDriveProvider contrato: OK')
"

# 6. Tests unitarios de la factory pasan
pytest tests/providers/test_factory.py -v

# 7. Servidor sigue levantando sin errores
APP_ENV=development uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/health
kill %1 2>/dev/null
```

---

## Restricciones

- **No implementar** la lógica interna de `GoogleDriveProvider` — ese es el Bloque 4. En este bloque `provider.py` solo necesita la estructura de clase con los métodos definidos (pueden tener `...` o `raise NotImplementedError` como cuerpo).
- **No modificar** ningún archivo de los bloques anteriores excepto `app/providers/google_drive/provider.py` para agregar la estructura mínima de clase.
- Los imports de providers dentro de `factory.py` deben ser **locales** (dentro de la función `get_provider`), nunca en el nivel del módulo.
- `BucketProvider` debe usar `ABC` y `@abstractmethod` de `abc` — no simular abstracción con `raise NotImplementedError` sin el decorator.

---

## Entrega esperada

Al finalizar este bloque, estos archivos deben estar completamente implementados:

```
app/providers/base.py                  ✅ BucketProvider ABC completo
app/providers/factory.py               ✅ get_provider() con PROVIDER_REGISTRY
app/providers/google_drive/provider.py ✅ Estructura de clase (métodos sin lógica interna)
tests/providers/test_factory.py        ✅ Tests de la factory (archivo nuevo)
```

El resto del repositorio no se toca.
