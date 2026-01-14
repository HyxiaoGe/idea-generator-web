# Nano Banana Lab - FastAPI 迁移实施计划

## 概述

本文档详细描述了将 Nano Banana Lab 从 Streamlit 迁移到 FastAPI 的完整实施计划。

**目标**：移除 Streamlit 依赖，构建纯 API 后端服务，为前端应用提供 RESTful API 接口。

---

## 一、技术栈选型

### 核心框架

| 组件 | 选型 | 版本 | 说明 |
|------|------|------|------|
| Web 框架 | FastAPI | ^0.115.0 | 高性能异步框架，自动 OpenAPI 文档 |
| ASGI 服务器 | Uvicorn | ^0.32.0 | 高性能异步服务器 |
| 数据验证 | Pydantic | ^2.0 | FastAPI 内置，类型安全 |

### 认证 & 安全

| 组件 | 选型 | 版本 | 说明 |
|------|------|------|------|
| JWT | python-jose[cryptography] | ^3.3.0 | JWT Token 生成/验证 |
| HTTP 客户端 | httpx | ^0.27.0 | 异步 OAuth 回调 |
| 密码哈希 | passlib[bcrypt] | ^1.7.4 | 可选，未来用户系统 |

### 数据存储

| 组件 | 选型 | 版本 | 说明 |
|------|------|------|------|
| 缓存/会话 | Redis | ^5.0.0 | 会话管理、配额追踪、任务状态 |
| 异步 Redis | redis[hiredis] | ^5.0.0 | 高性能异步客户端 |
| 云存储 | boto3 | ^1.34.0 | 复用现有 R2 存储 |

### 任务队列 (可选)

| 组件 | 选型 | 版本 | 说明 |
|------|------|------|------|
| 任务队列 | arq | ^0.26.0 | 轻量级异步任务队列 |
| 备选方案 | Celery | ^5.4.0 | 重量级，功能更全 |

### 现有依赖 (保留)

| 组件 | 版本 | 说明 |
|------|------|------|
| google-genai | ^1.0.0 | Gemini API SDK |
| Pillow | ^10.0.0 | 图像处理 |
| python-dotenv | ^1.0.0 | 环境变量 |

---

## 二、项目结构设计

