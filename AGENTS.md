# AGENTS Guide for buckets_reader

This file equips coding agents working on the ETL Bucket Service microservice.
Follow these instructions before touching code.

---

## Repository Snapshot

- `context/` hosts normative docs: read DOC-01 (ADRs) and DOC-02 before coding.
- Service target: Python 3.11 FastAPI app with async providers and Pydantic v2 models.
- Source tree expected: see DOC-02 section 2 for canonical layout under `app/` and `tests/`.
- No runtime code exists yet; new work must align with documented contracts.
- Deployment target is a VM with N8N (DOC-05); local development uses venv only.
- Version control: do not commit `.env` or secrets; follow `.gitignore` guidance.

---

## Environment & Setup

- Use Python 3.11+ only; earlier versions lack required typing features.
- Create isolated venv before installing deps; activating the venv is mandatory for tooling parity.
- Required pip packages are pinned in the spec; mirror them in `requirements.txt`.
- Upgrade pip before install to avoid resolver mismatches.

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## Core Commands

- Launch dev server:
  ```bash
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
  ```
- Run full test suite:
  ```bash
  pytest
  ```
- Run async tests (rely on pytest-asyncio — already in requirements).
- Target one test:
  ```bash
  pytest tests/providers/test_google_drive.py::TestListFiles::test_recursion
  ```
- Static analysis:
  ```bash
  pip install ruff      # if missing
  ruff check .
  ruff format .
  ```
- Type checking (once `mypy.ini` is introduced):
  ```bash
  mypy app tests --config-file mypy.ini
  ```
  Treat mypy warnings as blockers.
- Freeze dependencies after updates:
  ```bash
  pip freeze > requirements.txt
  ```
  Review the diff manually before committing.

---

## Verifying the Service Locally

- Health check (with server running):
  ```bash
  curl http://localhost:8000/health
  # Expected: {"status": "ok", "version": "1.0.0"}
  ```
- API docs available only when `APP_ENV=development`:
  ```
  http://localhost:8000/docs
  http://localhost:8000/redoc
  ```
- Set environment variables from `.env.example`:
  ```bash
  cp .env.example .env
  # Edit .env with real values, then:
  export $(cat .env | xargs)
  # Or use python-dotenv loading in config.py (already handled by pydantic-settings)
  ```

---

## Testing Guidance

- Prefer pytest classes grouped by unit under test (`TestValidateCredentials`, `TestListFiles`, etc.).
- Use `pytest.mark.asyncio` for async coroutines; avoid `asyncio.run` inside tests.
- Mock external SDK calls with asyncio-aware fixtures and `pytest-mock`.
- Providers require coverage for: credential validation, pagination, recursion depth, and error translation.
- Services should be tested with fake providers implementing the `BucketProvider` ABC.
- **No test may hit real Google APIs.** Enforce with fixtures that raise if network is accessed.

---

## Code Style

- Conform to PEP 8 with 100-character soft limit; wrap earlier for readability.
- Format using `ruff format` (black-compatible) for consistent whitespace and string quoting.
- Keep modules ASCII; only introduce Unicode when domain data demands it.
- Always start modules with `from __future__ import annotations` followed by standard library imports.
- Maintain module docstrings when behavior is non-trivial; avoid redundant boilerplate comments.
- Use dataclasses sparingly; Pydantic models already cover validation needs.

---

## Imports

- Order: stdlib → third-party → internal `app.*` → internal relative. Separate groups with one blank line.
- Prefer absolute imports from `app` instead of `..` except within tests where fixtures reside nearby.
- **Do not import providers directly inside services**; rely on `app.providers.factory.get_provider`.
- No wildcard imports.
- Lazily import heavy SDK modules inside functions when they are optional or slow to load.

---

## Typing & Data Models

- Every function signature must carry precise type hints; avoid `Any`.
- Use Pydantic models for structured payloads; never raw dict juggling.
- Enumerations go in `app/models/common.py`; extend `SourceType` and `AssetType` there only.
- Expose canonical extension mapping through `get_extensions_for_asset_types`.
- Ensure datetimes are timezone-aware UTC objects:
  ```python
  datetime.fromisoformat(value).astimezone(timezone.utc)
  ```

---

## Error Handling

