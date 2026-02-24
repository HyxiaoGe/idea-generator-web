"""
Authentication strategies for AI providers.
"""

import hashlib
import hmac
import secrets
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime


class AuthStrategy(ABC):
    """Base class for authentication strategies."""

    @abstractmethod
    def apply(self, headers: dict, **kwargs) -> dict:
        """Apply authentication to request headers."""
        pass


class BearerTokenAuth(AuthStrategy):
    """Bearer token authentication (Authorization: Bearer xxx)."""

    def __init__(self, token: str):
        self.token = token

    def apply(self, headers: dict, **kwargs) -> dict:
        headers["Authorization"] = f"Bearer {self.token}"
        return headers


class ApiKeyHeaderAuth(AuthStrategy):
    """API key header authentication (X-API-Key: xxx or custom header)."""

    def __init__(self, api_key: str, header_name: str = "X-API-Key"):
        self.api_key = api_key
        self.header_name = header_name

    def apply(self, headers: dict, **kwargs) -> dict:
        headers[self.header_name] = self.api_key
        return headers


class HmacSignatureAuth(AuthStrategy):
    """HMAC-based authentication (Kling, some Chinese providers)."""

    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key
        self.secret_key = secret_key

    def apply(
        self,
        headers: dict,
        method: str = "POST",
        path: str = "/",
        body: str = "",
        **kwargs,
    ) -> dict:
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(8)

        sign_str = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body}"
        signature = hmac.new(
            self.secret_key.encode(), sign_str.encode(), hashlib.sha256
        ).hexdigest()

        headers["X-Access-Key"] = self.access_key
        headers["X-Timestamp"] = timestamp
        headers["X-Nonce"] = nonce
        headers["X-Signature"] = signature
        return headers


class VolcanoEngineAuth(AuthStrategy):
    """ByteDance Volcano Engine authentication (AWS Signature V4 style)."""

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region: str = "cn-north-1",
        service: str = "cv",
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.service = service

    def _sign(self, key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signature_key(self, date_stamp: str) -> bytes:
        k_date = self._sign(self.secret_key.encode("utf-8"), date_stamp)
        k_region = self._sign(k_date, self.region)
        k_service = self._sign(k_region, self.service)
        k_signing = self._sign(k_service, "request")
        return k_signing

    def apply(
        self,
        headers: dict,
        method: str = "POST",
        path: str = "/",
        query: str = "",
        body: str = "",
        host: str = "",
        **kwargs,
    ) -> dict:
        t = datetime.now(UTC)
        amz_date = t.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = t.strftime("%Y%m%d")

        # Add required headers
        headers["X-Date"] = amz_date
        if host:
            headers["Host"] = host

        # Create canonical request
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        headers["X-Content-Sha256"] = payload_hash

        signed_headers = "host;x-content-sha256;x-date"
        canonical_headers = f"host:{host}\nx-content-sha256:{payload_hash}\nx-date:{amz_date}\n"

        canonical_request = (
            f"{method}\n{path}\n{query}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )

        # Create string to sign
        algorithm = "HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/{self.service}/request"
        string_to_sign = (
            f"{algorithm}\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

        # Calculate signature
        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # Add authorization header
        authorization = (
            f"{algorithm} "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        headers["Authorization"] = authorization

        return headers