```
nano-banana-lab/
├── api/                           # FastAPI 应用目录
│   ├── __init__.py
│   ├── main.py                    # FastAPI 应用入口
│   ├── config.py                  # 配置管理 (Pydantic Settings)
│   ├── dependencies.py            # 依赖注入
│   │
│   ├── routers/                   # API 路由模块
│   │   ├── __init__.py
│   │   ├── auth.py                # 认证路由 (/api/auth/*)
│   │   ├── generate.py            # 图像生成路由 (/api/generate/*)
│   │   ├── chat.py                # 聊天会话路由 (/api/chat/*)
│   │   ├── history.py             # 历史记录路由 (/api/history/*)
│   │   ├── prompts.py             # 提示词库路由 (/api/prompts/*)
│   │   ├── quota.py               # 配额管理路由 (/api/quota/*)
│   │   └── health.py              # 健康检查路由 (/api/health)
│   │
│   ├── schemas/                   # Pydantic 数据模型
│   │   ├── __init__.py
│   │   ├── auth.py                # 认证相关模型
│   │   ├── generate.py            # 生成相关模型
│   │   ├── chat.py                # 聊天相关模型
│   │   ├── history.py             # 历史相关模型
│   │   ├── prompts.py             # 提示词相关模型
│   │   ├── quota.py               # 配额相关模型
│   │   └── common.py              # 通用响应模型
│   │
│   └── middleware/                # 中间件
│       ├── __init__.py
│       ├── auth.py                # JWT 认证中间件
│       ├── rate_limit.py          # 速率限制中间件
│       └── error_handler.py       # 全局错误处理
│
├── core/                          # 核心模块 (新建)
│   ├── __init__.py
│   ├── security.py                # JWT & 安全工具
│   ├── redis.py                   # Redis 连接管理
│   └── exceptions.py              # 自定义异常
│
├── services/                      # 业务逻辑 (重构/复用)
│   ├── __init__.py                # 导出重构
│   ├── generator.py               # ✅ 直接复用 (移除 translator 参数)
│   ├── chat_session.py            # ✅ 直接复用
│   ├── cost_estimator.py          # ✅ 直接复用
│   ├── content_filter.py          # ✅ 直接复用
│   ├── ai_content_moderator.py    # ✅ 直接复用
│   ├── prompt_generator.py        # ✅ 直接复用
│   ├── r2_storage.py              # ⚠️ 移除 streamlit 导入
│   ├── image_storage.py           # ⚠️ 移除 streamlit 导入
│   ├── prompt_storage.py          # ⚠️ 移除 streamlit 导入
│   ├── auth_service.py            # 🔄 重写 (移除 streamlit-oauth)
│   ├── quota_service.py           # 🔄 重写 (使用 Redis 后端)
│   ├── session_service.py         # 🆕 新建 (管理聊天会话持久化)
│   └── health_check.py            # ⚠️ 移除 session_state
│
├── i18n/                          # ✅ 直接复用
│   ├── __init__.py
│   ├── en.json
│   └── zh.json
│
├── tests/                         # 测试 (新建)
│   ├── __init__.py
│   ├── conftest.py                # pytest fixtures
│   ├── test_auth.py
│   ├── test_generate.py
│   ├── test_chat.py
│   └── test_quota.py
│
├── scripts/                       # 工具脚本
│   ├── init_prompts.py            # ✅ 复用
│   └── migrate_data.py            # 🆕 数据迁移脚本
│
├── docs/                          # 文档
│   ├── FASTAPI_MIGRATION_PLAN.md  # 本文档
│   └── API.md                     # API 文档
│
├── .env.example                   # 环境变量模板 (更新)
├── requirements.txt               # 依赖 (更新)
├── requirements-dev.txt           # 开发依赖 (新建)
├── Dockerfile                     # Docker 配置 (更新)
├── docker-compose.yml             # Docker Compose (更新)
└── README.md                      # 项目说明 (更新)

# 以下目录/文件将被移除
# ├── app.py                       # ❌ Streamlit 入口
# ├── components/                  # ❌ Streamlit UI 组件
# ├── .streamlit/                  # ❌ Streamlit 配置
```

---

## 三、API 端点设计

### 3.1 认证模块 `/api/auth`

```yaml
# GitHub OAuth 登录
POST /api/auth/github/login
  Request: {}
  Response: { redirect_url: string }

# OAuth 回调
POST /api/auth/github/callback
  Request: { code: string, state?: string }
  Response: {
    access_token: string,
    token_type: "bearer",
    user: { id, login, name, email, avatar_url }
  }

# 获取当前用户
GET /api/auth/me
  Headers: Authorization: Bearer <token>
  Response: { id, login, name, email, avatar_url, user_folder_id }

# 登出 (可选，JWT 无状态)
POST /api/auth/logout
  Headers: Authorization: Bearer <token>
  Response: { success: true }

# 刷新 Token (可选)
POST /api/auth/refresh
  Request: { refresh_token: string }
  Response: { access_token: string, token_type: "bearer" }
```

### 3.2 图像生成模块 `/api/generate`

