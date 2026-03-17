**ETL BUCKET SERVICE**

Architecture Decision Records

DOC-01 | Versión 1.0 | Marzo 2025

|  |  |
| --- | --- |
| **Proyecto** | **Valor** |
| Nombre del Proyecto | ETL Bucket Service |
| Documento | DOC-01 — Architecture Decision Records |
| Versión | 1.0 |
| Estado | APROBADO |
| Fecha | Marzo 2025 |
| Autor | Arquitectura de Sistemas |
| Audiencia | Equipos de Backend, Frontend, DevOps |

*Este documento registra las decisiones arquitectónicas fundamentales del proyecto ETL Bucket Service. Cada ADR captura el contexto, la decisión tomada, su justificación y las consecuencias conocidas. Este es el documento de referencia que gobierna el diseño e implementación del sistema.*

# 1. Introducción y Alcance

Este conjunto de ADRs documenta las decisiones de arquitectura del ETL Bucket Service, un microservicio Python responsable de conectarse a fuentes de almacenamiento externas (buckets), listar archivos por tipo, y transferirlos a un bucket destino para su posterior procesamiento ETL.

## 1.1 Contexto del Sistema

El sistema se compone de tres capas principales:

* Frontend (equipo externo): interfaz de usuario que permite seleccionar fuente, credenciales y tipos de archivos. Consume la API del microservicio a través de N8N.
* N8N 2.0 (orquestador): instalado sobre Docker en una VM de Google Cloud. Actúa como capa de orquestación y routing entre el frontend y el microservicio.
* Microservicio Python/FastAPI (motor): responsable de toda la lógica de conexión a buckets, filtrado, listado y transferencia de archivos.

## 1.2 Alcance de Fase 1

Las decisiones en este documento cubren exclusivamente la Fase 1 del proyecto:

* Funcionalidad LIST: conectarse a Google Drive, listar archivos recursivamente por extensión y retornar metadata.
* Funcionalidad TRANSFER: mover archivos seleccionados al bucket destino (bucket destino a definir en iteración posterior).
* Soporte inicial a Google Drive como único provider. Arquitectura preparada para extensión a S3, Azure Blob, Dropbox.

## 1.3 Tipos de Archivos Soportados

El sistema debe soportar los siguientes tipos de activos digitales:

|  |  |  |
| --- | --- | --- |
| **Categoría** | **Extensiones** | **Notas** |
| audio | mp3, wav, flac | Archivos de audio de alta calidad |
| video | mp4, avi, mov | Considerar tamaño para streaming |
| dataset | csv, xlsx, parquet | Base del procesamiento ETL |
| documents | pdf, docx, txt | Documentos estructurados y texto plano |
| images | png, jpeg, jpg, tiff | Imágenes de alta resolución |

# 2. Architecture Decision Records

|  |  |
| --- | --- |
| **ADR-01 Patrón de Orquestación: N8N como capa de routing**  **ACCEPTED** | |
| **Contexto** | El sistema debe ser consumido por un frontend externo de otro equipo. Se requiere una capa de integración que no acople directamente al frontend con el microservicio.  La infraestructura ya cuenta con N8N 2.0 instalado sobre Docker en una VM de GCS. |
| **Decisión** | **N8N actúa como orquestador y capa de routing HTTP entre el frontend y el microservicio Python.**  **N8N no contiene lógica de negocio. Solo recibe webhooks, transforma payloads mínimamente y llama al microservicio.** |
| **Justificación** | Reduce acoplamiento: el frontend solo conoce los endpoints de N8N, no la dirección del microservicio.  Permite agregar lógica de retry, logging y alertas en N8N sin modificar el microservicio.  Aprovecha infraestructura ya instalada, reduciendo costos de implementación.  N8N es reemplazable a futuro sin impactar al frontend ni al microservicio. |
| **Alternativas** | * Alternativa rechazada: Frontend llama directamente al microservicio. Crea acoplamiento y expone la infraestructura interna. * Alternativa rechazada: API Gateway (Kong, AWS API Gateway). Viable a futuro pero añade complejidad innecesaria en Fase 1. |
| **Consecuencias** | * Positiva: desacoplamiento completo entre frontend y microservicio. * Positiva: N8N provee UI de debugging y monitoring sin costo adicional. * A monitorear: N8N introduce una hop adicional de latencia (~20-50ms). Aceptable para este caso de uso. * Restricción: N8N no debe procesar ni transformar datos de archivos. Solo orquesta llamadas HTTP. |

