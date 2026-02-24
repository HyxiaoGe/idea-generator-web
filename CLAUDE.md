# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Nano Banana Lab** is an AI Image & Video Generation API with multi-provider support. Built with FastAPI, it provides RESTful endpoints for text-to-image, text-to-video, image editing (blend/inpaint/outpaint), and chat-based iterative refinement.

Key capabilities: multi-provider abstraction (10+ providers), intelligent routing with fallback, async task pattern for long-running operations, optional PostgreSQL with graceful degradation to file storage, Redis-based quota/cooldown, ARQ background task queue, and pluggable storage (local/MinIO/OSS).

## Quick Reference Commands

The project uses **uv** as its package manager. All common operations have **Makefile targets**:

```bash
# Setup
make dev                    # Install dev deps + pre-commit hooks
make install                # Install production deps only

# Development
make run                    # Dev server with hot reload (port 8000)
make run-prod               # Production server (4 workers)

# Code Quality
make lint                   # Ruff check
make lint-fix               # Ruff check --fix
make format                 # Ruff format
make typecheck              # MyPy (api, services, core, database)
make security               # Bandit security scan
make check                  # lint + format-check + security (no typecheck)
make pre-commit             # Run all pre-commit hooks

# Testing
make test                   # All tests
make test-unit              # Unit tests only
make test-integration       # Integration tests only
make test-cov               # Tests with HTML coverage report

# Run a single test file or specific test
uv run pytest tests/unit/test_core.py -v
uv run pytest tests/integration/test_generate.py::test_generate_image -v

# Database
make migrate                # Apply all migrations (alembic upgrade head)
make migrate-down           # Rollback one migration
make migrate-new            # Create new migration (interactive prompt)

# Docker
make docker-run             # docker-compose up -d (api + arq worker)
make docker-down            # docker-compose down
make docker-logs            # Follow logs
```

## Architecture

```
api/                    FastAPI app, routers (18), schemas (18), dependencies, middleware
core/                   Config (Pydantic Settings), Redis, JWT security, exceptions
services/               Business logic, singleton getters in __init__.py
  providers/            Multi-provider abstraction (10+ providers)
  provider_router.py    Intelligent routing (priority/cost/quality/speed/round_robin/adaptive/region)
  generation_task.py    Async task pattern wrapper
  storage/              Pluggable storage (local/MinIO/OSS)
database/               Optional PostgreSQL - models (15), repositories, Alembic migrations
tests/                  Unit (16 files) + integration (8 files), fixtures in conftest.py
i18n/                   English/Chinese translations
api/workers.py          ARQ background task definitions
```

### Request Flow

1. Router receives request → validates with Pydantic schema
2. Auth dependency extracts user from JWT (if `AUTH_ENABLED`)
3. Quota service checks daily limit + cooldown via Redis
4. For generation: `ProviderRouter.route()` selects provider → `execute_with_fallback()` runs with retry
5. Long-running ops return `task_id` immediately → client polls `/api/tasks/{task_id}`
6. Results stored via pluggable storage → history saved to DB (if enabled) or file

### Providers

Image: Google Gemini, OpenAI, FLUX (BFL), Stability, Alibaba, ByteDance, Zhipu, MiniMax
Video: Runway ML, Kling AI
Each implements `ImageProvider` or `VideoProvider` protocol from `services/providers/base.py`.

## Code Patterns

### Service Singletons
Services are accessed via getter functions in `services/__init__.py`:
```python
from services import get_provider_router, get_quota_service, get_storage_manager
```

### Async Task Pattern
Generation endpoints use a task wrapper that returns immediately with a `task_id`:
```python
from services.generation_task import GenerationTaskService

task_service = GenerationTaskService(redis)
task_id = await task_service.create_task(user_id, task_type="generate")
# Client polls GET /api/tasks/{task_id} for status/result
```

The generate/blend/inpaint/outpaint/search endpoints all follow this pattern.

### Optional Database with Fallback
Database is optional (`DATABASE_ENABLED=false` by default). Repository dependencies yield `None` when DB is unavailable:
```python
@router.get("/history")
async def list_history(
    image_repo: Optional[ImageRepository] = Depends(get_image_repository),
):
    if image_repo:
        images = await image_repo.list_by_user(user_id, limit=20)
    else:
        storage = get_storage_manager()
        images = await storage.get_history(limit=20)
```

