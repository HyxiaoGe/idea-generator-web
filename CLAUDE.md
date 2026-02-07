# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Nano Banana Lab** is an AI Image & Video Generation API with multi-provider support. It provides RESTful API endpoints for various generation capabilities.

**Core Features:**
- Multi-provider abstraction layer (Google Gemini, OpenAI, FLUX, Runway, Kling)
- Intelligent provider routing with strategies (priority, cost, quality, speed)
- Text-to-image generation with multiple resolution options (1K, 2K, 4K)
- Text-to-video generation (provider-dependent)
- Multi-turn chat-based iterative image refinement
- Batch image generation with progress tracking
- Search-grounded generation with real-time data integration
- GitHub OAuth authentication with JWT tokens
- Redis-based per-user daily quota with cooldown (abuse prevention)
- Cloudflare R2 cloud storage for images
- AI-powered prompt library with content moderation

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
│                      (api/main.py)                          │
├─────────────────────────────────────────────────────────────┤
│   api/routers/          │        api/schemas/               │
│   ├── health.py         │        ├── common.py              │
│   ├── auth.py           │        ├── auth.py                │
│   ├── generate.py       │        ├── generate.py            │
│   ├── video.py          │        ├── video.py               │
│   ├── quota.py          │        ├── quota.py               │
│   ├── chat.py           │        ├── chat.py                │
│   ├── history.py        │        ├── history.py             │
│   └── prompts.py        │        └── prompts.py             │
├─────────────────────────┴───────────────────────────────────┤
│                    core/ (Configuration)                     │
│   ├── config.py          - Pydantic Settings                │
│   ├── exceptions.py      - Custom exceptions                │
│   ├── redis.py           - Redis connection                 │
│   └── security.py        - JWT tokens                       │
├─────────────────────────────────────────────────────────────┤
│                    database/ (PostgreSQL - Optional)         │
│   ├── __init__.py        - Connection management            │
│   ├── models/            - SQLAlchemy ORM models            │
│   │   ├── user.py        - User (GitHub OAuth)              │
│   │   ├── image.py       - GeneratedImage (history)         │
│   │   ├── chat.py        - ChatSession, ChatMessage         │
│   │   ├── quota.py       - QuotaUsage                       │
│   │   ├── prompt.py      - Prompt, UserFavoritePrompt       │
│   │   └── audit.py       - AuditLog, ProviderHealthLog      │
│   ├── repositories/      - Data access layer                │
│   │   ├── user_repo.py   - User CRUD                        │
│   │   ├── image_repo.py  - Image history CRUD               │
│   │   ├── chat_repo.py   - Chat session CRUD                │
│   │   └── ...                                               │
│   └── migrations/        - Alembic migrations               │
├─────────────────────────────────────────────────────────────┤
│                    services/ (Business Logic)                │
│   ├── provider_router.py - Intelligent provider routing     │
│   ├── providers/         - Multi-provider abstraction       │
│   │   ├── base.py        - Base protocols & data classes    │
│   │   ├── registry.py    - Provider registry                │
│   │   ├── google.py      - Google Gemini provider           │
│   │   ├── openai.py      - OpenAI/OpenRouter provider       │
│   │   ├── flux.py        - FLUX (Black Forest Labs)         │
│   │   ├── runway.py      - Runway ML (video)                │
│   │   └── kling.py       - Kling AI (video)                 │
│   ├── generator.py       - Legacy image generation          │
│   ├── chat_session.py    - Multi-turn conversations         │
│   ├── quota_service.py   - Per-user daily quota + cooldown   │
│   ├── r2_storage.py      - Cloudflare R2 storage            │
│   ├── content_filter.py  - Content moderation               │
│   └── ai_content_moderator.py - AI-based moderation         │
└─────────────────────────────────────────────────────────────┘
```

## Quick Reference Commands

```bash
# Development server
uvicorn api.main:app --reload

# Run tests
pytest

# Run single test file
pytest tests/unit/test_core.py -v

# Run specific test
pytest tests/integration/test_generate.py::test_generate_image -v

# Run with coverage
pytest --cov=api --cov=services --cov-report=html

# Linting
ruff check .
ruff format .

# Type checking
mypy api services core database

# Install dependencies
pip install -e ".[dev]"

# Docker
docker-compose up -d