```yaml
# 基础生成
POST /api/generate/basic
  Headers:
    Authorization: Bearer <token>  # 可选，用于配额追踪
    X-API-Key: <google_api_key>    # 可选，用户自带 key
  Request: {
    prompt: string,                # 必填，生成提示词
    aspect_ratio: "1:1" | "16:9" | "9:16" | "4:3" | "3:4",  # 默认 "16:9"
    resolution: "1K" | "2K" | "4K",                         # 默认 "1K"
    safety_level: "strict" | "moderate" | "relaxed" | "none",  # 默认 "moderate"
    enable_thinking: boolean,      # 默认 false
    save_to_history: boolean       # 默认 true
  }
  Response: {
    success: boolean,
    data: {
      image_url: string,           # 图片 URL (R2 公开链接)
      image_base64?: string,       # Base64 编码 (可选返回)
      text_response?: string,      # 模型文本响应
      thinking?: string,           # 思考过程
      duration: number,            # 生成耗时(秒)
      history_id?: string          # 历史记录 ID
    },
    error?: {
      code: string,                # 错误代码
      message: string,             # 错误消息
      type: string                 # 错误类型 (用于 i18n)
    }
  }

# 搜索增强生成
POST /api/generate/search
  Request: {
    prompt: string,
    aspect_ratio: string,
    safety_level: string,
    save_to_history: boolean
  }
  Response: {
    ...同上,
    data: {
      ...,
      search_sources?: string      # 搜索来源 HTML
    }
  }

# 图像混合
POST /api/generate/blend
  Request: {
    prompt: string,
    images: string[],              # Base64 编码的图片数组 (最多 14 张)
    aspect_ratio: string,
    safety_level: string,
    save_to_history: boolean
  }
  Response: { ...同基础生成 }

# 批量生成
POST /api/generate/batch
  Request: {
    prompt: string,
    count: number,                 # 生成数量 (1-10)
    aspect_ratio: string,
    resolution: string,
    safety_level: string,
    save_to_history: boolean
  }
  Response: {
    success: boolean,
    data: {
      task_id: string,             # 任务 ID (用于轮询)
      status: "pending" | "processing" | "completed" | "failed",
      total: number,
      completed: number,
      results: [...]               # 已完成的结果
    }
  }

# 获取批量任务状态
GET /api/generate/batch/{task_id}
  Response: { ...同上 }
```

### 3.3 聊天会话模块 `/api/chat`

```yaml
# 创建新会话
POST /api/chat/sessions
  Request: {
    aspect_ratio: string           # 默认宽高比
  }
  Response: {
    session_id: string,
    created_at: string,
    aspect_ratio: string
  }

# 获取会话列表
GET /api/chat/sessions
  Query: { limit?: number, offset?: number }
  Response: {
    sessions: [{
      session_id: string,
      created_at: string,
      message_count: number,
      last_message_at?: string,
      preview_prompt?: string
    }],
    total: number
  }

# 获取单个会话详情
GET /api/chat/sessions/{session_id}
  Response: {
    session_id: string,
    created_at: string,
    messages: [{
      role: "user" | "assistant",
      content: string,
      image_url?: string,
      thinking?: string,
      timestamp: string
    }]
  }

# 发送消息
POST /api/chat/sessions/{session_id}/messages
  Request: {
    message: string,
    aspect_ratio?: string,         # 覆盖会话默认值
    safety_level?: string
  }
  Response: {
    role: "assistant",
    content?: string,
    image_url?: string,
    thinking?: string,
    duration: number,
    timestamp: string
  }

# 删除会话
DELETE /api/chat/sessions/{session_id}
  Response: { success: true }

# 导出会话
GET /api/chat/sessions/{session_id}/export
  Query: { format: "json" | "markdown" }
  Response: 文件下载
```

### 3.4 历史记录模块 `/api/history`

```yaml
# 获取历史列表
GET /api/history
  Query: {
    limit?: number,                # 默认 20
    offset?: number,               # 默认 0
    mode?: string,                 # 过滤模式
    search?: string,               # 搜索关键词
    sort?: "newest" | "oldest",    # 排序
    date_from?: string,            # 日期范围
    date_to?: string
  }
  Response: {
    items: [{
      id: string,                  # 唯一标识 (R2 key)
      prompt: string,
      image_url: string,
      thumbnail_url?: string,
      mode: string,
      settings: { aspect_ratio, resolution },
      duration: number,
      created_at: string,
      session_id?: string          # 聊天会话 ID
    }],
    total: number,
    has_more: boolean
  }

# 获取单条记录
GET /api/history/{id}
  Response: {
    id: string,
    prompt: string,
    image_url: string,
    text_response?: string,
    thinking?: string,
    mode: string,
    settings: {...},
    duration: number,
    created_at: string
  }

# 删除记录
DELETE /api/history/{id}
  Response: { success: true }

# 批量删除
DELETE /api/history
  Request: { ids: string[] }
  Response: { success: true, deleted_count: number }

# 清空历史
DELETE /api/history/all
  Response: { success: true }
```

