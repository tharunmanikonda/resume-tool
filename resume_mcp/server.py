"""Hosted SSE MCP server for Poke resume generation."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route

from .contracts import ResumeChange
from .persistence import workflows
from .security import (
    AuthenticationError,
    authenticate_api_key,
    authenticate_headers,
    public_base_url,
    read_download_token,
    transport_security_settings,
    validate_configuration,
)
from .service import (
    add_file_urls,
    apply_structured_changes,
    continue_resume_action as continue_action_service,
    finalize_resume as finalize_service,
    get_resume_status as status_service,
    start_resume_generation as start_service,
)
from . import service as resume_service


mcp = FastMCP(
    "Resume Generator",
    instructions=(
        "Generate and revise resumes through the existing local resume pipeline. "
        "Preserve draft_id, revision, and action_id. Resolve action_required responses "
        "before continuing, and never call finalize_resume without explicit user confirmation."
    ),
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8010")),
    transport_security=transport_security_settings(),
)


def _request(ctx: Context) -> Request:
    request = ctx.request_context.request
    if not isinstance(request, Request):
        raise RuntimeError("This tool requires the hosted SSE transport.")
    return request


def _user(ctx: Context) -> str:
    return authenticate_headers(_request(ctx).headers)


def _with_files(response: dict, ctx: Context, poke_user_id: str) -> dict:
    return add_file_urls(
        response,
        poke_user_id=poke_user_id,
        base_url=public_base_url(_request(ctx)),
    )


@mcp.tool()
def start_resume_generation(
    job_description: str,
    ctx: Context,
    identity_id: str = "",
    company_name: str = "",
    role_title: str = "",
    source_url: str = "",
) -> dict:
    """Start an asynchronous resume from a raw JD using the canonical resume pipeline."""
    user_id = _user(ctx)
    if len(job_description.strip()) < 120:
        raise ValueError("The job description must contain at least 120 characters.")
    return start_service(
        poke_user_id=user_id,
        job_description=job_description,
        identity_id=identity_id,
        company_name=company_name,
        role_title=role_title,
        source_url=source_url,
    )


@mcp.tool()
def get_resume_status(
    draft_id: str,
    ctx: Context,
    include_review: bool = False,
    wait_seconds: int = 0,
) -> dict:
    """Check generation progress, optionally waiting up to 20 seconds for a state change."""
    user_id = _user(ctx)
    if wait_seconds < 0 or wait_seconds > 20:
        raise ValueError("wait_seconds must be between 0 and 20.")
    response = status_service(
        poke_user_id=user_id,
        workflow_id=draft_id,
        include_review=include_review,
        wait_seconds=wait_seconds,
    )
    return _with_files(response, ctx, user_id)


@mcp.tool()
def continue_resume_action(
    draft_id: str,
    action_id: str,
    selection: str | dict,
    ctx: Context,
) -> dict:
    """Resolve the current identity, duplicate, retry, review, or confirmation action."""
    user_id = _user(ctx)
    response = continue_action_service(
        poke_user_id=user_id,
        workflow_id=draft_id,
        action_id=action_id,
        selection=selection,
    )
    return _with_files(response, ctx, user_id)


@mcp.tool()
def update_resume_draft(
    draft_id: str,
    base_revision: int,
    changes: list[ResumeChange],
    ctx: Context,
) -> dict:
    """Apply atomic, revision-protected edits without running Luna again."""
    user_id = _user(ctx)
    return apply_structured_changes(
        poke_user_id=user_id,
        workflow_id=draft_id,
        base_revision=base_revision,
        changes=changes,
    )


@mcp.tool()
def finalize_resume(
    draft_id: str,
    base_revision: int,
    confirmed: bool,
    ctx: Context,
) -> dict:
    """Generate PDF and DOCX for the latest revision after explicit confirmation."""
    user_id = _user(ctx)
    response = finalize_service(
        poke_user_id=user_id,
        workflow_id=draft_id,
        base_revision=base_revision,
        confirmed=confirmed,
    )
    return _with_files(response, ctx, user_id)


class McpAuthenticationMiddleware:
    """Authenticate MCP HTTP scopes without buffering the SSE response stream."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        if path == "/health" or path.startswith("/downloads/"):
            await self.app(scope, receive, send)
            return
        try:
            # Poke's integration test authenticates tool discovery with the API
            # key but does not attach a user ID until an actual tool invocation.
            authenticate_api_key(Headers(scope=scope))
        except (AuthenticationError, RuntimeError) as exc:
            response = JSONResponse({"error": str(exc)}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def health(_request: Request):
    return JSONResponse({"status": "ok", "transport": "sse"})


async def download(request: Request):
    try:
        payload = read_download_token(request.path_params["token"])
        workflow = workflows.get_for_user(payload["workflow_id"], payload["poke_user_id"])
        if (
            not workflow
            or workflow.get("resume_draft_id") != payload.get("resume_draft_id")
        ):
            raise AuthenticationError("This download does not belong to the workflow.")
        draft = resume_service.resume_app.extension_draft_payload(
            resume_service.resume_app.extension_drafts.get(workflow["resume_draft_id"])
        )
        if int(draft.get("resume_revision") or 1) != int(payload.get("revision") or 0):
            raise AuthenticationError("This download link is for an older resume revision.")
        if (
            draft.get("pdf_stale")
            or int(draft.get("pdf_revision") or 0) != int(draft.get("resume_revision") or 1)
        ):
            raise AuthenticationError("The generated files are stale.")
        kind = str(payload.get("kind", ""))
        if kind not in {"pdf", "docx"}:
            raise AuthenticationError("Unsupported download type.")
        path = resume_service.resume_app.require_within_output(
            str(draft.get(f"{kind}_path", ""))
        )
        media_type = (
            "application/pdf"
            if kind == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return FileResponse(
            Path(path),
            media_type=media_type,
            filename=Path(path).name,
        )
    except AuthenticationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except (KeyError, FileNotFoundError, ValueError):
        return JSONResponse({"error": "The requested file is unavailable."}, status_code=404)


application = Starlette(routes=[
    Route("/health", health, methods=["GET"]),
    Route("/downloads/{token:str}", download, methods=["GET"]),
    Mount("/", app=mcp.sse_app()),
])
application = McpAuthenticationMiddleware(application)


def main() -> None:
    validate_configuration()
    uvicorn.run(
        application,
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8010")),
        log_level=os.getenv("MCP_LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