# Database migrations (requires DATABASE_URL)
alembic upgrade head           # Apply all migrations
alembic downgrade -1           # Rollback one migration
alembic revision --autogenerate -m "description"  # Create new migration
```

## Environment Variables

Required:
```
SECRET_KEY                  # JWT signing key (32+ chars)
REDIS_URL                   # Redis connection URL
```

At least one provider API key is required:
```
GOOGLE_API_KEY              # Google Gemini API key
PROVIDER_OPENAI_API_KEY     # OpenAI API key (or OpenRouter)
PROVIDER_BFL_API_KEY        # FLUX (Black Forest Labs) API key
```

Optional - Provider Configuration:
```
PROVIDER_GOOGLE_ENABLED     # Enable Google provider (default: true)
PROVIDER_GOOGLE_PRIORITY    # Priority (lower = higher priority)
PROVIDER_OPENAI_ENABLED     # Enable OpenAI provider
PROVIDER_OPENAI_BASE_URL    # Custom base URL (for OpenRouter, etc.)
PROVIDER_BFL_ENABLED        # Enable FLUX provider
DEFAULT_ROUTING_STRATEGY    # priority|cost|quality|speed|round_robin
ENABLE_FALLBACK             # Enable automatic provider failover
```

Optional - Storage & Auth:
```
R2_ENABLED                  # Enable Cloudflare R2 cloud storage
AUTH_ENABLED                # Enable GitHub OAuth
```

Optional - PostgreSQL Database:
```
DATABASE_ENABLED            # Enable PostgreSQL (default: false)
DATABASE_URL                # postgresql+asyncpg://user:pass@host:port/db
DB_POOL_SIZE                # Connection pool size (default: 5)
DB_MAX_OVERFLOW             # Max overflow connections (default: 10)
```

## API Endpoints

### Core Generation
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/generate` | Generate image |
| POST | `/api/generate/batch` | Batch generation |
| POST | `/api/generate/search` | Search-grounded |
| POST | `/api/video/generate` | Generate video |

### Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Create session |
| POST | `/api/chat/{id}/message` | Send message |
| GET | `/api/chat/{id}` | Get history |

### Authentication & API Keys
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/login` | Get GitHub authorization URL |
| POST | `/api/auth/callback` | Handle OAuth callback |
| GET | `/api/auth/me` | Get current user |
| POST | `/api/auth/logout` | Logout user |
| POST | `/api/auth/refresh` | Refresh JWT token |
| GET | `/api/auth/api-keys` | List API keys |
| POST | `/api/auth/api-keys` | Create API key |
| DELETE | `/api/auth/api-keys/{id}` | Delete API key |

### User Settings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings` | Get user settings |
| PUT | `/api/settings` | Update user settings |
| GET | `/api/settings/providers` | Get provider preferences |
| PUT | `/api/settings/providers` | Update provider preferences |

### Favorites
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/favorites` | List favorites |
| POST | `/api/favorites` | Add favorite |
| DELETE | `/api/favorites/{id}` | Remove favorite |
| POST | `/api/favorites/bulk` | Bulk operations |
| GET | `/api/favorites/folders` | List folders |
| POST | `/api/favorites/folders` | Create folder |

### Templates
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/templates` | List templates |
| POST | `/api/templates` | Create template |
| GET | `/api/templates/{id}` | Get template |
| PUT | `/api/templates/{id}` | Update template |
| DELETE | `/api/templates/{id}` | Delete template |
| POST | `/api/templates/{id}/use` | Use template |
| GET | `/api/templates/public` | Public templates |

### Projects
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects` | List projects |
| POST | `/api/projects` | Create project |
| GET | `/api/projects/{id}` | Get project |
| PUT | `/api/projects/{id}` | Update project |
| DELETE | `/api/projects/{id}` | Delete project |
| GET | `/api/projects/{id}/images` | List project images |
| POST | `/api/projects/{id}/images` | Add image to project |

### Notifications
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/notifications` | List notifications |
| GET | `/api/notifications/unread-count` | Get unread count |
| POST | `/api/notifications/mark-read` | Mark as read |
| POST | `/api/notifications/mark-all-read` | Mark all as read |
| DELETE | `/api/notifications/{id}` | Delete notification |

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analytics/overview` | Overall statistics |
| GET | `/api/analytics/usage` | Usage statistics |
| GET | `/api/analytics/costs` | Cost analysis |
| GET | `/api/analytics/providers` | Provider stats |
| GET | `/api/analytics/trends` | Trend analysis |

### Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/search` | Global search |
| GET | `/api/search/images` | Search images |
| GET | `/api/search/prompts` | Search prompts |
| GET | `/api/search/suggestions` | Search suggestions |

### WebSocket
| Protocol | Endpoint | Description |
|----------|----------|-------------|
| WS | `/api/ws` | Real-time updates |