### Custom Exceptions
`core/exceptions.py` defines `AppException` base with `error_code` (machine-readable for i18n), `message`, and `status_code`. Subclasses: `AuthenticationError` (401), `QuotaExceededError` (429), `ContentBlockedError` (400/403), etc.

### Shared Preferences (prefhub)
User preferences extend `prefhub.schemas.preferences.BasePreferences` (language, theme, timezone). Domain fields defined in `api/schemas/preferences.py`. Service in `services/preferences_service.py`. Enums (`Language`, `Theme`, `HourCycle`) imported from `prefhub.schemas`, not defined locally.

## External Dependencies

Two git-based dependencies (not on PyPI):
- **auth-client**: `git+https://github.com/HyxiaoGe/auth-service.git#subdirectory=auth-client` — JWT/OAuth
- **prefhub**: `git+https://github.com/HyxiaoGe/prefhub.git` — Shared user preferences

## Environment Variables

**Required:** `SECRET_KEY` (JWT, 32+ chars), `REDIS_URL`, and at least one provider API key (`GOOGLE_API_KEY`, `PROVIDER_OPENAI_API_KEY`, or `PROVIDER_BFL_API_KEY`).

**Optional:** `DATABASE_ENABLED`/`DATABASE_URL` (PostgreSQL), `AUTH_ENABLED`/`AUTH_SERVICE_URL` (auth), `PROVIDER_*_ENABLED`/`PROVIDER_*_PRIORITY` (per-provider config), `DEFAULT_ROUTING_STRATEGY`, `ENABLE_FALLBACK`, `ENVIRONMENT` (development/staging/production).

## Code Style

- **Line length:** 100 (enforced by ruff)
- **Quote style:** double quotes
- **Python target:** 3.11+
- **Import sorting:** isort via ruff, first-party packages: `api`, `services`, `core`, `database`, `i18n`
- **Async:** `asyncio_mode = "auto"` in pytest — all async test functions run automatically
- **Pre-commit:** ruff check/format, bandit (security), standard hooks (trailing whitespace, private key detection)

## Testing

Fixtures in `tests/conftest.py` provide: `client`/`async_client`, `mock_redis` (in-memory), `mock_image_generator`, `mock_quota_service`, `mock_app_user`/`mock_admin_user`, `auth_headers`, `sample_generate_request`.

Coverage configured for `api`, `services`, `core`, `database` with branch coverage.

CI runs on Python 3.11 + 3.12 with Redis 7 and PostgreSQL 16 containers.

## API Endpoints

Core endpoints — use the `ig-backend-api-reference` skill for full reference:

- **Generation:** `POST /api/generate`, `/api/generate/batch`, `/api/generate/search`, `/api/video/generate`
- **Image editing:** `POST /api/generate/blend`, `/api/generate/inpaint`, `/api/generate/outpaint`, `/api/generate/describe`
- **Tasks:** `GET /api/tasks/{task_id}` (poll async generation status)
- **Chat:** `POST /api/chat`, `POST /api/chat/{id}/message`, `GET /api/chat/{id}`
- **Auth:** `/api/auth/login`, `/api/auth/callback`, `/api/auth/me`, `/api/auth/api-keys`
- **Templates:** CRUD at `/api/templates` with like/favorite/generate/enhance
- **Also:** `/api/quota`, `/api/history`, `/api/favorites`, `/api/preferences`, `/api/projects`, `/api/notifications`, `/api/analytics`, `/api/search`, `/api/models`, `/api/admin/*`, `WS /api/ws`

## Skills Documentation

Claude Code skills — update when code changes affect these areas:

| Skill | Path | Content |
|-------|------|---------|
| Project Overview | `~/.claude/skills/ig-project-overview/SKILL.md` | Features, tech stack |
| Architecture | `~/.claude/skills/ig-backend-architecture/SKILL.md` | Component interaction, data flow |
| Codebase Guide | `~/.claude/skills/ig-backend-codebase-guide/SKILL.md` | Directory structure, naming conventions |
| API Reference | `~/.claude/skills/ig-backend-api-reference/SKILL.md` | All endpoints, request/response formats |
| Frontend Guide | `~/.claude/skills/ig-frontend-api-guide/SKILL.md` | TypeScript types, SDK examples |
| Add Endpoint | `~/.claude/skills/ig-backend-add-endpoint/SKILL.md` | Step-by-step template |
| Add Model | `~/.claude/skills/ig-backend-add-model/SKILL.md` | Step-by-step template |
| Add Provider | `~/.claude/skills/ig-backend-add-provider/SKILL.md` | Step-by-step template |