### 3.5 提示词库模块 `/api/prompts`

```yaml
# 获取提示词列表
GET /api/prompts
  Query: {
    category?: string,             # 分类过滤
    search?: string,               # 搜索关键词
    favorites_only?: boolean       # 仅收藏
  }
  Response: {
    prompts: [{
      id: string,
      title: string,
      prompt: string,
      category: string,
      tags: string[],
      is_favorite: boolean,
      created_at: string
    }],
    categories: string[]           # 所有分类
  }

# 生成提示词 (AI)
POST /api/prompts/generate
  Request: {
    category: string,
    style?: string,
    count?: number                 # 默认 5
  }
  Response: {
    prompts: [{
      title: string,
      prompt: string,
      tags: string[]
    }]
  }

# 收藏/取消收藏
POST /api/prompts/{id}/favorite
  Request: { is_favorite: boolean }
  Response: { success: true }

# 创建自定义提示词
POST /api/prompts
  Request: {
    title: string,
    prompt: string,
    category: string,
    tags?: string[]
  }
  Response: { id: string, ...prompt }

# 删除提示词
DELETE /api/prompts/{id}
  Response: { success: true }
```

### 3.6 配额模块 `/api/quota`

```yaml
# 获取配额状态
GET /api/quota
  Response: {
    is_trial_mode: boolean,
    global: {
      used: number,
      limit: number,
      remaining: number
    },
    modes: {
      [mode_key]: {
        name: string,
        used: number,
        limit: number,
        remaining: number,
        cost: number
      }
    },
    cooldown: {
      active: boolean,
      remaining_seconds: number
    },
    resets_at: string              # UTC 重置时间
  }

# 检查是否可生成 (预检)
POST /api/quota/check
  Request: {
    mode: string,
    resolution?: string,
    count?: number
  }
  Response: {
    can_generate: boolean,
    reason?: string,
    quota_info: {...}
  }
```

### 3.7 健康检查模块 `/api/health`

```yaml
# 基础健康检查
GET /api/health
  Response: {
    status: "healthy" | "degraded" | "unhealthy",
    timestamp: string
  }

# 详细健康检查
GET /api/health/detailed
  Response: {
    status: string,
    components: {
      api: { status, latency_ms },
      redis: { status, latency_ms },
      r2_storage: { status },
      gemini_api: { status, last_check }
    },
    version: string,
    uptime_seconds: number
  }
```

---

## 四、数据模型设计

### 4.1 Pydantic Schemas