- Define custom exceptions in `app/exceptions.py` exactly as outlined in DOC-02 §9.1.
- Translate third-party errors to domain exceptions before they bubble out of providers.
- HTTP layer maps exceptions to responses mirroring DOC-03 error schema.
- Never swallow errors silently; log context, raise typed exception, and let the router convert it.
- Use `UnsupportedProviderError` for unknown sources; message should cite `request.source`.
- Reserve `HTTPException` for FastAPI-level cross-cutting failures only.

---

## Logging & Observability

- Initialize logger via `logging.getLogger(__name__)`; no root logger usage.
- Log start and end of `list_files` with: `folder_id`, `extensions`, duration in milliseconds.
- **Never log tokens or credentials** in any log message.
- Emit structured info-level logs.
- Integrate `tenacity` retry logging to surface backoff attempts and outcomes.

---

## Providers & Services

- Providers must remain **stateless**; inject credentials at init and avoid caching user data.
- Build synchronous SDK calls through `asyncio.get_event_loop().run_in_executor` (ADR-10).
- Keep constants like Drive-specific MIME types near provider implementations.
- Services orchestrate providers but never inspect provider internals; return domain models only.
- All provider registry changes happen inside `get_provider`; update tests alongside.
- When adding providers, update DOC-07 checklist and requirements with pinned SDK versions.

---

## FastAPI Routers

- Routers live under `app/routers/`; each file registers an `APIRouter` with prefix `/api/v1`.
- Validate requests via Pydantic models; return instances of response schemas, not bare dicts.
- Register exception handlers in `app/main.py` for each custom exception class.
- `GET /health` is open to unauthenticated callers; include version string from settings.
- OpenAPI docs only expose when `APP_ENV == "development"`.

---

## Async IO & Concurrency

- Do not block the event loop; wrap synchronous SDK calls in `run_in_executor` (ADR-10).
- Limit recursion depth respecting `max_depth`; treat `None` as unlimited but guard against runaway loops.
- Avoid global state; rely on dependency-injected singletons where necessary.

---

## Configuration & Secrets

- Load settings exclusively through `pydantic-settings.Settings`; access via:
  ```python
  from app.config import settings
  ```
- Keep `.env` local; `.env.example` documents valid keys and defaults.
- Default `CORS_ALLOWED_ORIGINS` to `["*"]` only for development; override per environment.
- Any new configuration must be documented in `.env.example`.
- **Never require Google OAuth client secrets server-side** in Fase 1 (per ADR-03).

---

## API Contract Reminders

- Follow DOC-03 for JSON structure, including error envelopes and field casing.
- Responses must include `total_files`, `asset_types_requested`, and `extensions_searched`.
- All IDs remain opaque strings; never parse or infer structure.
- Maintain versioned path `/api/v1/bucket/...`; use new prefix for breaking changes.
- Return `HTTP 401` with code `INVALID_TOKEN` for rejected credentials; message in Spanish.
- Document new error codes in DOC-03 §5 and update client expectations.

---

## Extending the System

- Consult DOC-07 for provider checklist; follow steps 1–7 without skipping order.
- Update `ProviderCredentials` unions when new credential models are added.
- Add SDK dependencies with pinned versions; document in `requirements.txt` comments.
- Expand test coverage under `tests/providers/` and `tests/services/` for each new feature.
- Keep extensibility changes additive; modifying an existing contract indicates design drift.
- Coordinate ADR updates with the architecture team before altering foundational patterns.

---

## Documentation References

| Documento | Uso |
|---|---|
| DOC-01 | Architecture decisions — never overturn without a new ADR |
| DOC-02 | Component contracts — canonical source for module responsibilities |
| DOC-03 | REST contract — align responses and errors exactly |
| DOC-04 | Data models — Pydantic schemas source of truth |
| DOC-05 | Infrastructure — Docker Compose and deployment context |
| DOC-06 | N8N workflow — ensures routing assumptions stay valid |
| DOC-07 | Extensibility playbook — mandatory for new provider work |
| ADR-10 | SDK vs httpx decision — mandatory read before touching GoogleDriveProvider |

---

## Tooling & Editors

- Configure editor to trim trailing whitespace and insert newline at EOF.
- Enable `ruff` integration for on-save linting.
- Keep indentation at 4 spaces.
- Prefer terminals with UTF-8; ensure tests run on Linux to match prod.

---

## When In Doubt

- Re-read the relevant DOC-x document before coding.
- Request a new ADR when a change contradicts current decisions.
- Prefer explicitness over cleverness; the next agent must understand your code quickly.
- Leave TODOs only with owner and context.
- Keep this guide updated whenever workflow or style assumptions change.