|  |  |
| --- | --- |
| **ADR-02 Stack del Microservicio: Python + FastAPI**  **ACCEPTED** | |
| **Contexto** | El sistema necesita un microservicio capaz de conectarse a APIs externas (Google Drive, S3, etc.), manejar archivos de gran tamaño en streaming, y ejecutar transformaciones ETL en fases posteriores.  El equipo de implementación requiere un stack moderno, con soporte async nativo y tipado estático. |
| **Decisión** | **El microservicio se implementa en Python 3.11+ usando FastAPI como framework HTTP.**  **Se usa Pydantic v2 para validación de schemas de request/response.**  **Se usa httpx para llamadas HTTP async hacia APIs externas.** |
| **Justificación** | Python es el estándar de la industria para ETL y procesamiento de datos (pandas, polars, pyarrow disponibles en Fase 2).  FastAPI provee generación automática de documentación OpenAPI, validación con Pydantic y soporte async nativo.  El ecosistema de clientes para Google Drive, S3 y Azure está maduro y bien mantenido en Python.  Pydantic v2 asegura contratos de API explícitos y documentados automáticamente. |
| **Alternativas** | * Alternativa evaluada: Node.js/Express. Descartado por ecosistema ETL inferior. * Alternativa evaluada: Go. Descartado por complejidad de integración con librerías ETL en Fase 2. * Alternativa evaluada: Java/Spring. Descartado por overhead operacional excesivo para este alcance. |
| **Consecuencias** | * Positiva: ecosistema ETL disponible sin cambio de lenguaje en Fase 2. * Positiva: documentación OpenAPI generada automáticamente facilita integración con el equipo de frontend. * Restricción: el equipo de implementación debe usar Python 3.11+ para aprovechar mejoras de tipado. * A monitorear: rendimiento bajo carga alta con archivos grandes. Mitigar con streaming y workers async. |

|  |  |
| --- | --- |
| **ADR-03 Estrategia de Autenticación OAuth2: Opción A — Frontend Stateless**  **ACCEPTED** | |
| **Contexto** | El sistema debe autenticarse con Google Drive en nombre del usuario. Existen múltiples usuarios simultáneos no relacionados entre sí.  El frontend pertenece a un equipo externo independiente. El microservicio debe mantenerse simple y desacoplado de la gestión de sesiones.  Se evaluaron dos opciones: (A) OAuth en el frontend, microservicio stateless; (B) OAuth centralizado en el microservicio con gestión de sesiones. |
| **Decisión** | **La autenticación OAuth2 con Google Drive se gestiona en el frontend.**  **El frontend obtiene el Access Token de Google y lo pasa al microservicio en cada request.**  **El microservicio es completamente stateless: recibe el token, lo usa, no lo almacena.**  **El refresco del token (refresh flow) es responsabilidad del frontend.** |
| **Justificación** | Mantiene el microservicio simple, sin estado y sin dependencias de almacenamiento de sesiones (sin Redis, sin base de datos de tokens).  El equipo de frontend tiene autonomía total sobre el flujo de autenticación y experiencia de usuario.  Facilita el escalado horizontal del microservicio: cualquier instancia puede procesar cualquier request.  Reduce la superficie de seguridad del microservicio: nunca almacena credenciales de usuario.  Estándar en arquitecturas BFF (Backend for Frontend) donde el frontend gestiona el contexto de usuario. |
| **Alternativas** | * Opción B rechazada: OAuth en microservicio. Requiere Redis para sesiones, añade complejidad operacional y acopla el microservicio a la gestión de identidad. * Opción C rechazada: Service Account. Solo aplicable a recursos propios del sistema, no a Drives personales de usuarios. |
| **Consecuencias** | * Positiva: microservicio completamente stateless, fácil de escalar y mantener. * Positiva: el frontend del equipo externo tiene control total del ciclo OAuth. * Responsabilidad asignada al frontend: implementar flujo OAuth2 con Google, manejar expiración de tokens y refresco. * Restricción: el microservicio debe validar que el token recibido no esté expirado antes de usarlo. Retornar HTTP 401 con mensaje claro si el token es inválido. * Restricción futura: al agregar nuevos providers (S3, Azure), el patrón se mantiene — el frontend provee credenciales en cada request. |