```python
# api/schemas/common.py
from pydantic import BaseModel
from typing import Generic, TypeVar, Optional

T = TypeVar('T')

class APIResponse(BaseModel, Generic[T]):
    """通用 API 响应"""
    success: bool
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None

class ErrorDetail(BaseModel):
    code: str
    message: str
    type: str  # 用于 i18n 映射

class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应"""
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool


# api/schemas/auth.py
class GitHubUser(BaseModel):
    id: str
    login: str
    name: Optional[str]
    email: Optional[str]
    avatar_url: Optional[str]

    @property
    def user_folder_id(self) -> str:
        import hashlib
        return hashlib.md5(f"github_{self.id}".encode()).hexdigest()[:16]

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: GitHubUser


# api/schemas/generate.py
class GenerateRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "16:9"
    resolution: str = "1K"
    safety_level: str = "moderate"
    enable_thinking: bool = False
    save_to_history: bool = True

class GenerateResponse(BaseModel):
    image_url: str
    image_base64: Optional[str] = None
    text_response: Optional[str] = None
    thinking: Optional[str] = None
    duration: float
    history_id: Optional[str] = None

class BlendRequest(BaseModel):
    prompt: str
    images: list[str]  # Base64 encoded
    aspect_ratio: str = "1:1"
    safety_level: str = "moderate"

class BatchRequest(BaseModel):
    prompt: str
    count: int = 1
    aspect_ratio: str = "16:9"
    resolution: str = "1K"
    safety_level: str = "moderate"

class BatchTaskResponse(BaseModel):
    task_id: str
    status: str
    total: int
    completed: int
    results: list[GenerateResponse]


# api/schemas/chat.py
class CreateSessionRequest(BaseModel):
    aspect_ratio: str = "16:9"

class ChatSession(BaseModel):
    session_id: str
    created_at: str
    message_count: int
    last_message_at: Optional[str]

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    image_url: Optional[str]
    thinking: Optional[str]
    timestamp: str

class SendMessageRequest(BaseModel):
    message: str
    aspect_ratio: Optional[str] = None
    safety_level: str = "moderate"


# api/schemas/history.py
class HistoryItem(BaseModel):
    id: str
    prompt: str
    image_url: str
    thumbnail_url: Optional[str]
    mode: str
    settings: dict
    duration: float
    created_at: str
    session_id: Optional[str]

class HistoryQuery(BaseModel):
    limit: int = 20
    offset: int = 0
    mode: Optional[str] = None
    search: Optional[str] = None
    sort: str = "newest"
    date_from: Optional[str] = None
    date_to: Optional[str] = None


# api/schemas/quota.py
class QuotaMode(BaseModel):
    name: str
    used: int
    limit: int
    remaining: int
    cost: int

class QuotaStatus(BaseModel):
    is_trial_mode: bool
    global_used: int
    global_limit: int
    global_remaining: int
    modes: dict[str, QuotaMode]
    cooldown_active: bool
    cooldown_remaining: int
    resets_at: str
```

### 4.2 Redis 数据结构

```python
# 用户会话
"session:{user_id}" -> {
    "user": {...},
    "api_key": "encrypted_key",
    "created_at": timestamp,
    "last_active": timestamp
}
TTL: 7 days

# 聊天会话状态
"chat:{session_id}" -> {
    "user_id": str,
    "aspect_ratio": str,
    "messages": [...],
    "created_at": timestamp,
    "last_message_at": timestamp
}
TTL: 30 days

# 配额数据
"quota:{date}:global" -> int (全局已用点数)
"quota:{date}:user:{user_id}" -> {
    "global_used": int,
    "mode_usage": {...},
    "last_generation": timestamp
}
TTL: 2 days (自动清理)

# 批量任务
"batch:{task_id}" -> {
    "user_id": str,
    "status": str,
    "total": int,
    "completed": int,
    "results": [...],
    "created_at": timestamp
}
TTL: 1 day

# 速率限制
"ratelimit:{user_id}:{endpoint}" -> counter
TTL: 1 minute
```

---

## 五、分阶段实施计划

### 阶段一：基础架构搭建 (P0)

**目标**：建立 FastAPI 项目骨架，实现基本运行

**任务清单**：

1. **项目初始化**
   - [ ] 创建 `api/` 目录结构
   - [ ] 创建 `core/` 目录结构
   - [ ] 更新 `requirements.txt` (添加 FastAPI 依赖)
   - [ ] 创建 `requirements-dev.txt` (pytest, httpx 等)

2. **配置管理**
   - [ ] 创建 `api/config.py` (Pydantic Settings)
   - [ ] 支持环境变量和 .env 文件
   - [ ] 配置 CORS、日志、调试模式

3. **FastAPI 应用入口**
   - [ ] 创建 `api/main.py`
   - [ ] 配置路由前缀 `/api`
   - [ ] 添加全局异常处理
   - [ ] 添加请求日志中间件

4. **健康检查端点**
   - [ ] 实现 `GET /api/health`
   - [ ] 实现 `GET /api/health/detailed`