### Admin (Requires admin privileges)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/users` | List users |
| GET | `/api/admin/users/{id}` | Get user details |
| PUT | `/api/admin/users/{id}/tier` | Update user tier |
| PUT | `/api/admin/users/{id}/quota` | Adjust quota |
| GET | `/api/admin/providers` | List providers |
| POST | `/api/admin/providers/{name}/enable` | Enable provider |
| GET | `/api/admin/system/status` | System status |
| GET | `/api/admin/system/metrics` | System metrics |
| POST | `/api/admin/quota/reset/{user_id}` | Reset user quota |
| POST | `/api/admin/announcements` | Create announcement |

### Supporting Endpoints
- `/api/health` - Health checks (basic, detailed, ready, live)
- `/api/quota` - Quota management (status, check, config)
- `/api/history` - Generation history
- `/api/prompts` - Prompt library

## Code Patterns

### Service Layer with Singleton Pattern
Services are accessed via getter functions that return singleton instances:
```python
from services import get_quota_service, get_provider_router

quota = get_quota_service()
router = get_provider_router()
```

### Multi-Provider System
New generation requests should use the `ProviderRouter` for intelligent routing:
```python
from services import get_provider_router, GenerationRequest

router = get_provider_router()
request = GenerationRequest(prompt="...", resolution="1K")
decision = await router.route(request)
result = await router.execute_with_fallback(request, decision)
```

Routing strategies: `priority`, `cost`, `quality`, `speed`, `round_robin`

### Adding a New Provider
1. Create provider class in `services/providers/` implementing `ImageProvider` or `VideoProvider`
2. Add registration logic in `ProviderRouter._register_providers()`
3. Add config settings in `core/config.py`

### Adding a New API Endpoint
1. Create schema in `api/schemas/`
2. Create router in `api/routers/`
3. Export from `__init__.py` files
4. Register router in `api/main.py`
5. Add tests in `tests/integration/`

### Error Handling with Retry
Network operations use automatic retry with exponential backoff:
- Max attempts: 3
- Backoff delays: [2s, 4s, 8s]
- Retryable: Connection errors, timeout, 502/503/504

### Database Access Pattern
When PostgreSQL is enabled, use repository pattern via dependency injection:
```python
from api.dependencies import get_image_repository
from database.repositories import ImageRepository

@router.get("/history")
async def list_history(
    image_repo: Optional[ImageRepository] = Depends(get_image_repository),
):
    if image_repo:
        # Use database
        images = await image_repo.list_by_user(user_id, limit=20)
    else:
        # Fallback to file storage
        storage = get_storage_manager()
        images = await storage.get_history(limit=20)
```

Database is optional - when not configured, services fall back to file-based storage.

## Testing

Tests use pytest with async support. Fixtures in `tests/conftest.py` provide:
- `client` / `async_client` - Test clients
- `mock_redis` - In-memory Redis mock
- `mock_image_generator`, `mock_r2_storage`, etc.

```bash
# Run all tests
pytest

# Run specific test
pytest tests/integration/test_generate.py::test_generate_image -v

# With coverage report
pytest --cov=api --cov=services --cov-report=html
```

## Deployment

**Required:** Redis (for sessions and quota tracking)

**Optional:** PostgreSQL (for persistent history, chat sessions, analytics)

**Startup:**
```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

**Database Setup (if using PostgreSQL):**
```bash
# Create database
createdb idea_generator

# Run migrations
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/idea_generator alembic upgrade head
```

**Health check:** `GET /api/health`

## Skills Documentation

Claude Code skills 文档，代码变更时需同步更新：

| Skill | 路径 | 内容 |
|-------|------|------|
| 项目概览 | `~/.claude/skills/ig-project-overview/SKILL.md` | 项目介绍、功能列表、技术栈 |
| 系统架构 | `~/.claude/skills/ig-backend-architecture/SKILL.md` | 架构图、多提供商系统、数据流 |
| 代码导航 | `~/.claude/skills/ig-backend-codebase-guide/SKILL.md` | 目录结构、按功能查找、命名约定 |
| API 参考 | `~/.claude/skills/ig-backend-api-reference/SKILL.md` | 所有端点列表、请求头、状态码 |
| 前端对接 | `~/.claude/skills/ig-frontend-api-guide/SKILL.md` | TypeScript 类型、调用示例、SDK |
| 添加端点 | `~/.claude/skills/ig-backend-add-endpoint/SKILL.md` | 新建 API 端点步骤模板 |
| 添加模型 | `~/.claude/skills/ig-backend-add-model/SKILL.md` | 新建数据库模型步骤模板 |
| 添加提供商 | `~/.claude/skills/ig-backend-add-provider/SKILL.md` | 新建 AI 提供商步骤模板 |
