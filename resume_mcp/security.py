"""Authentication and short-lived download tokens for the MCP adapter."""

from __future__ import annotations

import hmac
import logging
import os
from urllib.parse import quote
from urllib.parse import urlparse

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from mcp.server.transport_security import TransportSecuritySettings


DOWNLOAD_MAX_AGE_SECONDS = 24 * 60 * 60
logger = logging.getLogger(__name__)


class AuthenticationError(PermissionError):
    pass


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for the MCP server.")
    return value


def allowed_users() -> set[str]:
    users = {
        item.strip()
        for item in _required_env("MCP_ALLOWED_POKE_USER_IDS").split(",")
        if item.strip()
    }
    if not users:
        raise RuntimeError("MCP_ALLOWED_POKE_USER_IDS must contain at least one user ID.")
    return users


def validate_configuration() -> None:
    _required_env("MCP_API_KEY")
    allowed_users()
    _required_env("MCP_SIGNING_SECRET")
    public_url = _required_env("MCP_PUBLIC_BASE_URL").rstrip("/")
    parsed = urlparse(public_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("MCP_PUBLIC_BASE_URL must be a public HTTPS origin.")


def transport_security_settings() -> TransportSecuritySettings:
    public_url = _required_env("MCP_PUBLIC_BASE_URL").rstrip("/")
    parsed = urlparse(public_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("MCP_PUBLIC_BASE_URL must be a public HTTPS origin.")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
            parsed.netloc,
        ],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
            public_url,
        ],
    )


def authenticate_api_key(headers) -> None:
    configured_key = _required_env("MCP_API_KEY")
    authorization = str(headers.get("authorization", "")).strip()
    supplied_key = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not supplied_key or not hmac.compare_digest(supplied_key, configured_key):
        raise AuthenticationError("A valid bearer API key is required.")


def authenticate_headers(headers) -> str:
    authenticate_api_key(headers)
    poke_user_id = str(headers.get("x-poke-user-id", "")).strip()
    if not poke_user_id or poke_user_id not in allowed_users():
        if poke_user_id:
            logger.warning(
                "Rejected Poke user ID %r. Add it to MCP_ALLOWED_POKE_USER_IDS and restart the MCP server.",
                poke_user_id[:200],
            )
        raise AuthenticationError("X-Poke-User-Id is missing or not allowed.")
    return poke_user_id


def serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("MCP_SIGNING_SECRET", "").strip() or _required_env("MCP_API_KEY")
    return URLSafeTimedSerializer(secret, salt="resume-mcp-download-v1")


def create_download_token(
    *,
    workflow_id: str,
    resume_draft_id: str,
    poke_user_id: str,
    kind: str,
    revision: int,
) -> str:
    if kind not in {"pdf", "docx"}:
        raise ValueError("Unsupported download type.")
    return serializer().dumps({
        "workflow_id": workflow_id,
        "resume_draft_id": resume_draft_id,
        "poke_user_id": poke_user_id,
        "kind": kind,
        "revision": int(revision),
    })


def read_download_token(token: str) -> dict:
    try:
        payload = serializer().loads(token, max_age=DOWNLOAD_MAX_AGE_SECONDS)
    except SignatureExpired as exc:
        raise AuthenticationError("This download link has expired.") from exc
    except BadSignature as exc:
        raise AuthenticationError("This download link is invalid.") from exc
    if not isinstance(payload, dict):
        raise AuthenticationError("This download link is invalid.")
    return payload


def public_base_url(request) -> str:
    configured = os.getenv("MCP_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    return f"{request.url.scheme}://{request.url.netloc}".rstrip("/")


def signed_download_urls(*, workflow: dict, draft: dict, poke_user_id: str, base_url: str) -> dict:
    revision = int(draft.get("resume_revision") or 1)
    result = {}
    for kind in ("pdf", "docx"):
        path = str(draft.get(f"{kind}_path", "")).strip()
        if not path:
            continue
        token = create_download_token(
            workflow_id=workflow["id"],
            resume_draft_id=draft["id"],
            poke_user_id=poke_user_id,
            kind=kind,
            revision=revision,
        )
        result[kind] = f"{base_url}/downloads/{quote(token, safe='')}"
    return result
