"""
Lightweight OpenRouter LLM client for prompt processing.

Uses httpx to call OpenRouter's chat completions endpoint with
retry and exponential backoff.
"""

import asyncio
import logging

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)

# Retry config matching project conventions (3 attempts, 2/4/8s backoff)
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]


class LLMClient:
    """Async OpenRouter LLM client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-sonnet-4-5",
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_message: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """
        Call OpenRouter chat completions and return the text response.

        Retries on transient errors with exponential backoff.
        """
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        last_error: str | None = None
        client = await self._get_client()

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.post("/chat/completions", json=payload)

                if response.status_code in (200, 201):
                    data = response.json()
                    return data["choices"][0]["message"]["content"].strip()

                error_msg = self._extract_error(response)
                last_error = error_msg

                # Fail fast on client errors (auth, bad request, etc.)
                if 400 <= response.status_code < 500:
                    logger.warning(f"[LLMClient] Client error {response.status_code}: {error_msg}")
                    break

                # Retry on transient server errors, but not if the error
                # indicates an authentication/authorization problem
                if (
                    response.status_code in (502, 503, 504)
                    and attempt < MAX_RETRIES - 1
                    and not self._is_auth_error(error_msg)
                ):
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"[LLMClient] Retryable error (attempt {attempt + 1}): {error_msg}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    continue

                break

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = str(e)
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"[LLMClient] Connection error (attempt {attempt + 1}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                break

        raise RuntimeError(f"LLM call failed after {MAX_RETRIES} attempts: {last_error}")

    @staticmethod
    def _is_auth_error(error_msg: str) -> bool:
        """Check if an error message indicates an authentication failure."""
        lower = error_msg.lower()
        return any(
            keyword in lower
            for keyword in ("authenticat", "unauthoriz", "api key", "invalid key", "forbidden")
        )

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            data = response.json()
            if isinstance(data.get("error"), dict):
                return data["error"].get("message", f"HTTP {response.status_code}")
            if isinstance(data.get("error"), str):
                return data["error"]
            return f"HTTP {response.status_code}"
        except Exception:
            return f"HTTP {response.status_code}"

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get or create the singleton LLM client."""
    global _llm_client
    if _llm_client is None:
        settings = get_settings()
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        _llm_client = LLMClient(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.openrouter_model,
        )
    return _llm_client
