# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Nano Banana Lab** is an AI Image Generation API powered by Google Gemini. It provides RESTful API endpoints for various image generation capabilities.

**Core Features:**
- Text-to-image generation with multiple resolution options (1K, 2K, 4K)
- Multi-turn chat-based iterative image refinement
- Batch image generation with progress tracking
- Search-grounded generation with real-time data integration
- GitHub OAuth authentication with JWT tokens
- Redis-based quota management for trial users
- Cloudflare R2 cloud storage for images
- AI-powered prompt library

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
│                    services/ (Business Logic)                │
│   ├── generator.py       - Core image generation            │
│   ├── chat_session.py    - Multi-turn conversations         │
│   ├── auth_service.py    - GitHub OAuth                     │
│   ├── quota_service.py   - Redis quota management           │
│   ├── image_storage.py   - Local storage                    │
│   ├── r2_storage.py      - Cloudflare R2 storage            │
│   ├── prompt_generator.py- AI prompt generation             │
│   └── health_check.py    - API health monitoring            │
├─────────────────────────────────────────────────────────────┤
│              Google GenAI SDK (gemini-3-pro-image-preview)   │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
nano-banana-lab/
├── api/                   # FastAPI application
│   ├── main.py            # Application entry point
│   ├── routers/           # API route handlers
│   │   ├── auth.py        # Authentication endpoints
│   │   ├── generate.py    # Image generation endpoints
│   │   ├── quota.py       # Quota management
│   │   ├── chat.py        # Chat sessions
│   │   ├── history.py     # Image history
│   │   ├── prompts.py     # Prompt library
│   │   └── health.py      # Health checks
│   ├── schemas/           # Pydantic models
│   └── middleware/        # Error handlers
├── core/                  # Core configuration
│   ├── config.py          # Settings management
│   ├── exceptions.py      # Custom exceptions
│   ├── redis.py           # Redis client
│   └── security.py        # JWT handling
├── services/              # Business logic
│   ├── generator.py       # ImageGenerator class
│   ├── chat_session.py    # ChatSession class
│   ├── auth_service.py    # AuthService class
│   ├── quota_service.py   # QuotaService class
│   ├── image_storage.py   # Local storage
│   ├── r2_storage.py      # R2 cloud storage
│   ├── prompt_generator.py# AI prompt generation
│   ├── prompt_storage.py  # Prompt library storage
│   └── health_check.py    # Health checks
├── tests/                 # Test suite
│   ├── conftest.py        # Pytest fixtures
│   ├── unit/              # Unit tests
│   └── integration/       # API tests
├── i18n/                  # Internationalization
├── experiments/           # Standalone experiment scripts
├── docs/                  # Documentation
├── pyproject.toml         # Project configuration
├── Dockerfile             # Container configuration
├── docker-compose.yml     # Docker Compose
└── .env.example           # Environment template
```

## Quick Reference Commands

```bash
# Development server
uvicorn api.main:app --reload

# Run with specific port
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Run tests
pytest

# Run tests with coverage
pytest --cov=api --cov=services --cov-report=html

# Docker local development
docker-compose up -d

# Docker build
docker build -t nano-banana-lab .
docker run -p 8000:8000 -e GOOGLE_API_KEY=your_key nano-banana-lab

# Install dependencies
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"
```

## Key Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.11+ | Runtime |
| FastAPI | >=0.115.0 | Web framework |
| Pydantic | >=2.0.0 | Data validation |
| Redis | >=5.0.0 | Cache & sessions |
| google-genai | >=1.0.0 | Gemini API SDK |
| Pillow | >=10.0.0 | Image processing |
| boto3 | >=1.34.0 | R2 storage (S3) |
| python-jose | >=3.3.0 | JWT tokens |
| httpx | >=0.27.0 | Async HTTP |
| pytest | >=8.0.0 | Testing |

**AI Models:**
- `gemini-3-pro-image-preview` - Image generation
- `gemini-2.0-flash` - Health checks and prompt generation

## Environment Variables

Required:
```
GOOGLE_API_KEY              # Google Gemini API key
SECRET_KEY                  # JWT signing key (32+ chars)
REDIS_URL                   # Redis connection URL
```

Optional - Server:
```
HOST                        # Server host (default: 0.0.0.0)
PORT                        # Server port (default: 8000)
ENVIRONMENT                 # development/production
DEBUG                       # Enable debug mode
```

Optional - Cloudflare R2:
```
R2_ENABLED                  # Enable cloud storage (true/false)
R2_ACCOUNT_ID               # Cloudflare account ID
R2_ACCESS_KEY_ID            # R2 access key
R2_SECRET_ACCESS_KEY        # R2 secret key
R2_BUCKET_NAME              # Bucket name
R2_PUBLIC_URL               # Public URL for images
```

Optional - GitHub OAuth:
```
AUTH_ENABLED                # Enable OAuth (true/false)
GITHUB_CLIENT_ID            # GitHub OAuth app client ID
GITHUB_CLIENT_SECRET        # GitHub OAuth app client secret
GITHUB_REDIRECT_URI         # OAuth callback URL
```

Optional - Trial Mode:
```
TRIAL_ENABLED               # Enable trial mode (true/false)
TRIAL_GLOBAL_QUOTA          # Global daily quota (default: 50)
TRIAL_COOLDOWN_SECONDS      # Cooldown between generations
```

## API Endpoints

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Basic health check |
| GET | `/api/health/detailed` | Detailed status |
| GET | `/api/health/ready` | Readiness probe |
| GET | `/api/health/live` | Liveness probe |

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/login` | Get OAuth URL |
| POST | `/api/auth/callback` | OAuth callback |
| GET | `/api/auth/me` | Current user |
| POST | `/api/auth/logout` | Logout |