|  |  |
| --- | --- |
| **ADR-04 Patrón de Extensibilidad: Abstract Provider con Factory**  **ACCEPTED** | |
| **Contexto** | El sistema debe soportar Google Drive en Fase 1 y extenderse a S3, Azure Blob, Dropbox y otros providers en fases posteriores.  El equipo de implementación debe poder agregar un nuevo provider sin modificar el código existente (Principio Open/Closed).  La lógica de negocio de listado y filtrado de archivos debe ser independiente del provider específico. |
| **Decisión** | **Se implementa una clase abstracta BucketProvider (ABC) que define el contrato que todo provider debe cumplir.**  **Cada provider concreto implementa esa interfaz: GoogleDriveProvider, S3Provider, AzureProvider, etc.**  **Una función factory get\_provider(source: str, credentials: dict) retorna la instancia correcta según el campo source del request.**  **La lógica de negocio en ListService opera exclusivamente sobre la interfaz BucketProvider, sin conocer el provider concreto.** |
| **Justificación** | Permite agregar un nuevo provider implementando solo 2-3 métodos de la interfaz, sin tocar el resto del sistema.  Facilita el testing: cada provider puede testearse de forma aislada con mocks.  El contrato de la API REST no cambia al agregar nuevos providers — el campo source del request selecciona el provider.  Patrón Strategy ampliamente conocido, fácil de mantener por cualquier equipo de backend. |
| **Alternativas** | * Alternativa rechazada: condicionales if/elif por provider dentro del servicio. No escalable, viola Open/Closed. * Alternativa rechazada: plugins dinámicos. Excesiva complejidad para el alcance actual. |
| **Consecuencias** | * Positiva: agregar S3 o Azure en el futuro requiere solo un archivo nuevo, sin modificar código existente. * Positiva: contratos explícitos previenen regresiones al modificar un provider. * Restricción: todo nuevo provider debe implementar el contrato completo de BucketProvider. Métodos no implementados deben lanzar NotImplementedError. * Restricción: la factory debe lanzar una excepción controlada si el source no está registrado, retornando HTTP 400 al cliente. |

|  |  |
| --- | --- |
| **ADR-05 Listado de Archivos: Recursivo con Paginación Interna**  **ACCEPTED** | |
| **Contexto** | El usuario puede seleccionar cualquier carpeta de Google Drive, que puede contener subcarpetas anidadas a múltiples niveles.  Google Drive API pagina sus resultados (máximo 1000 ítems por página). Carpetas grandes pueden requerir múltiples llamadas.  El frontend espera una lista plana y completa de archivos, sin estructura de carpetas. |
| **Decisión** | **El microservicio implementa un listado recursivo de subcarpetas.**  **La paginación de la API de Drive se maneja internamente: el microservicio consume todas las páginas y retorna un resultado unificado.**  **El resultado es una lista plana de archivos filtrados por las extensiones solicitadas.**  **Se expone el campo folder\_path en cada FileInfo para que el frontend pueda mostrar la ruta de origen si lo requiere.** |
| **Justificación** | Simplifica el contrato con el frontend: una sola llamada retorna todos los archivos relevantes.  El filtrado por extensión ocurre en el microservicio, reduciendo datos transferidos al frontend.  La profundidad recursiva no tiene límite fijo pero se incluye un parámetro max\_depth opcional para casos extremos. |
| **Alternativas** | * Alternativa rechazada: exponer paginación al frontend. Añade complejidad al contrato de API sin beneficio claro en Fase 1. * Alternativa rechazada: listado no recursivo. No cumple el requerimiento del usuario. |
| **Consecuencias** | * Positiva: experiencia de usuario simple — una llamada retorna todo. * A monitorear: carpetas con miles de archivos pueden incrementar el tiempo de respuesta. Mitigar con timeout configurable. * Restricción: el microservicio debe implementar retry con backoff exponencial en llamadas a Drive API para manejar rate limits (quota: 1000 req/100s por usuario). * Restricción: se debe incluir el campo total\_files en la respuesta para que el frontend informe al usuario antes de procesar. |

