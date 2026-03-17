# ADR-10 — Cliente HTTP para Google Drive API: SDK vs httpx

**Proyecto:** ETL Bucket Service  
**Versión:** 1.0  
**Estado:** ACCEPTED  
**Fecha:** Marzo 2025  
**Documento padre:** DOC-01 — Architecture Decision Records  

---

## Contexto

El microservicio está diseñado con una arquitectura completamente async (Python + FastAPI + asyncio). Para comunicarse con Google Drive API se evaluaron dos enfoques:

**Opción A — `google-api-python-client` (SDK oficial de Google)**  
El SDK provee una abstracción de alto nivel sobre la REST API de Drive. Maneja construcción de queries, paginación, serialización y errores de forma transparente. Sin embargo, es **completamente síncrono** — bloquea el event loop si se usa directamente.

**Opción B — `httpx` (cliente HTTP async)**  
Llamadas directas a los endpoints REST de Drive API usando un cliente HTTP async nativo. La arquitectura es completamente async sin thread pools. El equipo debe implementar y mantener manualmente la capa de integración: construcción de queries, paginación, parsing de errores de Google.

---

## Decisión

**Fase 1: Opción A — `google-api-python-client` con `run_in_executor`**

Cada llamada síncrona al SDK se envuelve en `run_in_executor` para no bloquear el event loop:

```python
import asyncio
from functools import partial

async def _execute_async(callable_):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, callable_)

# Uso en list_files():
result = await _execute_async(
    service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        pageSize=1000,
        fields=DRIVE_FILE_FIELDS
    ).execute
)
```

**Revisión programada en Fase 2: migración a Opción B — `httpx` directo**

---

## Justificación de la Decisión Fase 1

| Factor | SDK + run_in_executor | httpx directo |
|---|---|---|
| Arquitectura async | ⚠️ thread pool | ✅ nativo |
| Velocidad de implementación | ✅ alta | ⚠️ media-baja |
| Riesgo de errores en integración | ✅ bajo (SDK maneja edge cases) | ⚠️ medio (implementación manual) |
| Mantenimiento de integración | ✅ Google mantiene el SDK | ⚠️ equipo mantiene la integración |
| Rendimiento bajo carga alta | ⚠️ limitado por thread pool | ✅ escala bien |
| Dependencias | ⚠️ más pesado | ✅ más liviano |
| Contexto de entrenamiento del agente | ✅ amplio | ⚠️ menor |

**Argumento decisivo para Fase 1:** el microservicio será implementado por un agente de programación. El SDK reduce la superficie de errores de integración y acelera la implementación. El patrón `run_in_executor` es conocido y funciona correctamente para el volumen de Fase 1.

---

## Consecuencias de la Decisión

### Positivas
- Implementación más rápida y segura en Fase 1.
- Menor superficie de bugs en la integración con Drive API.
- El SDK maneja automáticamente cambios menores en la API de Google.

### A monitorear
- El thread pool de Python por default usa `min(32, os.cpu_count() + 4)` hilos. Con carpetas muy grandes y muchas páginas en paralelo, puede convertirse en cuello de botella.
- Cada llamada a Drive API que usa `run_in_executor` ocupa un hilo durante su ejecución.

### Restricción de implementación
- **Nunca** llamar a métodos del SDK directamente desde código async sin `run_in_executor`.
- Crear una función helper `_execute_async(callable_)` en `GoogleDriveProvider` y usarla para **toda** llamada al SDK.
- El helper debe estar documentado con referencia a este ADR.

---

## Criterios para activar la revisión en Fase 2

La migración a `httpx` debe evaluarse cuando se cumpla **cualquiera** de estas condiciones:

1. El tiempo de respuesta del endpoint `/list` supera consistentemente los 15 segundos con carpetas de más de 500 archivos.
2. Se observan errores de saturación del thread pool bajo carga concurrente de múltiples usuarios.
3. Se agrega soporte a un segundo provider que también use un SDK síncrono, amplificando el problema.
4. El equipo decide implementar el endpoint `/transfer` con streaming de archivos grandes — escenario donde async nativo es crítico.

---

## Referencias

- DOC-02 sección 4.3 — `GoogleDriveProvider` — uso de `run_in_executor`
- ADR-02 — Elección de Python + FastAPI como stack del microservicio
- ADR-04 — Patrón Abstract Provider + Factory (aplica a futuros providers)
- [Python docs — run_in_executor](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor)
- [google-api-python-client docs](https://googleapis.github.io/google-api-python-client/docs/)
- [httpx async docs](https://www.python-httpx.org/async/)

---

## Historial

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | Marzo 2025 | Decisión inicial: SDK en Fase 1, revisión httpx en Fase 2 |
