# Prompt — Bloque 5: ListService + Router

## Contexto del proyecto

Estás implementando el **ETL Bucket Service**. La especificación completa está en `context/`. Las instrucciones de trabajo están en `AGENTS.md`.

Este es el **Bloque 5 de 6 — el último bloque de código**. Los bloques anteriores están completos:
- Bloque 1: infraestructura, config, excepciones, main.py ✅
- Bloque 2: modelos Pydantic ✅
- Bloque 3: BucketProvider ABC + factory ✅
- Bloque 4: GoogleDriveProvider completo ✅

En este bloque conectas todas las piezas: implementas `ListService`, el router con el endpoint `/api/v1/bucket/list`, registras el router en `main.py`, y escribes los tests de integración del servicio.

Al finalizar este bloque el microservicio estará completamente funcional end-to-end.

---

## Documentos que debes leer ANTES de escribir código

1. `context/DOC-02_Component_Specification.md` — Sección 5 (`ListService`) y Sección 7 (`main.py` — registro de routers).
2. `context/DOC-03_API_REST_Specification.md` — Sección 4.2 completa (endpoint `/api/v1/bucket/list`, todos los casos de error, diagrama de flujo).
3. `context/DOC-04_Data_Model.md` — Sección 4.2 (`ListResponse`) para construir la respuesta correctamente.

---

## Qué implementar en este bloque

### 1. `app/services/list_service.py`

Implementar `ListService` exactamente como especifica DOC-02 Sección 5.

```python
class ListService:
    async def execute(self, request: ListRequest) -> ListResponse:
        ...
```

Flujo del método `execute`:
1. Expandir `request.asset_types` → lista de extensiones usando `get_extensions_for_asset_types()`
2. Obtener provider: `get_provider(request)`
3. Validar credenciales: `await provider.validate_credentials()`
4. Listar archivos: `await provider.list_files(folder_id=..., extensions=..., max_depth=...)`
5. Construir y retornar `ListResponse`

Reglas del servicio:
- No capturar excepciones — propagarlas al router que las convierte a HTTP
- No importar `GoogleDriveProvider` directamente — usar solo `get_provider()`
- No contener lógica de filtrado — eso ya ocurre dentro del provider
- `total_files` = `len(files)` — calculado en el servicio, no en el provider

### 2. `app/routers/bucket.py`

Implementar el router con el endpoint `POST /api/v1/bucket/list`.

```python
router = APIRouter(prefix="/api/v1/bucket", tags=["bucket"])

@router.post("/list", response_model=ListResponse)
async def list_bucket_files(request: ListRequest) -> ListResponse:
    ...
```

El endpoint:
- Instancia `ListService()` y llama a `execute(request)`
- No maneja excepciones — los exception handlers de `main.py` las capturan
- No contiene lógica de negocio

### 3. Actualizar `app/main.py`

Registrar el router del bucket. Agregar estas dos líneas en el lugar correcto:

```python
from app.routers.bucket import router as bucket_router
app.include_router(bucket_router)
```

El resto de `main.py` no se modifica.

### 4. `tests/services/test_list_service.py`

Reemplazar el stub con tests completos. Los tests del servicio usan un **MockProvider** — no el `GoogleDriveProvider` real.

Implementar el `MockProvider` dentro del archivo de tests:

```python
class MockProvider(BucketProvider):
    """Provider falso para tests del servicio."""
    def __init__(self, files_to_return=None, error_to_raise=None):
        self.files_to_return = files_to_return or []
        self.error_to_raise = error_to_raise
        self.validate_called = False
        self.list_files_called = False

    async def validate_credentials(self):
        self.validate_called = True
        if self.error_to_raise:
            raise self.error_to_raise

    async def list_files(self, folder_id, extensions, max_depth=None, *, current_depth=0, current_path=""):
        self.list_files_called = True
        if self.error_to_raise:
            raise self.error_to_raise
        return self.files_to_return

    async def get_file_metadata(self, file_id):
        return self.files_to_return[0] if self.files_to_return else None
```

Tests requeridos:

```
class TestListServiceExecute:
    test_retorna_list_response_con_archivos_encontrados
    test_llama_validate_credentials_antes_de_list_files
    test_expande_asset_types_a_extensiones_correctas
    test_total_files_coincide_con_len_files
    test_propaga_invalid_credentials_error
    test_propaga_folder_not_found_error
    test_propaga_provider_connection_error
    test_list_response_incluye_extensions_searched
    test_pasa_max_depth_al_provider
```

---

## Criterio de aceptación

```bash
# 1. Importaciones sin error
python -c "
from app.services.list_service import ListService
from app.routers.bucket import router
print('Importaciones: OK')
"

# 2. Router registrado en main.py
python -c "
from app.main import app
routes = [r.path for r in app.routes]
assert '/api/v1/bucket/list' in routes, f'Ruta no encontrada. Rutas: {routes}'
print('Router registrado: OK')
"

# 3. Tests del servicio
pytest tests/services/test_list_service.py -v

# 4. Todos los tests del proyecto
pytest tests/ -v

# 5. Servidor levanta correctamente
APP_ENV=development uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/health
echo ""

# 6. Endpoint existe y valida el body
curl -s -X POST http://localhost:8000/api/v1/bucket/list \
  -H "Content-Type: application/json" \
  -d '{}' | python -m json.tool
# Esperado: HTTP 422 con error.code = "VALIDATION_ERROR"

# 7. Endpoint responde correctamente a request malformado
curl -s -X POST http://localhost:8000/api/v1/bucket/list \
  -H "Content-Type: application/json" \
  -d '{"source": "proveedor_invalido", "credentials": {"access_token": "ya29.test_token_ok"}, "folder_id": "abc123", "asset_types": ["dataset"]}' | python -m json.tool
# Esperado: HTTP 400 con error.code = "UNSUPPORTED_PROVIDER"

kill %1 2>/dev/null
```

---

## Restricciones

- `ListService` no importa `GoogleDriveProvider` directamente — solo usa `get_provider()`.
- `ListService` no captura excepciones — las propaga al router.
- El router no contiene lógica de negocio — solo delega a `ListService`.
- Los tests del servicio usan `MockProvider` — nunca el provider real.
- No modificar ningún archivo de bloques anteriores excepto `app/main.py` para agregar el router.

---

## Entrega esperada

```
app/services/list_service.py     ✅ ListService con execute()
app/routers/bucket.py            ✅ Router con POST /api/v1/bucket/list
app/main.py                      ✅ Router registrado (2 líneas agregadas)
tests/services/test_list_service.py  ✅ 9 tests con MockProvider
```

El resto del repositorio no se toca.