5. **Docker 更新**
   - [ ] 更新 `Dockerfile` (使用 uvicorn)
   - [ ] 更新 `docker-compose.yml` (添加 Redis)

**预期产出**：
- FastAPI 应用可启动
- 健康检查接口可用
- Docker 容器可构建

---

### 阶段二：服务层重构 (P0)

**目标**：移除 Streamlit 依赖，适配 FastAPI

**任务清单**：

1. **移除 Streamlit 依赖**
   - [ ] `services/r2_storage.py` - 移除 `st.secrets` 访问
   - [ ] `services/image_storage.py` - 移除 streamlit 导入
   - [ ] `services/trial_quota.py` - 移除 `st.session_state`
   - [ ] `services/auth.py` - 完全重写
   - [ ] `services/health_check.py` - 移除 session_state

2. **创建配置工具**
   - [ ] 创建 `core/config.py` - 统一配置访问
   - [ ] 替换所有 `get_config_value()` 调用

3. **Redis 集成**
   - [ ] 创建 `core/redis.py` - 连接管理
   - [ ] 实现连接池和异步支持

4. **重写配额服务**
   - [ ] 创建 `services/quota_service.py`
   - [ ] 使用 Redis 存储配额数据
   - [ ] 保留原有配额逻辑

5. **重写认证服务**
   - [ ] 创建 `services/auth_service.py`
   - [ ] 实现 GitHub OAuth 流程 (使用 httpx)
   - [ ] 实现 JWT Token 生成/验证
   - [ ] 创建 `core/security.py`

**预期产出**：
- 所有服务无 Streamlit 依赖
- Redis 连接可用
- 认证服务可独立运行

---

### 阶段三：核心 API 实现 (P0)

**目标**：实现图像生成和聊天 API

**任务清单**：

1. **认证路由**
   - [ ] 实现 `POST /api/auth/github/login`
   - [ ] 实现 `POST /api/auth/github/callback`
   - [ ] 实现 `GET /api/auth/me`
   - [ ] 创建 JWT 认证中间件

2. **生成路由**
   - [ ] 创建 `api/schemas/generate.py`
   - [ ] 实现 `POST /api/generate/basic`
   - [ ] 实现 `POST /api/generate/search`
   - [ ] 实现 `POST /api/generate/blend`
   - [ ] 集成内容过滤

3. **聊天路由**
   - [ ] 创建 `services/session_service.py` (会话持久化)
   - [ ] 实现 `POST /api/chat/sessions`
   - [ ] 实现 `GET /api/chat/sessions`
   - [ ] 实现 `POST /api/chat/sessions/{id}/messages`
   - [ ] 实现 `DELETE /api/chat/sessions/{id}`

4. **配额路由**
   - [ ] 实现 `GET /api/quota`
   - [ ] 实现 `POST /api/quota/check`
   - [ ] 集成到生成路由

5. **依赖注入**
   - [ ] 创建 `api/dependencies.py`
   - [ ] 实现 `get_current_user`
   - [ ] 实现 `get_generator`
   - [ ] 实现 `get_quota_service`

**预期产出**：
- 认证流程完整
- 基础/搜索/混合生成可用
- 聊天会话完整功能
- 配额检查工作

---

### 阶段四：辅助功能实现 (P1)

**目标**：实现历史、提示词库等功能

**任务清单**：

1. **历史记录路由**
   - [ ] 实现 `GET /api/history`
   - [ ] 实现 `GET /api/history/{id}`
   - [ ] 实现 `DELETE /api/history/{id}`
   - [ ] 实现 `DELETE /api/history` (批量)

2. **提示词库路由**
   - [ ] 实现 `GET /api/prompts`
   - [ ] 实现 `POST /api/prompts/generate`
   - [ ] 实现 `POST /api/prompts/{id}/favorite`
   - [ ] 实现 `POST /api/prompts`
   - [ ] 实现 `DELETE /api/prompts/{id}`

