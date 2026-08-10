import pytest

import resume_mcp.security as security
from resume_mcp.security import (
    AuthenticationError,
    authenticate_api_key,
    authenticate_headers,
    create_download_token,
    read_download_token,
    transport_security_settings,
)


def test_bearer_and_poke_user_are_both_required(monkeypatch, caplog):
    monkeypatch.setenv("MCP_API_KEY", "secret")
    monkeypatch.setenv("MCP_ALLOWED_POKE_USER_IDS", "poke-a,poke-b")

    assert authenticate_headers({
        "authorization": "Bearer secret",
        "x-poke-user-id": "poke-a",
    }) == "poke-a"
    with pytest.raises(AuthenticationError):
        authenticate_headers({
            "authorization": "Bearer wrong",
            "x-poke-user-id": "poke-a",
        })
    with pytest.raises(AuthenticationError):
        authenticate_headers({
            "authorization": "Bearer secret",
            "x-poke-user-id": "unknown",
        })
    assert "Rejected Poke user ID 'unknown'" in caplog.text


def test_transport_auth_allows_poke_discovery_without_user_id(monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "secret")

    assert authenticate_api_key({"authorization": "Bearer secret"}) is None
    with pytest.raises(AuthenticationError):
        authenticate_api_key({"authorization": "Bearer wrong"})


def test_download_token_preserves_owner_file_type_and_revision(monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "secret")
    monkeypatch.setenv("MCP_SIGNING_SECRET", "signing-secret")
    token = create_download_token(
        workflow_id="mcp-1",
        resume_draft_id="draft-1",
        poke_user_id="poke-a",
        kind="pdf",
        revision=4,
    )

    payload = read_download_token(token)

    assert payload == {
        "workflow_id": "mcp-1",
        "resume_draft_id": "draft-1",
        "poke_user_id": "poke-a",
        "kind": "pdf",
        "revision": 4,
    }


def test_download_token_expiration_is_reported(monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "secret")
    monkeypatch.setenv("MCP_SIGNING_SECRET", "signing-secret")
    token = create_download_token(
        workflow_id="mcp-1",
        resume_draft_id="draft-1",
        poke_user_id="poke-a",
        kind="docx",
        revision=2,
    )
    monkeypatch.setattr(security, "DOWNLOAD_MAX_AGE_SECONDS", -1)

    with pytest.raises(AuthenticationError, match="expired"):
        read_download_token(token)


def test_server_configuration_requires_public_https_url(monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "secret")
    monkeypatch.setenv("MCP_ALLOWED_POKE_USER_IDS", "poke-a")
    monkeypatch.setenv("MCP_SIGNING_SECRET", "signing-secret")
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "http://127.0.0.1:8010")

    with pytest.raises(RuntimeError, match="public HTTPS"):
        security.validate_configuration()


def test_transport_security_allows_configured_tunnel_and_localhost(monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "https://resume-example.ngrok-free.dev")

    settings = transport_security_settings()

    assert settings.enable_dns_rebinding_protection is True
    assert "resume-example.ngrok-free.dev" in settings.allowed_hosts
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert "https://resume-example.ngrok-free.dev" in settings.allowed_origins