### Image Generation
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/generate` | Generate image |
| POST | `/api/generate/batch` | Batch generation |
| GET | `/api/generate/task/{id}` | Task progress |
| POST | `/api/generate/search` | Search-grounded |

### Quota
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/quota` | Quota status |
| POST | `/api/quota/check` | Check availability |
| GET | `/api/quota/config` | Configuration |

### Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Create session |
| GET | `/api/chat` | List sessions |
| POST | `/api/chat/{id}/message` | Send message |
| GET | `/api/chat/{id}` | Get history |
| DELETE | `/api/chat/{id}` | Delete session |

### History
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/history` | List history |
| GET | `/api/history/stats` | Statistics |
| GET | `/api/history/{id}` | Get detail |
| GET | `/api/history/{id}/image` | Get image |
| DELETE | `/api/history/{id}` | Delete item |

### Prompts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prompts` | List prompts |
| POST | `/api/prompts` | Save custom |
| GET | `/api/prompts/categories` | Categories |
| POST | `/api/prompts/generate` | AI generate |
| POST | `/api/prompts/{id}/favorite` | Toggle favorite |
| DELETE | `/api/prompts/{id}` | Delete prompt |

## Code Conventions

### Naming Conventions
- **Classes:** PascalCase (`ImageGenerator`, `QuotaService`)
- **Functions:** snake_case (`generate_image()`, `check_quota()`)
- **Constants:** UPPER_SNAKE_CASE (`MAX_RETRIES`, `MODEL_ID`)
- **API paths:** kebab-case (`/api/health/ready`)

### Patterns Used

**1. Service Layer Pattern**
Services in `services/` contain business logic separated from API handlers:
```python
from services import ImageGenerator, get_quota_service
```

**2. Dependency Injection**
FastAPI dependencies for authentication and services:
```python
async def get_current_user(authorization: str = Header(None)) -> GitHubUser:
    ...
```

**3. Pydantic Schemas**
Request/response validation with Pydantic models:
```python
class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    settings: GenerationSettings
```

**4. Error Handling**
Custom exceptions with global handlers:
```python
raise QuotaExceededError(message="Daily quota exceeded")
```

**5. Error Handling with Retry**
Network operations use retry logic with exponential backoff:
- Max attempts: 3
- Backoff delays: [2s, 4s, 8s]
- Retryable errors: Connection issues, timeout, 502/503/504 errors

### Important Files

| File | Purpose |
|------|---------|
| `api/main.py` | FastAPI app entry, lifespan, routers |
| `core/config.py` | Pydantic Settings configuration |
| `core/security.py` | JWT token creation/verification |
| `services/generator.py` | Core `ImageGenerator` class |
| `services/chat_session.py` | `ChatSession` for multi-turn |
| `services/auth_service.py` | GitHub OAuth with httpx |
| `services/quota_service.py` | Redis-based quota management |
| `services/r2_storage.py` | Cloudflare R2 integration |

## Testing

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_core.py

# Run with coverage
pytest --cov=api --cov=services

# Generate HTML coverage report
pytest --cov-report=html
```

## Deployment

**Supported Platforms:**
- Docker (any container platform)
- Railway (`railway.json`)
- Render (`render.yaml`)
- Google Cloud Run
- AWS ECS/Fargate

**Required Services:**
- Redis (for sessions and quota tracking)

**Startup command:**
```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

**Health check endpoint:**
```
GET /api/health
```

**Docker health check:**
```
curl --fail http://localhost:8000/api/health
```

## Security Notes

- JWT tokens for authentication (32+ char secret key)
- API keys can be passed via `X-API-Key` header
- CORS configured via environment variables
- Redis for secure session storage
- `.env` files excluded from git

## Common Tasks

### Adding a New API Endpoint
1. Create schema in `api/schemas/`
2. Create router in `api/routers/`
3. Export from `__init__.py` files
4. Register router in `api/main.py`
5. Add tests in `tests/integration/`

### Adding New Service
1. Create file in `services/`
2. Implement service class with singleton getter
3. Export from `services/__init__.py`

### Modifying Image Generation
Core generation logic is in `services/generator.py`:
- `generate()` - Basic text-to-image
- `blend_images()` - Multi-image blending
- `generate_with_search()` - Search-grounded generation

## Error Handling

**Retryable errors (automatic retry):**
- Connection errors
- Timeout errors
- HTTP 502/503/504 (server overloaded)

**Non-retryable errors (immediate failure):**
- Invalid API key (401)
- Quota exceeded (429)
- Safety content blocked
- Invalid request parameters