3. **批量生成**
   - [ ] 实现 `POST /api/generate/batch`
   - [ ] 实现 `GET /api/generate/batch/{task_id}`
   - [ ] 集成 arq 任务队列 (可选)

4. **导出功能**
   - [ ] 实现 `GET /api/chat/sessions/{id}/export`

**预期产出**：
- 历史记录完整功能
- 提示词库完整功能
- 批量生成可用

---

### 阶段五：测试与优化 (P1)

**目标**：完善测试，优化性能

**任务清单**：

1. **单元测试**
   - [ ] 创建 `tests/conftest.py` (fixtures)
   - [ ] 测试认证流程
   - [ ] 测试生成端点
   - [ ] 测试配额逻辑

2. **集成测试**
   - [ ] 测试完整生成流程
   - [ ] 测试聊天会话流程
   - [ ] 测试配额消耗

3. **性能优化**
   - [ ] 添加响应缓存
   - [ ] 优化 Redis 访问
   - [ ] 添加连接池

4. **文档**
   - [ ] 生成 OpenAPI 文档
   - [ ] 编写 API 使用指南
   - [ ] 更新 README

**预期产出**：
- 测试覆盖率 > 70%
- API 文档完整
- 性能达标

---

### 阶段六：部署与清理 (P2)

**目标**：完成部署，清理旧代码

**任务清单**：

1. **部署配置**
   - [ ] 更新 Railway/Render 配置
   - [ ] 配置生产环境变量
   - [ ] 配置 HTTPS

2. **代码清理**
   - [ ] 移除 `app.py`
   - [ ] 移除 `components/` 目录
   - [ ] 移除 `.streamlit/` 目录
   - [ ] 更新 `.gitignore`

3. **监控**
   - [ ] 添加 Sentry 错误追踪 (可选)
   - [ ] 添加性能监控 (可选)

**预期产出**：
- 生产环境部署完成
- 旧代码清理完毕

---

## 六、关键实现细节

### 6.1 JWT 认证实现

```python
# core/security.py
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext

SECRET_KEY = "your-secret-key"  # 从环境变量读取
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
```

### 6.2 GitHub OAuth 流程

```python
# services/auth_service.py
import httpx
from core.security import create_access_token

class AuthService:
    GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
    GITHUB_API_URL = "https://api.github.com/user"

    async def get_authorization_url(self, state: str = None) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "read:user user:email",
            "state": state
        }
        return f"{self.GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GITHUB_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code
                },
                headers={"Accept": "application/json"}
            )
            return response.json()

    async def get_user_info(self, access_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.GITHUB_API_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            return response.json()
```

### 6.3 Redis 配额存储

```python
# services/quota_service.py
from core.redis import get_redis

class QuotaService:
    async def check_quota(self, user_id: str, mode: str, resolution: str, count: int):
        redis = await get_redis()
        date_key = datetime.utcnow().strftime("%Y-%m-%d")

        # 获取全局配额
        global_key = f"quota:{date_key}:global"
        global_used = int(await redis.get(global_key) or 0)

        # 获取用户配额
        user_key = f"quota:{date_key}:user:{user_id}"
        user_data = await redis.hgetall(user_key)

        # 检查逻辑...

    async def consume_quota(self, user_id: str, mode: str, cost: int):
        redis = await get_redis()
        date_key = datetime.utcnow().strftime("%Y-%m-%d")

        # 原子操作增加配额
        async with redis.pipeline() as pipe:
            pipe.incrby(f"quota:{date_key}:global", cost)
            pipe.hincrby(f"quota:{date_key}:user:{user_id}", "global_used", cost)
            pipe.hincrby(f"quota:{date_key}:user:{user_id}", f"mode:{mode}", 1)
            pipe.expire(f"quota:{date_key}:global", 86400 * 2)
            pipe.expire(f"quota:{date_key}:user:{user_id}", 86400 * 2)
            await pipe.execute()
```

### 6.4 生成器适配