|  |  |
| --- | --- |
| **ADR-06 Separación de Funcionalidades: LIST y TRANSFER como endpoints independientes**  **ACCEPTED** | |
| **Contexto** | El flujo de usuario tiene dos pasos diferenciados: (1) el usuario elige qué tipos de archivos quiere ver, (2) el usuario selecciona de esa lista qué archivos quiere transferir.  Combinar listado y transferencia en una sola operación implicaría transferir archivos que el usuario aún no ha aprobado. |
| **Decisión** | **Se exponen dos endpoints independientes en el microservicio: POST /api/v1/bucket/list y POST /api/v1/bucket/transfer.**  **El endpoint LIST no mueve ningún archivo. Solo retorna metadata.**  **El endpoint TRANSFER recibe los IDs de archivos seleccionados por el usuario y ejecuta la copia al destino.**  **El bucket destino del endpoint TRANSFER queda a definir en la iteración siguiente del proyecto.** |
| **Justificación** | Respeta el flujo mental del usuario: primero explorar, luego actuar.  Permite al frontend implementar una pantalla de confirmación entre ambas operaciones.  Reduce operaciones costosas: archivos no seleccionados nunca se transfieren.  Cada endpoint tiene una responsabilidad única y puede evolucionar independientemente. |
| **Alternativas** | * Alternativa rechazada: endpoint único que lista y transfiere en una sola llamada. No respeta el flujo de aprobación del usuario. |
| **Consecuencias** | * Positiva: flujo de usuario más seguro y controlado. * Positiva: el endpoint LIST es idempotente y puede llamarse múltiples veces sin efectos secundarios. * Restricción: el endpoint TRANSFER debe recibir explícitamente los IDs de los archivos a mover, nunca asumir que todos los listados deben transferirse. * Pendiente: la especificación completa del endpoint TRANSFER (incluyendo bucket destino) se documenta en DOC-03 versión 1.1. |

|  |  |
| --- | --- |
| **ADR-07 Comunicación N8N ↔ Microservicio: HTTP REST Síncrono**  **ACCEPTED** | |
| **Contexto** | N8N necesita llamar al microservicio y obtener una respuesta para retornarla al frontend en el mismo flujo.  Se evaluó comunicación asíncrona (colas de mensajes) versus síncrona (HTTP). |
| **Decisión** | **La comunicación entre N8N y el microservicio se realiza mediante HTTP REST síncrono.**  **N8N usa el nodo HTTP Request para llamar al microservicio.**  **El microservicio retorna la respuesta completa en la misma conexión HTTP.** |
| **Justificación** | HTTP REST es nativo en N8N sin configuración adicional.  Debugging directo: los logs de N8N muestran request y response completos.  Para Fase 1 (listado de archivos), los tiempos de respuesta son predecibles y no justifican complejidad asíncrona.  Simplifica el diagrama de secuencia: un request entra, una respuesta sale. |
| **Alternativas** | * Alternativa rechazada: colas de mensajes (RabbitMQ, Pub/Sub). Necesario en Fase 2 para procesos ETL largos, no justificado para listado. * Alternativa rechazada: WebSockets. Añade complejidad sin beneficio para operaciones de corta duración. |
| **Consecuencias** | * Positiva: implementación simple y debuggeable. * A revisar en Fase 2: los procesos ETL sobre archivos grandes pueden exceder timeouts HTTP. Se evaluará arquitectura async para esa fase. * Restricción: el microservicio debe responder en menos de 30 segundos. Para carpetas muy grandes, implementar respuesta paginada o streaming. * Restricción: N8N debe configurar timeout de al menos 60 segundos en el nodo HTTP Request para acomodar listados de carpetas grandes. |

|  |  |
| --- | --- |
| **ADR-08 Versionado de API: Prefijo /api/v1/ en URL**  **ACCEPTED** | |
| **Contexto** | El microservicio será consumido por un frontend externo que no está bajo control del mismo equipo.  El sistema debe evolucionar sin romper a los clientes existentes. |
| **Decisión** | **Todos los endpoints del microservicio usan el prefijo /api/v1/ en la URL.**  **Cambios breaking se introducen en /api/v2/ manteniendo /api/v1/ operativo durante el período de migración.**  **Cambios no-breaking (campos nuevos opcionales) se pueden agregar en la versión actual.** |
| **Justificación** | Permite evolucionar el contrato de API sin coordinar despliegues simultáneos con el equipo de frontend.  Práctica estándar de la industria, familiar para cualquier equipo de desarrollo.  FastAPI soporta versionado por prefijo de forma nativa con APIRouter. |
| **Alternativas** | * Alternativa rechazada: versionado por header (Accept-Version). Menos visible, más difícil de debuggear. * Alternativa rechazada: sin versionado. Inaceptable dado que el frontend es un equipo externo independiente. |
| **Consecuencias** | * Positiva: el equipo de frontend puede adoptar nuevas versiones a su propio ritmo. * Restricción: toda modificación breaking a un endpoint existente requiere crear una nueva versión y notificar al equipo de frontend con al menos 2 semanas de anticipación. * Restricción: las versiones anteriores deben mantenerse operativas por un mínimo de 30 días tras el lanzamiento de una nueva versión. |

