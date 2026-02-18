"""
Unit tests for error handler middleware.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.middleware.error_handler import setup_exception_handlers
from core.exceptions import (
    AppException,
    GenerationError,
    ModelUnavailableError,
    NotFoundError,
    QuotaExceededError,
    TaskNotFoundError,
    ValidationError,
)


def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with exception handlers for testing."""
    app = FastAPI()
    setup_exception_handlers(app)

    @app.get("/raise-app-exception")
    async def raise_app_exception():
        raise AppException(message="Something broke", error_code="test_error")

    @app.get("/raise-generation-error")
    async def raise_generation_error():
        raise GenerationError(message="GPU out of memory")

    @app.get("/raise-not-found")
    async def raise_not_found():
        raise NotFoundError(message="Image not found")

    @app.get("/raise-quota-exceeded")
    async def raise_quota_exceeded():
        raise QuotaExceededError(
            message="Daily limit reached",
            details={"used": 50, "limit": 50},
        )

    @app.get("/raise-task-not-found")
    async def raise_task_not_found():
        raise TaskNotFoundError()

    @app.get("/raise-model-unavailable")
    async def raise_model_unavailable():
        raise ModelUnavailableError(message="GPT-4 is down")

    @app.get("/raise-validation-error")
    async def raise_validation_error():
        raise ValidationError(message="Invalid prompt")

    @app.get("/raise-http-400")
    async def raise_http_400():
        raise HTTPException(status_code=400, detail="Bad input")

    @app.get("/raise-http-404")
    async def raise_http_404():
        raise HTTPException(status_code=404, detail="Not here")

    @app.get("/raise-http-501")
    async def raise_http_501():
        raise HTTPException(status_code=501, detail="Coming soon")

    @app.get("/raise-http-503")
    async def raise_http_503():
        raise HTTPException(status_code=503, detail="Service down")

    @app.get("/raise-unexpected")
    async def raise_unexpected():
        raise RuntimeError("Something unexpected")

    return app


@pytest.fixture
def test_client():
    app = _create_test_app()
    return TestClient(app, raise_server_exceptions=False)


class TestAppExceptionHandler:
    """Test that AppException subclasses produce structured responses."""

    def test_generation_error(self, test_client):
        resp = test_client.get("/raise-generation-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "generation_failed"
        assert body["error"]["message"] == "GPU out of memory"

    def test_not_found(self, test_client):
        resp = test_client.get("/raise-not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "not_found"

    def test_quota_exceeded_with_details(self, test_client):
        resp = test_client.get("/raise-quota-exceeded")
        assert resp.status_code == 429
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "quota_exceeded"
        assert body["error"]["details"]["used"] == 50

    def test_task_not_found(self, test_client):
        resp = test_client.get("/raise-task-not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "task_not_found"

    def test_model_unavailable(self, test_client):
        resp = test_client.get("/raise-model-unavailable")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["code"] == "model_unavailable"

    def test_validation_error(self, test_client):
        resp = test_client.get("/raise-validation-error")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"


class TestHTTPExceptionFallbackHandler:
    """Test that HTTPException is wrapped in structured format."""

    def test_http_400(self, test_client):
        resp = test_client.get("/raise-http-400")
        assert resp.status_code == 400
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "bad_request"
        assert body["error"]["message"] == "Bad input"

    def test_http_404(self, test_client):
        resp = test_client.get("/raise-http-404")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "not_found"

    def test_http_501(self, test_client):
        resp = test_client.get("/raise-http-501")
        assert resp.status_code == 501
        body = resp.json()
        assert body["error"]["code"] == "not_implemented"

    def test_http_503(self, test_client):
        resp = test_client.get("/raise-http-503")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["code"] == "service_unavailable"


class TestGeneralExceptionHandler:
    """Test that unhandled exceptions also produce structured format."""

    def test_unexpected_error(self, test_client):
        resp = test_client.get("/raise-unexpected")
        assert resp.status_code == 500
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "internal_error"