```python
# api/routers/generate.py
from fastapi import APIRouter, Depends, HTTPException
from services.generator import ImageGenerator, GenerationResult

router = APIRouter(prefix="/generate", tags=["generate"])

@router.post("/basic")
async def generate_basic(
    request: GenerateRequest,
    user: Optional[GitHubUser] = Depends(get_current_user_optional),
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    quota_service: QuotaService = Depends(get_quota_service),
    storage: R2Storage = Depends(get_storage),
):
    # 确定使用的 API key
    effective_api_key = api_key or settings.GOOGLE_API_KEY
    if not effective_api_key:
        raise HTTPException(400, "No API key provided")

    # 检查配额 (试用模式)
    if not api_key and user:
        can_generate, reason, _ = await quota_service.check_quota(
            user.user_folder_id, "basic", request.resolution, 1
        )
        if not can_generate:
            raise HTTPException(429, reason)

    # 内容过滤
    # ...

    # 生成图像
    generator = ImageGenerator(api_key=effective_api_key)
    result = generator.generate(
        prompt=request.prompt,
        aspect_ratio=request.aspect_ratio,
        resolution=request.resolution,
        enable_thinking=request.enable_thinking,
        safety_level=request.safety_level,
    )

    if result.error:
        raise HTTPException(500, result.error)

    # 保存到存储
    if request.save_to_history and result.image:
        key = storage.save_image(
            image=result.image,
            prompt=request.prompt,
            settings={"aspect_ratio": request.aspect_ratio, "resolution": request.resolution},
            duration=result.duration,
            mode="basic"
        )

    # 消耗配额
    if not api_key and user:
        await quota_service.consume_quota(...)

    return GenerateResponse(
        image_url=storage.get_public_url(key) if key else None,
        text_response=result.text,
        thinking=result.thinking,
        duration=result.duration,
        history_id=key
    )
```

---

## 七、新增 requirements.txt

```txt
# Core
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic>=2.0.0
pydantic-settings>=2.0.0

# Auth & Security
python-jose[cryptography]>=3.3.0
httpx>=0.27.0
passlib[bcrypt]>=1.7.4

# Cache & Queue
redis[hiredis]>=5.0.0

# Task Queue (Optional)
# arq>=0.26.0

# Existing (Keep)
google-genai>=1.0.0
Pillow>=10.0.0
python-dotenv>=1.0.0
boto3>=1.34.0

# REMOVED:
# streamlit>=1.30.0
# extra-streamlit-components>=0.1.60
# streamlit-oauth>=0.1.8
```

---

## 八、风险与注意事项

### 8.1 数据迁移

- **现有历史数据**：R2 存储的数据格式不变，无需迁移
- **用户认证**：JWT Token 与现有 Cookie 不兼容，用户需重新登录
- **配额数据**：迁移到 Redis，需要初始化脚本

### 8.2 破坏性变更

- API 响应格式完全不同
- 前端需要完全重写
- 现有部署配置需更新

### 8.3 向后兼容

- 如需保留 Streamlit 版本，可创建 `legacy/` 分支
- R2 存储格式保持不变，数据可共用

### 8.4 性能考虑

- 图像生成是 I/O 密集型，考虑使用异步
- 批量生成应使用任务队列
- Redis 需要配置持久化 (AOF/RDB)

---

## 九、时间线建议

| 阶段 | 优先级 | 依赖 |
|------|--------|------|
| 阶段一：基础架构 | P0 | 无 |
| 阶段二：服务重构 | P0 | 阶段一 |
| 阶段三：核心 API | P0 | 阶段二 |
| 阶段四：辅助功能 | P1 | 阶段三 |
| 阶段五：测试优化 | P1 | 阶段四 |
| 阶段六：部署清理 | P2 | 阶段五 |

---

## 十、下一步行动

1. **确认技术选型** - 是否需要调整 Redis/任务队列选择
2. **确认 API 设计** - 是否需要调整端点或响应格式
3. **开始阶段一** - 创建基础架构

如有问题或需要调整，请随时提出。