|  |  |
| --- | --- |
| **ADR-09 Infraestructura de Despliegue: Docker Compose en VM GCS**  **ACCEPTED** | |
| **Contexto** | El sistema corre en una VM de Google Cloud con N8N 2.0 ya instalado sobre Docker.  El microservicio Python debe correr en la misma VM, en el mismo entorno Docker, para minimizar latencia y costos de red. |
| **Decisión** | **El microservicio Python se agrega como un servicio adicional en el Docker Compose existente de N8N.**  **Ambos servicios (N8N y microservicio) se comunican a través de la red interna de Docker (no expuesta a internet).**  **Solo N8N expone puerto al exterior. El microservicio no tiene puerto público.**  **Las credenciales de Google Drive (Client ID, Client Secret) se pasan como variables de entorno al microservicio.** |
| **Justificación** | El microservicio no tiene puerto público expuesto, reduciendo la superficie de ataque.  La comunicación interna entre N8N y el microservicio usa DNS interno de Docker (nombre del servicio), no IPs.  Reutiliza la infraestructura existente sin costo adicional.  Docker Compose facilita el despliegue reproducible y el control de versiones de la infraestructura. |
| **Alternativas** | * Alternativa rechazada: Cloud Run o servicios serverless. Añade complejidad de red y costos variables. Adecuado para escala mayor en el futuro. * Alternativa rechazada: VM separada para el microservicio. Introduce latencia de red y costo adicional innecesario en Fase 1. |
| **Consecuencias** | * Positiva: despliegue simple con docker-compose up. * Positiva: el microservicio está aislado de internet por diseño. * Restricción: el archivo docker-compose.yml debe incluir health checks para ambos servicios. * Restricción: las credenciales nunca deben estar en el docker-compose.yml. Usar archivo .env excluido de control de versiones. * A monitorear: si el volumen de usuarios crece, evaluar migrar el microservicio a Cloud Run o GKE. |

# 3. Resumen de Decisiones

|  |  |  |  |
| --- | --- | --- | --- |
| **ADR** | **Decisión** | **Patrón / Tecnología** | **Estado** |
| ADR-01 | N8N como orquestador | HTTP Proxy / Routing | ✅ Aceptado |
| ADR-02 | Python + FastAPI | REST API + Pydantic v2 | ✅ Aceptado |
| ADR-03 | OAuth2 en el frontend | Stateless / BFF | ✅ Aceptado |
| ADR-04 | Abstract Provider + Factory | Strategy + Factory | ✅ Aceptado |
| ADR-05 | Listado recursivo con paginación interna | Recursive Traversal | ✅ Aceptado |
| ADR-06 | LIST y TRANSFER separados | Single Responsibility | ✅ Aceptado |
| ADR-07 | HTTP REST síncrono N8N ↔ Microservicio | Request/Response | ✅ Aceptado |
| ADR-08 | Versionado /api/v1/ en URL | URL Versioning | ✅ Aceptado |
| ADR-09 | Docker Compose en VM GCS | Container / IaC | ✅ Aceptado |

# 4. Documentos Relacionados

|  |  |  |
| --- | --- | --- |
| **Documento** | **Título** | **Descripción** |
| DOC-02 | Especificación de Componentes | Interfaces, clases abstractas y contratos internos del microservicio |
| DOC-03 | Especificación de API REST | OpenAPI completo: endpoints, schemas, códigos de error |
| DOC-04 | Modelo de Datos | Schemas Pydantic, estructuras de request/response |
| DOC-05 | Especificación de Infraestructura | Docker Compose, variables de entorno, red GCS |
| DOC-06 | Flujo N8N | Descripción nodo a nodo de los workflows de N8N |
| DOC-07 | Guía de Extensibilidad | Cómo agregar S3, Azure Blob u otros providers |

*— Fin del documento DOC-01 —*