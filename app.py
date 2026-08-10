#!/usr/bin/env python3
"""
Modern Flask Resume Generator App
- Manual content input → Parse → Generate PDF
- No AI needed, just template replacement
"""

import copy
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

# Environment-backed database configuration must be loaded before database modules.
load_dotenv()

from flask import Flask, render_template, request, jsonify, send_file, Response
from desktop_runtime import (
    default_output_dir,
    load_json_file,
    open_path,
    resource_path,
    settings_path,
    write_json_file,
)
from manual_resume_parser import parse_updated_content_to_resume, validate_updated_content
from pdf_builder import build_resume_docx, is_pdf_conversion_ready
from extension_drafts import ActiveDraftTaskError, AuditStaleError, ExtensionDraftStore, normalize_context, validate_context
from database import init_db

# Configuration
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
BASE_RESUME_PATH = resource_path("config", "base_resume.json")
# Default to local resumes folder in project directory
DEFAULT_OUTPUT_ROOT = str(default_output_dir())
OUTPUT_ROOT = os.getenv("OUTPUT_ROOT", DEFAULT_OUTPUT_ROOT)
SETTINGS_FILE = settings_path()
TRACKER_FILE = resource_path("config", "application_tracker.json")
PERMANENT_PROFILE_FILE = resource_path("config", "user_profile.json")
SESSION_PROFILE_FILE = resource_path("config", "session_profile.json")
PROFILE_TEMPLATE_FILE = resource_path("config", "user_profile.template.json")

GMAIL_IDENTITY_DEFAULT = {
    "id": "gmail",
    "label": "Gmail",
    "location": "Dallas, TX",
    "phone": "(469)963-5323",
    "email": "tmanikonda.1@gmail.com",
    "format_profile": "gmail",
}

def load_settings():
    """Load settings from config/settings.json, fall back to env var if missing."""
    loaded_settings = load_json_file(Path(SETTINGS_FILE), {"output_directory": OUTPUT_ROOT})
    loaded_settings.setdefault("output_directory", OUTPUT_ROOT)
    loaded_settings.setdefault("keep_docx", True)
    loaded_settings.setdefault("identities", [])
    return loaded_settings

def save_settings(settings_dict):
    """Save settings to config/settings.json."""
    write_json_file(Path(SETTINGS_FILE), settings_dict)

settings = load_settings()
init_db()
extension_drafts = ExtensionDraftStore()
extension_ai_stage_gate_lock = threading.RLock()

TRACKER_STATUSES = ["Applied", "Updated", "Converted", "Ghosted", "Rejected"]

ANALYSIS_MODEL = os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-4o-mini")
RESUME_MODEL = os.getenv("OPENAI_RESUME_MODEL", "gpt-5-mini")
SYNTHESIS_MODEL = os.getenv("OPENAI_SYNTHESIS_MODEL", "gpt-5.6-terra")
AUDIT_MODEL = os.getenv("OPENAI_AUDIT_MODEL", "gpt-5.6-luna")
SYNTHESIS_REASONING_EFFORT = os.getenv("OPENAI_SYNTHESIS_REASONING_EFFORT", "medium")
AUDIT_REASONING_EFFORT = os.getenv("OPENAI_AUDIT_REASONING_EFFORT", "medium")
ANALYSIS_TEMPERATURE = 0.2
RESUME_TEMPERATURE = 0.4
AI_MEMORY_LIMIT = 2
AI_REVISION_REQUEST_MAX_CHARS = 3000
AI_REVISION_RESUME_MAX_CHARS = 18000
ANALYSIS_MAX_OUTPUT_TOKENS = 2400
RESUME_MAX_OUTPUT_TOKENS = 7800
SMALL_OUTPUT_HEADROOM = 200
MEDIUM_OUTPUT_HEADROOM = 300
LARGE_OUTPUT_HEADROOM = 500
OPENAI_ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("OPENAI_ANALYSIS_TIMEOUT_SECONDS", "120"))
OPENAI_RESUME_TIMEOUT_SECONDS = int(os.getenv("OPENAI_RESUME_TIMEOUT_SECONDS", "180"))
OPENAI_AUDIT_BACKGROUND_TIMEOUT_SECONDS = int(
    os.getenv("OPENAI_AUDIT_BACKGROUND_TIMEOUT_SECONDS", "600")
)
OPENAI_BACKGROUND_HTTP_TIMEOUT_SECONDS = int(
    os.getenv("OPENAI_BACKGROUND_HTTP_TIMEOUT_SECONDS", "60")
)
OPENAI_BACKGROUND_POLL_INTERVAL_SECONDS = float(
    os.getenv("OPENAI_BACKGROUND_POLL_INTERVAL_SECONDS", "2")
)
OPENAI_API_URL = "https://api.openai.com/v1/responses"

EXPERIENCE_BLUEPRINTS = [
    {
        "key": "mckinsey",
        "company": "McKinsey & Company",
        "location": "CA, USA",
        "dates": "May 2025 – Present",
        "bullet_min": 6,
        "bullet_max": 7,
        "anchor": "enterprise delivery, applied AI workflows, ingestion and retrieval systems, customer-facing software",
    },
    {
        "key": "uber",
        "company": "Uber",
        "location": "CA, USA",
        "dates": "February 2024 – May 2025",
        "bullet_min": 5,
        "bullet_max": 6,
        "anchor": "operational tooling, transaction validation, real-time workflows, internal product systems",
    },
    {
        "key": "kpmg",
        "company": "KPMG",
        "location": "India",
        "dates": "September 2021 – July 2022",
        "bullet_min": 5,
        "bullet_max": 5,
        "anchor": "audit and compliance systems, Java backend services, document processing, reporting workflows",
    },
    {
        "key": "trigent",
        "company": "Trigent Software",
        "location": "India",
        "dates": "March 2020 – August 2021",
        "bullet_min": 3,
        "bullet_max": 3,
        "anchor": "frontend engineering, UI migration, responsive web delivery, QA-oriented implementation",
    },
]

EXPERIENCE_BLUEPRINTS_BY_KEY = {blueprint["key"]: blueprint for blueprint in EXPERIENCE_BLUEPRINTS}
EXPERIENCE_BLUEPRINT_KEYS = [blueprint["key"] for blueprint in EXPERIENCE_BLUEPRINTS]

TITLE_WORD_MIN = 2
TITLE_WORD_MAX = 8
SUMMARY_WORD_MIN = 65
SUMMARY_WORD_MAX = 95
EXPERIENCE_BULLET_WORD_MIN = 25
EXPERIENCE_BULLET_WORD_MAX = 30

ALLOWED_SKILL_CATEGORIES = {
    "Programming Languages",
    "Frontend Engineering",
    "Backend Engineering",
    "Data & Storage",
    "Cloud & Infrastructure",
    "DevOps & CI/CD",
    "Observability & Reliability",
    "System Design & Performance",
    "Testing & Quality",
    "AI & LLM Systems",
    "Data Engineering",
    "Mobile Development",
    "Embedded Systems",
    "Messaging & Streaming",
    "Security & Auth",
    "Data Analysis & Querying",
    "BI & Visualization",
    "Reporting & Insights",
    "Business Analysis",
    "Process & Requirements",
    "Marketing Analytics",
    "Experimentation & Measurement",
    "Stakeholder Communication",
    "GTM Systems & Automation",
    "CRM & RevOps Platforms",
    "Outbound & Lifecycle Tooling",
    "Tools & Platforms",
}

SKILL_CATEGORY_ORDER_TEMPLATES = {
    "fullstack_product": [
        "Programming Languages",
        "Frontend Engineering",
        "Backend Engineering",
        "Data & Storage",
        "Cloud & Infrastructure",
        "DevOps & CI/CD",
        "Testing & Quality",
        "AI & LLM Systems",
        "System Design & Performance",
    ],
    "backend_application": [
        "Programming Languages",
        "Backend Engineering",
        "Data & Storage",
        "Cloud & Infrastructure",
        "Observability & Reliability",
        "DevOps & CI/CD",
        "Testing & Quality",
        "System Design & Performance",
        "Security & Auth",
    ],
    "data_engineering": [
        "Programming Languages",
        "Data Engineering",
        "Data & Storage",
        "Frontend Engineering",
        "Cloud & Infrastructure",
        "DevOps & CI/CD",
        "Testing & Quality",
        "AI & LLM Systems",
        "System Design & Performance",
    ],
    "platform_distributed": [
        "Programming Languages",
        "Backend Engineering",
        "Messaging & Streaming",
        "Cloud & Infrastructure",
        "Observability & Reliability",
        "DevOps & CI/CD",
        "Testing & Quality",
        "System Design & Performance",
        "Security & Auth",
    ],
    "embedded_systems": [
        "Programming Languages",
        "Embedded Systems",
        "Backend Engineering",
        "Observability & Reliability",
        "Testing & Quality",
        "System Design & Performance",
        "Security & Auth",
    ],
    "ai_application": [
        "Programming Languages",
        "AI & LLM Systems",
        "Frontend Engineering",
        "Backend Engineering",
        "Data & Storage",
        "Cloud & Infrastructure",
        "DevOps & CI/CD",
        "Testing & Quality",
        "System Design & Performance",
    ],
    "solutions_engineering": [
        "Programming Languages",
        "Backend Engineering",
        "Frontend Engineering",
        "Data & Storage",
        "Cloud & Infrastructure",
        "Testing & Quality",
        "System Design & Performance",
        "AI & LLM Systems",
    ],
    "analyst_data": [
        "Programming Languages",
        "Data Analysis & Querying",
        "BI & Visualization",
        "Data & Storage",
        "Reporting & Insights",
        "Experimentation & Measurement",
        "Stakeholder Communication",
        "Tools & Platforms",
    ],
    "analyst_business": [
        "Business Analysis",
        "Data Analysis & Querying",
        "BI & Visualization",
        "Process & Requirements",
        "Reporting & Insights",
        "Stakeholder Communication",
        "Tools & Platforms",
    ],
    "analyst_marketing": [
        "Marketing Analytics",
        "Data Analysis & Querying",
        "BI & Visualization",
        "Experimentation & Measurement",
        "Reporting & Insights",
        "Stakeholder Communication",
        "Tools & Platforms",
    ],
    "gtm_engineering": [
        "Programming Languages",
        "GTM Systems & Automation",
        "CRM & RevOps Platforms",
        "Data Analysis & Querying",
        "Outbound & Lifecycle Tooling",
        "Reporting & Insights",
        "Stakeholder Communication",
        "AI & LLM Systems",
        "Tools & Platforms",
    ],
}

PREFERRED_SKILL_CATEGORY_ORDER = [
    "Programming Languages",
    "Backend Engineering",
    "Frontend Engineering",
    "Data & Storage",
    "Cloud & Infrastructure",
    "Messaging & Streaming",
    "Observability & Reliability",
    "DevOps & CI/CD",
    "Security & Auth",
    "Testing & Quality",
    "System Design & Performance",
    "AI & LLM Systems",
    "Data Engineering",
    "Mobile Development",
    "Embedded Systems",
    "Data Analysis & Querying",
    "BI & Visualization",
    "Reporting & Insights",
    "Business Analysis",
    "Process & Requirements",
    "Marketing Analytics",
    "Experimentation & Measurement",
    "Stakeholder Communication",
    "GTM Systems & Automation",
    "CRM & RevOps Platforms",
    "Outbound & Lifecycle Tooling",
    "Tools & Platforms",
]

ROLE_FAMILY_TO_SKILL_ORDER_KEY = {
    "full-stack product engineering": "fullstack_product",
    "backend application engineering": "backend_application",
    "integration engineering": "backend_application",
    "application integration engineering": "backend_application",
    "cloud integration engineering": "backend_application",
    "data engineering": "data_engineering",
    "analytics engineering": "data_engineering",
    "platform engineering": "platform_distributed",
    "distributed systems engineering": "platform_distributed",
    "cloud infrastructure engineering": "platform_distributed",
    "embedded systems engineering": "embedded_systems",
    "system software engineering": "embedded_systems",
    "ai application engineering": "ai_application",
    "solutions engineering": "solutions_engineering",
    "implementation engineering": "solutions_engineering",
    "data analyst": "analyst_data",
    "data analytics": "analyst_data",
    "business analyst": "analyst_business",
    "marketing analyst": "analyst_marketing",
    "product analyst": "analyst_data",
    "operations analyst": "analyst_business",
    "financial analyst": "analyst_business",
    "finance analyst": "analyst_business",
    "supply chain analyst": "analyst_business",
    "inventory analyst": "analyst_business",
    "sales analyst": "analyst_marketing",
    "pricing analyst": "analyst_business",
    "cost analyst": "analyst_business",
    "vendor management analyst": "analyst_business",
    "reporting analyst": "analyst_data",
    "research analyst": "analyst_data",
    "institutional data analyst": "analyst_data",
    "prospect analyst": "analyst_data",
    "erp analyst": "analyst_business",
    "business systems analyst": "analyst_business",
    "systems analyst": "analyst_business",
    "wms analyst": "analyst_business",
    "warehouse management analyst": "analyst_business",
    "gtm engineering": "gtm_engineering",
    "go-to-market engineering": "gtm_engineering",
    "go to market engineering": "gtm_engineering",
    "gtm engineer": "gtm_engineering",
    "go-to-market engineer": "gtm_engineering",
    "go to market engineer": "gtm_engineering",
    "revops engineering": "gtm_engineering",
    "revenue engineering": "gtm_engineering",
}

ROLE_FAMILY_TO_PROMPT_FAMILY_KEY = {
    "full-stack product engineering": "software_engineering",
    "backend application engineering": "software_engineering",
    "integration engineering": "software_engineering",
    "application integration engineering": "software_engineering",
    "cloud integration engineering": "software_engineering",
    "data engineering": "data_engineering",
    "analytics engineering": "data_engineering",
    "platform engineering": "platform_systems",
    "distributed systems engineering": "platform_systems",
    "cloud infrastructure engineering": "platform_systems",
    "embedded systems engineering": "platform_systems",
    "system software engineering": "platform_systems",
    "ai application engineering": "software_engineering",
    "solutions engineering": "solutions_customer",
    "implementation engineering": "solutions_customer",
    "data analyst": "analyst_data",
    "data analytics": "analyst_data",
    "business analyst": "analyst_business",
    "marketing analyst": "analyst_marketing",
    "product analyst": "analyst_data",
    "operations analyst": "analyst_business",
    "financial analyst": "analyst_business",
    "finance analyst": "analyst_business",
    "supply chain analyst": "analyst_business",
    "inventory analyst": "analyst_business",
    "sales analyst": "analyst_marketing",
    "pricing analyst": "analyst_business",
    "cost analyst": "analyst_business",
    "vendor management analyst": "analyst_business",
    "reporting analyst": "analyst_data",
    "research analyst": "analyst_data",
    "institutional data analyst": "analyst_data",
    "prospect analyst": "analyst_data",
    "erp analyst": "analyst_business",
    "business systems analyst": "analyst_business",
    "systems analyst": "analyst_business",
    "wms analyst": "analyst_business",
    "warehouse management analyst": "analyst_business",
    "gtm engineering": "gtm_engineering",
    "go-to-market engineering": "gtm_engineering",
    "go to market engineering": "gtm_engineering",
    "gtm engineer": "gtm_engineering",
    "go-to-market engineer": "gtm_engineering",
    "go to market engineer": "gtm_engineering",
    "revops engineering": "gtm_engineering",
    "revenue engineering": "gtm_engineering",
}

GENERATION_ROUTE_CONFIG = {
    "fullstack_product": {
        "skill_category_order_key": "fullstack_product",
        "prompt_family_key": "software_engineering",
    },
    "growth_product": {
        "skill_category_order_key": "fullstack_product",
        "prompt_family_key": "software_engineering",
    },
    "backend_application": {
        "skill_category_order_key": "backend_application",
        "prompt_family_key": "software_engineering",
    },
    "data_engineering": {
        "skill_category_order_key": "data_engineering",
        "prompt_family_key": "data_engineering",
    },
    "data_science": {
        "skill_category_order_key": "ai_application",
        "prompt_family_key": "data_science",
    },
    "platform_distributed": {
        "skill_category_order_key": "platform_distributed",
        "prompt_family_key": "platform_systems",
    },
    "embedded_systems": {
        "skill_category_order_key": "embedded_systems",
        "prompt_family_key": "platform_systems",
    },
    "ai_application": {
        "skill_category_order_key": "ai_application",
        "prompt_family_key": "software_engineering",
    },
    "agentic_ai_engineering": {
        "skill_category_order_key": "ai_application",
        "prompt_family_key": "agentic_ai_engineering",
    },
    "security_engineering": {
        "skill_category_order_key": "backend_application",
        "prompt_family_key": "security_engineering",
    },
    "solutions_engineering": {
        "skill_category_order_key": "solutions_engineering",
        "prompt_family_key": "solutions_customer",
    },
    "analyst_data": {
        "skill_category_order_key": "analyst_data",
        "prompt_family_key": "analyst_data",
    },
    "analyst_business": {
        "skill_category_order_key": "analyst_business",
        "prompt_family_key": "analyst_business",
    },
    "analyst_marketing": {
        "skill_category_order_key": "analyst_marketing",
        "prompt_family_key": "analyst_marketing",
    },
    "gtm_engineering": {
        "skill_category_order_key": "gtm_engineering",
        "prompt_family_key": "gtm_engineering",
    },
}

SKILL_GENERIC_PHRASES = {
    "monitoring tools",
    "data driven solutions",
    "ai feature integration",
    "deployment strategies",
    "technical design discussions",
    "reliability focused design",
    "service design and apis",
    "service design & apis",
    "product focused ui and interaction design",
    "cost aware cloud architecture",
}

SKILL_CATEGORY_PATTERNS = {
    "Programming Languages": (
        "python", "java", "javascript", "typescript", "sql", "pl-sql", "oracle sql", "c#", "c++", "go", "rust", "scala",
    ),
    "Frontend Engineering": (
        "react", "reactjs", "next.js", "nextjs", "ui", "dashboard", "visualization", "component", "responsive", "accessibility",
        "state management", "api integration", "rich-text", "rich text", "css", "webpack", "storybook",
    ),
    "Backend Engineering": (
        "node", "node.js", "graphql", "rest api", "webhook", "service architecture", "api design", "grpc", "protobuf",
        "microservice", "tokio", "flask", "fastapi", "spring", "asp.net", "entity framework",
    ),
    "Data & Storage": (
        "snowflake", "oracle", "oracle sql", "oracle pl-sql", "postgres", "postgresql", "mysql", "sql server", "redis",
        "mongodb", "schema", "partition", "query", "warehouse", "data modeling", "index", "materialized view",
    ),
    "Cloud & Infrastructure": (
        "aws", "gcp", "azure", "google cloud", "docker", "kubernetes", "terraform", "terragrunt", "pulumi", "helm",
        "cloudformation", "cdk", "lambda", "cloud run", "gke", "eks", "ecs", "serverless",
    ),
    "DevOps & CI/CD": (
        "github actions", "gitlab", "jenkins", "argocd", "codepipeline", "ci/cd", "ci cd", "deployment", "release",
        "build", "smoke test", "rollout",
    ),
    "Observability & Reliability": (
        "prometheus", "grafana", "cloudwatch", "datadog", "opentelemetry", "logging", "monitoring", "alerting", "tracing",
        "telemetry", "observability", "incident", "mttr", "slo", "sli",
    ),
    "Testing & Quality": (
        "unit testing", "integration testing", "end-to-end", "e2e", "cypress", "jest", "validation", "test automation",
        "data quality", "debugging", "root-cause", "root cause", "regression",
    ),
    "System Design & Performance": (
        "performance", "throughput", "latency", "scalable", "reliable", "fault tolerance", "concurrency", "architecture",
        "cost optimization", "pipeline architecture", "distributed systems", "real-time", "deterministic",
    ),
    "AI & LLM Systems": (
        "claude", "anthropic", "openai", "llm", "rag", "prompt", "agent", "agentic", "embedding", "vector", "semantic",
        "model integration", "inference",
    ),
    "Data Engineering": (
        "pyspark", "spark", "etl", "elt", "airflow", "orchestration", "data pipeline", "data ingestion", "batch", "stream",
        "workflow orchestration", "copy load",
    ),
    "Messaging & Streaming": (
        "kafka", "pubsub", "streaming", "websocket", "tcp", "udp", "messaging", "event", "queue",
    ),
    "Security & Auth": (
        "auth", "authentication", "authorization", "jwt", "oauth", "security", "secret management", "owasp", "encryption",
        "dod", "secure communications",
    ),
    "Embedded Systems": (
        "embedded", "embedded linux", "nixos", "sensor fusion", "can", "rs-232", "firmware", "serial", "control system",
        "real-time", "hardware", "actuator", "ros2",
    ),
}

SYSTEM_SIGNAL_TERMS = {
    "api", "database", "db", "pipeline", "service", "workflow", "queue", "cache",
    "stream", "dashboard", "index", "batch", "async", "event", "search", "retrieval",
    "validation", "monitoring", "ingestion", "processing", "backend", "frontend",
}

CONSTRAINT_SIGNAL_TERMS = {
    "latency", "scale", "scalability", "throughput", "concurrency", "failure", "freshness",
    "downtime", "load", "volume", "reliability", "performance", "accuracy", "timeout",
}

DECISION_SIGNAL_TERMS = {
    "cache", "caching", "batch", "batching", "async", "asynchronous", "index", "indexing",
    "orchestration", "partitioning", "deduplication", "filtering", "routing", "normalizing",
}

GENERIC_BULLET_PATTERNS = (
    "worked with",
    "responsible for",
    "helped with",
    "involved in",
    "participated in",
)

FORBIDDEN_TERMS_BY_COMPANY = {
    "Trigent Software": {
        "ai", "llm", "rag", "embedding", "embeddings", "langchain", "openai",
        "pinecone", "vector", "vectors", "semantic search", "retrieval",
    },
}
FORBIDDEN_TERMS_BY_BLUEPRINT_KEY = {
    "trigent": FORBIDDEN_TERMS_BY_COMPANY["Trigent Software"],
}

ai_sessions: dict[str, dict] = {}
_whisper_model = None
_whisper_error = None

AI_AUDIT_STALEABLE_STATUSES = {
    "approved",
    "changes_suggested",
    "manual_attention",
    "applied",
    "kept_current",
    "technical_failed",
}
AI_PDF_ALLOWED_AUDIT_STATUSES = {
    "approved",
    "applied",
    "kept_current",
}


class ExtensionPdfAuditConflict(ValueError):
    def __init__(self, audit_status: str):
        self.audit_status = audit_status
        super().__init__("Run or resolve the resume quality review before creating a PDF.")


def clear_ai_session_audit(session: dict, *, status: str = "not_started") -> None:
    session["audit_status"] = status
    session["audit_result"] = None
    session["audit_proposal"] = None
    session["audit_base_revision"] = None
    session["audit_base_hash"] = None
    session["audit_created_at"] = None
    session["audit_applied_at"] = None


def ensure_ai_session_state(session: dict) -> dict:
    session.setdefault("resume_revision", 1)
    session.setdefault("resume_content", "")
    session.setdefault("enabled_experience_keys", list(EXPERIENCE_BLUEPRINT_KEYS))
    session.setdefault("audit_status", "not_started")
    session.setdefault("audit_result", None)
    session.setdefault("audit_proposal", None)
    session.setdefault("audit_base_revision", None)
    session.setdefault("audit_base_hash", None)
    session.setdefault("audit_created_at", None)
    session.setdefault("audit_applied_at", None)
    session.setdefault("revision_context", None)
    session.setdefault("advertised_job_title", "")
    session.setdefault("has_manual_resume_edits", False)
    session.setdefault("profile_snapshot", {})
    session.setdefault("resume_versions", {})
    session.setdefault("active_resume_version", "")
    if session.get("audit_status") == "failed":
        session["audit_status"] = "technical_failed"
    audit_result = session.get("audit_result")
    if (
        session.get("audit_status") in {"changes_proposed", "blocked"}
        or (
            isinstance(audit_result, dict)
            and audit_result.get("decision")
            and str(audit_result.get("schema_version", "")) != RESUME_QUALITY_AUDIT_SCHEMA_VERSION
        )
    ):
        session["audit_status"] = "stale"
        session["audit_proposal"] = None
    return session


def _structured_resume_version(
    *,
    canonical_resume: dict,
    resume_content: str,
    resume_snapshot: dict | None = None,
    revision: int = 1,
) -> dict:
    return {
        "resume": copy.deepcopy(canonical_resume),
        "resume_content": str(resume_content or ""),
        "resume_snapshot": copy.deepcopy(resume_snapshot or {}),
        "revision": int(revision or 1),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def capture_ai_session_resume_version(
    session: dict,
    version_key: str,
    active_blueprints: list[dict],
) -> dict:
    canonical = ai_session_canonical_resume(session, active_blueprints)
    version = _structured_resume_version(
        canonical_resume=canonical,
        resume_content=session.get("resume_content", ""),
        revision=int(session.get("resume_revision") or 1),
    )
    versions = copy.deepcopy(session.get("resume_versions") or {})
    versions[version_key] = version
    session["resume_versions"] = versions
    session["active_resume_version"] = version_key
    return version


def load_tracker_store() -> dict:
    store = load_json_file(Path(TRACKER_FILE), {"applications": []})
    applications = store.get("applications")
    if not isinstance(applications, list):
        applications = []
    store["applications"] = applications
    return store


def save_tracker_store(store: dict) -> None:
    write_json_file(Path(TRACKER_FILE), {"applications": store.get("applications", [])})


def today_iso_date() -> str:
    return datetime.now().date().isoformat()


def normalize_tracker_status(status: str) -> str:
    value = str(status or "").strip().title()
    return value if value in TRACKER_STATUSES else "Applied"


def parse_iso_date(value: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).strip())
    except Exception:
        return datetime.min


def iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


def file_created_iso(path: Path) -> str:
    stat = path.stat()
    created_ts = getattr(stat, "st_birthtime", None) or stat.st_mtime
    return iso_from_timestamp(created_ts)


def parse_resume_snapshot(
    content: str,
    contact_override: dict | None = None,
    identity: str = "outlook",
    experience_history_override: list[dict] | None = None,
    enabled_experience_keys: list[str] | None = None,
) -> dict:
    base_resume = load_base_resume()
    merged_resume = parse_updated_content_to_resume(str(content or "").strip(), base_resume)
    merged_resume = apply_profile_overrides(merged_resume)
    merged_resume = apply_experience_history_override(merged_resume, experience_history_override)
    merged_resume = apply_enabled_experience_filter(merged_resume, enabled_experience_keys)
    if isinstance(contact_override, dict):
        merged_resume["contact"] = {
            **merged_resume.get("contact", {}),
            **{
                key: str(contact_override.get(key, "")).strip()
                for key in ("location", "phone", "email")
                if str(contact_override.get(key, "")).strip()
            },
        }
    return merged_resume


def build_tracker_application_record(
    *,
    company_name: str,
    job_description: str,
    resume_content: str,
    analysis_payload: dict | None,
    applied_date: str,
    status: str,
    source: str = "",
    job_url: str = "",
    notes: str = "",
    pdf_path: str = "",
    output_dir: str = "",
    contact_override: dict | None = None,
    identity: str = "outlook",
    experience_history_override: list[dict] | None = None,
    enabled_experience_keys: list[str] | None = None,
    parsed_resume_override: dict | None = None,
) -> dict:
    parsed_resume = parsed_resume_override if isinstance(parsed_resume_override, dict) and parsed_resume_override else parse_resume_snapshot(
        resume_content,
        contact_override,
        identity,
        experience_history_override,
        enabled_experience_keys,
    )
    normalized_status = normalize_tracker_status(status)
    company = str(company_name or "").strip() or str((analysis_payload or {}).get("company_name", "")).strip() or "Unknown Company"
    role_title = str(parsed_resume.get("title", "")).strip() or str((analysis_payload or {}).get("target_role", "")).strip() or "Untitled Role"
    now_iso = datetime.now().isoformat(timespec="seconds")
    effective_applied_date = str(applied_date or "").strip() or today_iso_date()
    normalized_output_dir = str(output_dir or "").strip()
    folder_group = ""
    if normalized_output_dir:
        try:
            output_root = Path(settings["output_directory"]).expanduser().resolve()
            output_dir_path = Path(normalized_output_dir).expanduser().resolve()
            relative_parent = output_dir_path.parent.relative_to(output_root)
            folder_group = "" if str(relative_parent) == "." else str(relative_parent)
        except Exception:
            folder_group = ""
    initial_event = {
        "status": normalized_status,
        "changed_at": now_iso,
        "effective_date": effective_applied_date,
        "note": str(notes or "").strip(),
    }
    return {
        "id": uuid.uuid4().hex,
        "company_name": company,
        "role_title": role_title,
        "role_family": str((analysis_payload or {}).get("role_family", "")).strip(),
        "target_role": str((analysis_payload or {}).get("target_role", "")).strip(),
        "status": normalized_status,
        "applied_date": effective_applied_date,
        "last_updated_date": now_iso,
        "status_updated_date": effective_applied_date,
        "source": str(source or "").strip(),
        "job_url": str(job_url or "").strip(),
        "notes": str(notes or "").strip(),
        "pdf_path": str(pdf_path or "").strip(),
        "output_dir": normalized_output_dir,
        "folder_group": folder_group,
        "resume_content": str(resume_content or "").strip(),
        "resume_snapshot": parsed_resume,
        "job_description": str(job_description or "").strip(),
        "analysis": compact_analysis_for_generation(analysis_payload or {}),
        "history": [initial_event],
        "created_at": now_iso,
        "locked": True,
    }


def infer_application_from_output_dir(folder: Path, output_root: Path | None = None) -> dict | None:
    if not folder.is_dir():
        return None

    docx_path = folder / "tharun manikonda resume.docx"
    pdf_path = folder / "tharun manikonda resume.pdf"
    status_path = folder / "pdf_status.json"
    artifact_path = docx_path if docx_path.exists() else pdf_path if pdf_path.exists() else None
    if artifact_path is None:
        return None

    folder_name = folder.name
    company_name = folder_name
    role_title = "Locked Resume"
    if " - " in folder_name:
        parts = [part.strip() for part in folder_name.split(" - ") if part.strip()]
        if len(parts) >= 2:
            company_name = parts[0]
            role_title = " - ".join(parts[1:])

    created_iso = file_created_iso(artifact_path)
    application_id = "fs-" + uuid.uuid5(uuid.NAMESPACE_URL, str(folder.resolve())).hex
    folder_group = ""
    if output_root is not None:
        try:
            relative_parent = folder.parent.resolve().relative_to(output_root.resolve())
            folder_group = "" if str(relative_parent) == "." else str(relative_parent)
        except Exception:
            folder_group = ""
    return {
        "id": application_id,
        "company_name": company_name,
        "role_title": role_title,
        "role_family": "",
        "target_role": role_title,
        "status": "Applied",
        "applied_date": created_iso[:10],
        "last_updated_date": created_iso,
        "status_updated_date": created_iso[:10],
        "source": "",
        "job_url": "",
        "notes": "",
        "pdf_path": str(pdf_path) if pdf_path.exists() else "",
        "output_dir": str(folder),
        "folder_group": folder_group,
        "resume_content": "",
        "resume_snapshot": {"title": role_title},
        "job_description": "",
        "analysis": {},
        "history": [
            {
                "status": "Applied",
                "changed_at": created_iso,
                "effective_date": created_iso[:10],
                "note": "Imported from saved resume folder",
            }
        ],
        "created_at": created_iso,
        "locked": True,
        "discovered": True,
        "status_path": str(status_path) if status_path.exists() else "",
    }


def scan_output_tracker_applications() -> list[dict]:
    output_root = Path(settings["output_directory"]).expanduser().resolve()
    if not output_root.exists():
        return []

    discovered: list[dict] = []
    if output_root.is_dir():
        seen_dirs: set[str] = set()
        candidate_files = sorted(
            [
                path for path in output_root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".docx", ".pdf"}
            ],
            key=lambda path: str(path).lower(),
        )

        for path in candidate_files:
            if path.name.lower() in {"tharun manikonda resume.docx", "tharun manikonda resume.pdf"} and path.parent != output_root:
                parent_key = str(path.parent.resolve())
                if parent_key in seen_dirs:
                    continue
                item = infer_application_from_output_dir(path.parent, output_root)
                if item:
                    discovered.append(item)
                    seen_dirs.add(parent_key)
                continue

            if path.parent == output_root:
                created_iso = file_created_iso(path)
                application_id = "fs-" + uuid.uuid5(uuid.NAMESPACE_URL, str(path.resolve())).hex
                discovered.append({
                    "id": application_id,
                    "company_name": path.stem,
                    "role_title": "Locked Resume",
                    "role_family": "",
                    "target_role": "Locked Resume",
                    "status": "Applied",
                    "applied_date": created_iso[:10],
                    "last_updated_date": created_iso,
                    "status_updated_date": created_iso[:10],
                    "source": "",
                    "job_url": "",
                    "notes": "",
                    "pdf_path": str(path) if path.suffix.lower() == ".pdf" else "",
                    "output_dir": str(path.parent),
                    "folder_group": "",
                    "resume_content": "",
                    "resume_snapshot": {"title": path.stem},
                    "job_description": "",
                    "analysis": {},
                    "history": [
                        {
                            "status": "Applied",
                            "changed_at": created_iso,
                            "effective_date": created_iso[:10],
                            "note": "Imported from saved resume file",
                        }
                    ],
                    "created_at": created_iso,
                    "locked": True,
                    "discovered": True,
                    "status_path": "",
                })
    return discovered


def merge_tracker_applications(store: dict) -> list[dict]:
    persisted = list(store.get("applications", []))
    discovered = scan_output_tracker_applications()
    persisted_by_output = {
        str(item.get("output_dir", "")).strip(): item
        for item in persisted
        if str(item.get("output_dir", "")).strip()
    }

    merged: list[dict] = []
    seen_ids: set[str] = set()

    for discovered_item in discovered:
        match = persisted_by_output.get(str(discovered_item.get("output_dir", "")).strip())
        if match:
            merged_item = {
                **discovered_item,
                **match,
                "discovered": True,
                "locked": True,
            }
        else:
            merged_item = discovered_item
        merged.append(merged_item)
        seen_ids.add(str(merged_item.get("id", "")))

    for item in persisted:
        item_id = str(item.get("id", ""))
        if item_id not in seen_ids:
            merged.append(item)

    return merged


def summarize_tracker(store: dict) -> dict:
    applications = store.get("applications", [])
    counts = {status: 0 for status in TRACKER_STATUSES}
    for app_record in applications:
        counts[normalize_tracker_status(app_record.get("status", ""))] += 1
    return {
        "counts": counts,
        "total": len(applications),
    }


def sorted_tracker_applications(applications: list[dict], *, sort_key: str = "applied_date", descending: bool = True) -> list[dict]:
    def key_fn(item: dict):
        if sort_key == "last_updated_date":
            return parse_iso_date(item.get("last_updated_date", ""))
        if sort_key == "status":
            return normalize_tracker_status(item.get("status", ""))
        return parse_iso_date(item.get("applied_date", ""))

    return sorted(applications, key=key_fn, reverse=descending)


def normalize_company_lookup(company_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(company_name or "").strip().lower())


def list_tracker_applications() -> list[dict]:
    return merge_tracker_applications(load_tracker_store())


def tracker_company_history(company_name: str) -> dict:
    normalized = normalize_company_lookup(company_name)
    applications = [
        item
        for item in list_tracker_applications()
        if normalize_company_lookup(item.get("company_name", "")) == normalized
    ]
    applications = sorted_tracker_applications(applications, sort_key="applied_date")
    return {
        "company_name": company_name,
        "normalized_company": normalized,
        "count": len(applications),
        "applications": applications,
        "latest": applications[0] if applications else None,
    }


def tracker_application_by_id(application_id: str) -> dict | None:
    wanted = str(application_id or "").strip()
    if not wanted:
        return None
    return next((item for item in list_tracker_applications() if str(item.get("id", "")).strip() == wanted), None)


def upsert_tracker_application(application: dict) -> dict:
    store = load_tracker_store()
    applications = list(store.get("applications", []))
    incoming_id = str(application.get("id", "")).strip()
    incoming_output = str(application.get("output_dir", "")).strip()
    match_index = None
    for index, item in enumerate(applications):
        item_id = str(item.get("id", "")).strip()
        item_output = str(item.get("output_dir", "")).strip()
        if incoming_id and item_id == incoming_id:
            match_index = index
            break
        if incoming_output and item_output == incoming_output:
            match_index = index
            break
    if match_index is None:
        saved = {**application, "id": incoming_id or f"app-{uuid.uuid4().hex}"}
        applications.append(saved)
    else:
        saved = {**applications[match_index], **application, "id": applications[match_index].get("id") or incoming_id or f"app-{uuid.uuid4().hex}"}
        applications[match_index] = saved
    store["applications"] = applications
    save_tracker_store(store)
    return saved


def update_tracker_status_record(application_id: str, status: str, note: str, effective_date: str) -> dict:
    store = load_tracker_store()
    applications = list(store.get("applications", []))
    wanted = str(application_id or "").strip()
    changed_at = datetime.now(timezone.utc).isoformat()
    for index, item in enumerate(applications):
        if str(item.get("id", "")).strip() != wanted:
            continue
        history = list(item.get("history") or [])
        updated = {
            **item,
            "status": status,
            "last_updated_date": changed_at,
            "status_updated_date": effective_date,
            "history": history + [{
                "status": status,
                "changed_at": changed_at,
                "effective_date": effective_date,
                "note": note,
            }],
        }
        applications[index] = updated
        store["applications"] = applications
        save_tracker_store(store)
        return updated
    raise KeyError("Application not found.")


class AIStageError(RuntimeError):
    def __init__(self, stage: str, message: str, *, analysis: dict | None = None, timing: dict | None = None):
        super().__init__(message)
        self.stage = stage
        self.analysis = analysis
        self.timing = timing or {}


def with_output_headroom(base_tokens: int, extra_tokens: int) -> int:
    return max(1, int(base_tokens) + int(extra_tokens))

# Cache PDF conversion status check (checked once, reused for 1 hour)
_pdf_status_cache = {"result": None, "timestamp": 0}

def get_pdf_conversion_status():
    """Get cached PDF conversion tool status or check if needed."""
    current_time = time.time()
    cache_duration = 3600  # 1 hour

    if _pdf_status_cache["result"] is None or (current_time - _pdf_status_cache["timestamp"]) > cache_duration:
        try:
            ok, msg = is_pdf_conversion_ready()
            _pdf_status_cache["result"] = (ok, msg)
            _pdf_status_cache["timestamp"] = current_time
        except Exception as e:
            _pdf_status_cache["result"] = (False, f"Error: {str(e)}")
            _pdf_status_cache["timestamp"] = current_time

    return _pdf_status_cache["result"]


def get_whisper_model():
    global _whisper_model, _whisper_error
    if _whisper_model is not None:
        return _whisper_model
    if _whisper_error is not None:
        raise RuntimeError(_whisper_error)

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        _whisper_error = (
            "Local transcription is not available because faster-whisper is not installed. "
            "Install dependencies in the app venv and restart the app."
        )
        raise RuntimeError(_whisper_error) from exc

    try:
        model_name_or_path = os.getenv("FASTER_WHISPER_MODEL_PATH", "").strip() or "tiny.en"
        _whisper_model = WhisperModel(model_name_or_path, device="cpu", compute_type="int8")
        return _whisper_model
    except Exception as exc:
        _whisper_error = (
            "Failed to load local transcription model. "
            "Set FASTER_WHISPER_MODEL_PATH to a downloaded Whisper model directory, or allow the app to download tiny.en once. "
            f"Underlying error: {exc}"
        )
        raise RuntimeError(_whisper_error) from exc


def is_ai_generation_ready() -> tuple[bool, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return False, "OPENAI_API_KEY is not configured"
    return True, (
        f"Ready (analysis={ANALYSIS_MODEL}, resume={RESUME_MODEL}, "
        f"synthesis={SYNTHESIS_MODEL}, audit={AUDIT_MODEL})"
    )


def prune_ai_sessions(max_age_seconds: int = 6 * 3600) -> None:
    cutoff = time.time() - max_age_seconds
    expired = [session_id for session_id, session in ai_sessions.items() if session.get("updated_at", 0) < cutoff]
    for session_id in expired:
        ai_sessions.pop(session_id, None)


def get_ai_session(session_id: str | None, job_description: str, reset_memory: bool) -> tuple[str, dict]:
    prune_ai_sessions()

    if reset_memory or not session_id or session_id not in ai_sessions:
        new_session_id = uuid.uuid4().hex
        session = {
            "job_description": job_description,
            "advertised_job_title": "",
            "turns": [],
            "analysis": None,
            "title_summary": None,
            "skills": None,
            "core_resume": None,
            "experience_recent": None,
            "experience_older": None,
            "enabled_experience_keys": list(EXPERIENCE_BLUEPRINT_KEYS),
            "resume_content": "",
            "resume_revision": 1,
            "revision_context": None,
            "has_manual_resume_edits": False,
            "profile_snapshot": current_profile(),
            "resume_versions": {},
            "active_resume_version": "",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        clear_ai_session_audit(session)
        ai_sessions[new_session_id] = session
        return new_session_id, session

    session = ensure_ai_session_state(ai_sessions[session_id])
    if session.get("job_description") != job_description:
        session["job_description"] = job_description
        session["turns"] = []
        session["analysis"] = None
        session["title_summary"] = None
        session["skills"] = None
        session["core_resume"] = None
        session["experience_recent"] = None
        session["experience_older"] = None
        session["resume_content"] = ""
        session["resume_revision"] = int(session.get("resume_revision") or 0) + 1
        session["revision_context"] = None
        session["advertised_job_title"] = ""
        session["has_manual_resume_edits"] = False
        session["profile_snapshot"] = current_profile()
        session["resume_versions"] = {}
        session["active_resume_version"] = ""
        clear_ai_session_audit(session)
    session["updated_at"] = time.time()
    return session_id, session


def compact_turn_for_prompt(turn: dict) -> str:
    analysis = turn.get("analysis") or {}
    resume_text = (turn.get("resume_text") or "").strip()
    revision_request = (turn.get("revision_request") or "").strip() or "Initial draft request"

    lines = [f"Turn request: {revision_request}"]
    if analysis.get("core_problem"):
        lines.append(f"Core problem identified: {analysis['core_problem']}")
    if analysis.get("target_role"):
        lines.append(f"Target role: {analysis['target_role']}")
    if analysis.get("skills_mentioned"):
        lines.append("Skills mentioned: " + ", ".join(analysis["skills_mentioned"][:8]))
    if resume_text:
        lines.append("Resume draft used previously:")
        lines.append(resume_text)
    return "\n".join(lines)


def normalize_revision_context(revision_request: str = "", current_resume_content: str = "") -> dict | None:
    def normalize_text(value: str, max_chars: int) -> str:
        lines = [
            re.sub(r"[ \t]+", " ", line).strip()
            for line in str(value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        ]
        normalized = "\n".join(line for line in lines if line).strip()
        return normalized[:max_chars].rstrip()

    request_text = normalize_text(revision_request, AI_REVISION_REQUEST_MAX_CHARS)
    resume_text = normalize_text(current_resume_content, AI_REVISION_RESUME_MAX_CHARS)
    if not request_text and not resume_text:
        return None
    return {
        "revision_request": request_text,
        "current_resume_content": resume_text,
    }


def append_revision_context_to_prompt(user_parts: list[str], revision_context: dict | None) -> None:
    context = revision_context if isinstance(revision_context, dict) else {}
    revision_request = str(context.get("revision_request", "")).strip()
    current_resume_content = str(context.get("current_resume_content", "")).strip()
    if not revision_request and not current_resume_content:
        return

    user_parts.extend([
        "User-requested revision context (editing instruction only; never factual evidence):",
        f"Requested edit:\n{revision_request}" if revision_request else "Requested edit: none provided",
        (
            f"Current edited resume to preserve where unaffected:\n{current_resume_content}"
            if current_resume_content
            else "Current edited resume: none provided"
        ),
        "\n".join([
            "Revision safety rules:",
            "- Follow the requested edit only when it is consistent with the JD, generated evidence, immutable experience blueprints, and all factual validation rules.",
            "- Treat the request and current resume only as editing context, never as evidence for a skill, tool, metric, vertical or domain experience, employer, title, date, or work history.",
            "- Do not invent unsupported tools, metrics, vertical experience, or history to satisfy the request.",
            "- Preserve unaffected current resume content wherever the requested output schema allows; change only what the supported request requires.",
        ]),
    ])


def compact_analysis_for_generation(analysis_payload: dict) -> dict:
    analysis_payload = normalize_analysis_payload(analysis_payload)

    def compact_list(values: list, limit: int) -> list[str]:
        result: list[str] = []
        for value in values[:limit]:
            text = str(value).strip()
            if text:
                result.append(text)
        return result

    return {
        "company_name": str(analysis_payload.get("company_name", "")).strip(),
        "company_description": str(analysis_payload.get("company_description", "")).strip(),
        "company_domain": str(analysis_payload.get("company_domain", "")).strip(),
        "culture_signals": compact_list(analysis_payload.get("culture_signals", []), 4),
        "target_role": str(analysis_payload.get("target_role", "")).strip(),
        "role_family": str(analysis_payload.get("role_family", "")).strip(),
        "generation_route_key": str(analysis_payload.get("generation_route_key", "")).strip(),
        "skill_category_order_key": str(analysis_payload.get("skill_category_order_key", "")).strip(),
        "prompt_family_key": str(analysis_payload.get("prompt_family_key", "")).strip(),
        "core_problem": str(analysis_payload.get("core_problem", "")).strip(),
        "hire_problem": str(analysis_payload.get("hire_problem", "")).strip(),
        "desired_outcomes": compact_list(analysis_payload.get("desired_outcomes", []), 4),
        "top_requirements": compact_list(analysis_payload.get("top_requirements", []), 4),
        "secondary_requirements": compact_list(analysis_payload.get("secondary_requirements", []), 5),
        "evidence_terms": compact_list(analysis_payload.get("evidence_terms", []), 8),
        "domain_terms": compact_list(analysis_payload.get("domain_terms", []), 8),
        "system_description": str(analysis_payload.get("system_description", "")).strip(),
        "responsibilities": compact_list(analysis_payload.get("responsibilities", []), 5),
        "workflows": compact_list(analysis_payload.get("workflows", []), 5),
        "skills_mentioned": compact_list(analysis_payload.get("skills_mentioned", []), 20),
        "behavioral_signals": compact_list(analysis_payload.get("behavioral_signals", []), 5),
        "gaps": compact_list(analysis_payload.get("gaps", []), 5),
    }


def compact_analysis_for_reachout(analysis_payload: dict) -> dict:
    compact = compact_analysis_for_generation(analysis_payload)
    return {
        "company_name": compact.get("company_name", ""),
        "target_role": compact.get("target_role", ""),
        "core_problem": compact.get("core_problem", ""),
        "skills_mentioned": compact.get("skills_mentioned", [])[:4],
        "behavioral_signals": compact.get("behavioral_signals", [])[:3],
    }


def normalize_analysis_payload(analysis_payload: dict) -> dict:
    normalized = dict(analysis_payload or {})
    role_family = str(normalized.get("role_family", "")).strip()
    role_family_lower = role_family.lower()
    target_role = str(normalized.get("target_role", "")).strip().lower()
    skills_mentioned = [str(item).strip().lower() for item in (normalized.get("skills_mentioned") or []) if str(item).strip()]
    responsibilities = [str(item).strip().lower() for item in (normalized.get("responsibilities") or []) if str(item).strip()]
    combined_signals = " ".join([role_family_lower, target_role, *skills_mentioned, *responsibilities])

    customer_facing_markers = (
        "demo", "onboarding", "customer support", "adoption", "pre-sales", "presales",
        "sales engineering", "technical account", "implementation for customers", "customer-facing"
    )
    backend_integration_markers = (
        "azure", ".net", "rest", "restful", "api", "microservice", "service bus", "oauth", "jwt",
        "azure ad", "docker", "kubernetes", "ci/cd", "devops", "azure devops", "functions", "app service",
        "container apps", "event-driven", "event driven", "web services"
    )

    looks_customer_facing = any(marker in combined_signals for marker in customer_facing_markers)
    looks_backend_integration = any(marker in combined_signals for marker in backend_integration_markers)

    route_key = generation_route_key_for_analysis(normalized)
    route_config = GENERATION_ROUTE_CONFIG[route_key]
    normalized["generation_route_key"] = route_key
    normalized["skill_category_order_key"] = route_config["skill_category_order_key"]
    normalized["prompt_family_key"] = route_config["prompt_family_key"]

    if route_key == "growth_product" and role_family_lower != "growth product engineering":
        normalized["role_family"] = "growth product engineering"
    elif (
        route_key == "backend_application"
        and "integration" in combined_signals
        and looks_backend_integration
        and not looks_customer_facing
    ):
        normalized["role_family"] = "backend application engineering"
    elif route_key == "backend_application" and role_family_lower == "ai application engineering":
        normalized["role_family"] = "backend application engineering"
    return normalized


def extract_reachout_resume_snapshot(current_resume_content: str) -> dict:
    text = str(current_resume_content or "").strip()
    title = ""
    summary = ""

    title_match = re.search(r"Updated Title\s*\n+(.+)", text, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()

    summary_match = re.search(
        r"Updated Summary\s*\n+(.+?)(?:\n\s*\n(?:Updated Skills|Professional Experience)\b|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if summary_match:
        summary = re.sub(r"\s+", " ", summary_match.group(1)).strip()

    return {"title": title, "summary": summary}


def extract_text_from_pdf(pdf_path: str) -> str:
    resolved_path = require_within_output(pdf_path)
    if resolved_path.suffix.lower() != ".pdf":
        raise ValueError("A PDF file is required.")

    try:
        import pdfplumber  # type: ignore
    except Exception as exc:
        raise RuntimeError("pdfplumber is required to read generated resumes.") from exc

    fragments: list[str] = []
    with pdfplumber.open(str(resolved_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                fragments.append(text.strip())

    combined = "\n\n".join(fragments).strip()
    if not combined:
        raise RuntimeError("Could not read text from the generated PDF.")
    return combined


def normalize_skill_item_text(item: str) -> str:
    text = re.sub(r"\s+", " ", str(item or "").strip())
    text = re.sub(r"[\[\]\(\)]", "", text)
    text = re.sub(r"\s*/\s*", ", ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" ,.;")


def normalize_skill_dedupe_key(item: str) -> str:
    text = normalize_skill_item_text(item).lower()
    text = re.sub(r"[()]", "", text)
    text = re.sub(r"[^a-z0-9+/ ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def skill_item_looks_like_model_meta(item: str) -> bool:
    text = normalize_skill_item_text(item).lower()
    if not text:
        return False

    meta_markers = (
        "sorry",
        "please output",
        "corrected json",
        "however",
        "note:",
        "i'm going to",
        "i will revise",
        "remove uncertain",
        "must return valid json",
        "adhere to rules",
        "trusted items",
        "interruption",
    )
    return any(marker in text for marker in meta_markers)


def expand_skill_items(raw_items: list) -> list[str]:
    expanded: list[str] = []
    for raw_item in raw_items or []:
        cleaned = normalize_skill_item_text(raw_item)
        if not cleaned:
            continue
        parts = [part.strip(" ,.;") for part in cleaned.split(",")]
        non_empty_parts = [part for part in parts if part]
        if len(non_empty_parts) >= 2:
            expanded.extend(non_empty_parts)
        else:
            expanded.append(cleaned)
    return expanded


def normalize_updated_skills(skills_payload: list[dict]) -> list[dict]:
    if not isinstance(skills_payload, list):
        return []

    category_buckets: dict[str, list[str]] = {}
    encountered_categories: list[str] = []
    global_seen: set[str] = set()

    for entry in skills_payload:
        category = str(entry.get("category", "")).strip()
        if category not in ALLOWED_SKILL_CATEGORIES:
            continue

        if category not in category_buckets:
            category_buckets[category] = []
            encountered_categories.append(category)
        bucket = category_buckets[category]
        local_seen: set[str] = {normalize_skill_dedupe_key(item) for item in bucket}

        for item in expand_skill_items(entry.get("items", [])):
            if not item:
                continue
            if skill_item_looks_like_model_meta(item):
                continue
            key = normalize_skill_dedupe_key(item)
            if not key or key in local_seen or key in global_seen:
                continue
            bucket.append(item)
            local_seen.add(key)
            global_seen.add(key)

    normalized: list[dict] = []
    for category in encountered_categories:
        if len(category_buckets[category]) < 2:
            continue
        normalized.append({
            "category": category,
            "items": category_buckets[category],
        })

    return normalized


def infer_skill_category_order_key(role_family: str) -> str:
    family = (role_family or "").strip().lower()
    for known_family, key in ROLE_FAMILY_TO_SKILL_ORDER_KEY.items():
        if known_family in family:
            return key
    if "integration" in family and not any(term in family for term in ("solution", "implementation", "customer", "pre-sales", "presales")):
        return "backend_application"
    if "gtm" in family or "go-to-market" in family or "go to market" in family or "revops" in family or "revenue engineering" in family:
        return "gtm_engineering"
    if "data" in family or "analytics" in family:
        return "data_engineering"
    if "platform" in family or "distributed" in family or "infrastructure" in family:
        return "platform_distributed"
    if "embedded" in family or "system software" in family:
        return "embedded_systems"
    if "solution" in family or "implementation" in family:
        return "solutions_engineering"
    if "marketing analyst" in family:
        return "analyst_marketing"
    if "business analyst" in family or "operations analyst" in family:
        return "analyst_business"
    if "analyst" in family or "analytics" in family:
        return "analyst_data"
    if "ai" in family:
        return "ai_application"
    if "backend" in family:
        return "backend_application"
    return "fullstack_product"


def _analysis_route_signals(analysis_payload: dict) -> str:
    scalar_fields = (
        "target_role",
        "role_family",
        "core_problem",
        "hire_problem",
        "system_description",
    )
    list_fields = (
        "desired_outcomes",
        "top_requirements",
        "secondary_requirements",
        "responsibilities",
        "workflows",
        "skills_mentioned",
        "evidence_terms",
    )
    values = [str(analysis_payload.get(field, "")).strip() for field in scalar_fields]
    for field in list_fields:
        values.extend(str(item).strip() for item in (analysis_payload.get(field) or []))
    return " ".join(value for value in values if value).lower()


def _looks_like_growth_product_engineering(analysis_payload: dict) -> bool:
    signals = _analysis_route_signals(analysis_payload)
    target = " ".join(
        [
            str(analysis_payload.get("target_role", "")).strip(),
            str(analysis_payload.get("role_family", "")).strip(),
        ]
    ).lower()
    if not any(marker in target for marker in ("growth engineer", "growth product", "product growth")):
        return False

    product_growth_markers = (
        "activation funnel",
        "submission funnel",
        "experimentation",
        "a/b",
        "product analytics",
        "attribution",
        "instrumentation",
        "north-star",
        "north star",
        "product feature",
        "marketplace",
    )
    engineering_markers = (
        "backend",
        "frontend",
        "python",
        "postgres",
        "react",
        "javascript",
        "typescript",
        "aws",
        "design to production",
    )
    gtm_system_markers = (
        "crm",
        "revops",
        "salesforce",
        "hubspot",
        "lead routing",
        "lead enrichment",
        "outbound sequencing",
        "sales automation",
        "marketing automation",
        "pipeline reporting",
    )
    product_score = sum(marker in signals for marker in product_growth_markers)
    engineering_score = sum(marker in signals for marker in engineering_markers)
    gtm_system_score = sum(marker in signals for marker in gtm_system_markers)
    return product_score >= 2 and engineering_score >= 2 and gtm_system_score == 0


def _looks_like_ai_assisted_software_engineering(analysis_payload: dict) -> bool:
    signals = _analysis_route_signals(analysis_payload)
    role_family = str(analysis_payload.get("role_family", "")).strip().lower()
    if role_family != "ai application engineering":
        return False

    application_architecture_markers = (
        "monolith",
        "service oriented",
        "service-oriented",
        "microservice",
        "domain driven",
        "domain-driven",
        ".net",
        "c#",
        "react",
        "postgres",
        "event-driven",
    )
    ai_product_markers = (
        "rag",
        "retrieval augmented",
        "model serving",
        "model inference",
        "embedding",
        "vector search",
        "llm api",
        "ai feature",
        "agent orchestration",
        "tool calling",
    )
    architecture_score = sum(marker in signals for marker in application_architecture_markers)
    ai_product_score = sum(marker in signals for marker in ai_product_markers)
    return architecture_score >= 3 and ai_product_score == 0


def generation_route_key_for_analysis(analysis_payload: dict | None) -> str:
    analysis_payload = analysis_payload or {}

    # These two job shapes are commonly misrouted by surface words such as
    # "growth", "AI-augmented", or named coding assistants.
    if _looks_like_growth_product_engineering(analysis_payload):
        return "growth_product"
    if _looks_like_ai_assisted_software_engineering(analysis_payload):
        return "backend_application"

    explicit_route = str(analysis_payload.get("generation_route_key", "")).strip()
    if explicit_route in GENERATION_ROUTE_CONFIG:
        return explicit_route

    role_family = str(analysis_payload.get("role_family", "")).strip()
    inferred_skill_key = infer_skill_category_order_key(role_family)
    inferred_prompt_key = infer_prompt_family_key(role_family)
    legacy_skill_key = str(analysis_payload.get("skill_category_order_key", "")).strip()
    legacy_prompt_key = str(analysis_payload.get("prompt_family_key", "")).strip()

    for route_key, config in GENERATION_ROUTE_CONFIG.items():
        if (
            legacy_skill_key
            and legacy_prompt_key
            and config["skill_category_order_key"] == legacy_skill_key
            and config["prompt_family_key"] == legacy_prompt_key
        ):
            return route_key

    special_prompt_routes = {
        "data_science": "data_science",
        "agentic_ai_engineering": "agentic_ai_engineering",
        "security_engineering": "security_engineering",
    }
    if inferred_prompt_key in special_prompt_routes:
        return special_prompt_routes[inferred_prompt_key]

    skill_route_map = {
        "fullstack_product": "fullstack_product",
        "backend_application": "backend_application",
        "data_engineering": "data_engineering",
        "platform_distributed": "platform_distributed",
        "embedded_systems": "embedded_systems",
        "ai_application": "ai_application",
        "solutions_engineering": "solutions_engineering",
        "analyst_data": "analyst_data",
        "analyst_business": "analyst_business",
        "analyst_marketing": "analyst_marketing",
        "gtm_engineering": "gtm_engineering",
    }
    return skill_route_map.get(inferred_skill_key, "fullstack_product")


def generation_route_config_for_analysis(analysis_payload: dict | None) -> dict:
    return GENERATION_ROUTE_CONFIG[generation_route_key_for_analysis(analysis_payload)]


def skill_category_order_key_for_analysis(analysis_payload: dict | None) -> str:
    return generation_route_config_for_analysis(analysis_payload)["skill_category_order_key"]


def prompt_family_key_for_analysis(analysis_payload: dict | None) -> str:
    return generation_route_config_for_analysis(analysis_payload)["prompt_family_key"]


def skill_category_order_for_key(order_key: str) -> list[str]:
    return list(SKILL_CATEGORY_ORDER_TEMPLATES.get(order_key, SKILL_CATEGORY_ORDER_TEMPLATES["fullstack_product"]))


def infer_prompt_family_key(role_family: str) -> str:
    family = (role_family or "").strip().lower()
    for known_family, key in ROLE_FAMILY_TO_PROMPT_FAMILY_KEY.items():
        if known_family in family:
            return key
    if "integration" in family and not any(term in family for term in ("solution", "implementation", "customer", "pre-sales", "presales")):
        return "software_engineering"
    if "gtm" in family or "go-to-market" in family or "go to market" in family or "revops" in family or "revenue engineering" in family:
        return "gtm_engineering"
    if "marketing analyst" in family:
        return "analyst_marketing"
    if "business analyst" in family or "operations analyst" in family:
        return "analyst_business"
    if "analyst" in family or "analytics" in family:
        return "analyst_data"
    if "data engineering" in family:
        return "data_engineering"
    if "platform" in family or "distributed" in family or "infrastructure" in family or "system software" in family:
        return "platform_systems"
    if "solution" in family or "implementation" in family:
        return "solutions_customer"
    return "software_engineering"


def normalize_skills_for_order(skills_payload: dict, ordered_categories: list[str]) -> dict:
    normalized = normalize_updated_skills(skills_payload.get("updated_skills", []))
    allowed_categories = set(ordered_categories)
    by_category = {
        str(entry.get("category", "")).strip(): entry.get("items", [])
        for entry in normalized
        if str(entry.get("category", "")).strip() in allowed_categories
    }
    return {
        "updated_skills": [
            {"category": category, "items": by_category[category]}
            for category in ordered_categories
            if category in by_category and len(expand_skill_items(by_category[category])) >= 2
        ]
    }


def build_ai_analysis_prompt() -> str:
    return "\n".join(
        [
            "You are a resume role analyzer.",
            "Assume the candidate has 4+ years of experience.",
            "Analyze the JD and return a compact role model for downstream resume generation.",
            "Do not mirror the JD or invent unsupported domain expertise.",
            "Rank the job requirements instead of trying to preserve everything equally.",
            "Infer the company context, role family, problem, system, skills and technologies mentioned, and behavioral signals.",
            "Role family must describe the actual job shape, not a generic software-engineer label.",
            "Prefer precise role-family labels such as: full-stack product engineering, backend application engineering, data engineering, analytics engineering, data science, machine learning engineering, platform engineering, distributed systems engineering, cloud infrastructure engineering, security engineering, application security engineering, cloud security engineering, solutions engineering, implementation engineering, AI application engineering, agentic AI engineering, AI agent engineering, data analyst, business analyst, marketing analyst, product analyst, operations analyst, or GTM engineering.",
            "Choose exactly one generation_route_key from the fixed schema.",
            "The generation route is the single downstream routing decision; do not make separate prompt or skill-category routing decisions.",
            "Use growth_product for product engineers who build activation funnels, experimentation, instrumentation, attribution, lifecycle product infrastructure, or marketplace growth systems with production backend/frontend code.",
            "Do not classify a product Growth Engineer as GTM engineering merely because the JD mentions growth, lifecycle, acquisition, attribution, or marketing collaboration.",
            "Reserve gtm_engineering for CRM, RevOps, lead routing, enrichment, outbound sequencing, pipeline reporting, and sales or marketing system automation.",
            "AI coding assistants such as Cursor, Claude Code, or Copilot are supporting tools and do not make a software architecture role AI application engineering.",
            "If the JD centers on SQL, PySpark, Snowflake, ETL, orchestration, dashboards, or data quality, classify it as data engineering or analytics engineering rather than generic software engineering.",
            "If the JD centers on machine learning, statistical modeling, experimentation, forecasting, recommendation systems, NLP, computer vision, model training, feature engineering, model evaluation, or ML platforms, classify it as data science or machine learning engineering rather than data engineering.",
            "If the JD centers on SQL analysis, dashboards, reporting, BI tools, Excel, stakeholder insights, KPI tracking, funnel metrics, or ad hoc analysis without building pipelines or ML models, classify it as data analyst rather than data engineering.",
            "If the JD centers on Rust, Linux, concurrency, networking, security platforms, or low-level services, classify it as platform engineering or distributed systems engineering rather than generic full-stack work.",
            "If the JD centers on AI agents, agent orchestration, agent-to-agent communication, autonomous agents, tool calling, function calling, MCP, Model Context Protocol, agent governance, programmable policy for agents, LLM APIs, OpenAI, Anthropic, LangChain, LangGraph, or agent frameworks, classify it as agentic AI engineering rather than distributed systems or backend engineering.",
            "If the JD centers on reporting, dashboards, SQL analysis, business insights, stakeholder support, campaign measurement, attribution, funnel metrics, requirements gathering, or KPI analysis, classify it as an analyst family rather than software engineering.",
            "If the JD is about building internal or product-side integrations across APIs, cloud services, microservices, authentication, event-driven systems, CI/CD, DevOps, or backend services, classify it as backend application engineering or cloud integration engineering rather than solutions engineering.",
            "Reserve solutions engineering and implementation engineering for clearly customer-facing roles such as demos, onboarding, external implementations, technical account support, pre-sales, sales engineering, or customer adoption work.",
            "If the JD centers on CRM systems, revops, lead routing, enrichment, outbound tooling, lifecycle automation, sequencing, GTM workflows, pipeline reporting, or sales/marketing system automation, classify it as GTM engineering rather than software engineering or generic analyst work.",
            "If the JD centers on vulnerability management, application security, cloud security, identity and access management, threat detection, incident response, compliance, GRC, SOC workflows, SIEM, secrets management, encryption, OWASP, NIST, ISO 27001, SOC 2, HIPAA, PCI, or security tooling, classify it as security engineering rather than backend or platform engineering.",
            "If the JD mentions Excel, Power BI, Tableau, Looker, Jira, Confluence, Salesforce, SAP, Oracle, Workday, PeopleSoft, Banner, WMS, Manhattan SCALE, Manhattan Active, Blue Yonder, ERP, SCM, or CRM platforms, preserve those as important analyst or systems signals rather than treating them like minor supporting tools.",
            "If the JD mentions Clay, Salesforce, HubSpot, Outreach, Apollo, Marketo, 6sense, Gong, Customer.io, ZoomInfo, Smartlead, Instantly, HeyReach, Nooks, Warmly, lead routing, enrichment, outbound sequencing, or GTM automation, preserve those as important GTM systems and workflow signals.",
            "Return one unified skills_mentioned list containing all important skills, tools, frameworks, platforms, and technologies explicitly mentioned anywhere in the JD, including required, preferred, and nice-to-have items.",
            "Return top_requirements as the 3-4 requirements that should win the resume first scan.",
            "Return secondary_requirements as the next most useful supporting requirements.",
            "Return evidence_terms as the important terms that are safe to use only when later bullets or summary wording clearly prove them with an action, workflow, system, or measurable result.",
            "Return domain_terms as the niche product, domain, or industry terms that should be used carefully and only when the later resume content can support them honestly.",
            "Prefer recruiter-scan priorities over exhaustive JD coverage.",
            "Return only structured analysis matching the schema.",
        ]
    )


def build_ai_resume_prompt(enabled_experience_keys: list[str] | None = None) -> str:
    blueprint_lines = []
    for blueprint in filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_experience_keys):
        bullet_rule = f"{blueprint['bullet_min']}" if blueprint["bullet_min"] == blueprint["bullet_max"] else f"{blueprint['bullet_min']}-{blueprint['bullet_max']}"
        blueprint_lines.append(
            f"- {blueprint['company']} | {blueprint['location']} | {blueprint['dates']} | bullets: {bullet_rule} | anchor: {blueprint['anchor']}"
        )

    return "\n".join(
        [
            "You are a resume reconstruction engine.",
            "Your job is to build a realistic, production-level targeted resume aligned to a given job description.",
            "This resume is a targeted fit document, not a full professional biography.",
            "Its job is to help a recruiter quickly see why this candidate is a strong fit and move to the next step.",
            "",
            "You MUST:",
            "- Assume the candidate has 4+ years of experience",
            "- Use the JD analysis as the source of truth",
            "- Map capabilities from real engineering systems, not keywords",
            "- Never copy or mirror job description language",
            "- Never invent unrealistic tools or fake expertise",
            "- Prioritize the top_requirements first instead of trying to cover the whole JD",
            "- Use domain_terms only when the resume content can support them honestly",
            "- Ensure every bullet reflects explainable, production-level work",
            "- Optimize for recruiter first-scan clarity before deeper reading",
            "",
            "EXECUTION ORDER (MANDATORY):",
            "1. Build resume sections from the JD analysis",
            "2. Validate all constraints internally",
            "3. If any constraint fails, regenerate internally before output",
            "",
            "HARD CONSTRAINTS (NON-NEGOTIABLE):",
            "",
            "TITLE:",
            "- Format: Software Engineer (Specialization)",
            f"- {TITLE_WORD_MIN}-{TITLE_WORD_MAX} words",
            "- Must reflect the core problem, not tools",
            "- If the JD clearly signals seniority, preserve that seniority in the title",
            "- If the role is clearly full-stack but backend-heavy, reflect that balance instead of collapsing to backend only",
            "- The final title must read like a natural human job title, not an awkward template artifact",
            "- Prefer standard title phrasing such as 'Senior Full-Stack Engineer' over unnatural constructions",
            "- If the JD already uses a clean, standard engineering title, stay close to that title instead of over-rewriting it",
            "",
            "SUMMARY:",
            f"- {SUMMARY_WORD_MIN}-{SUMMARY_WORD_MAX} words",
            "- Must include systems built, technologies used, and problems solved",
            "- No generic phrases",
            "- No tool dumping",
            "- Must be concise, engaging, and aligned to the target role",
            "- Must reflect strengths, relevant skills, and years of experience in a compelling but nondramatic way",
            "- Should feel like a strong professional summary, not a keyword list or generic opener",
            "- Build it from the core problem, target system, and strongest transferable evidence",
            "- It should help a recruiter understand fit within seconds",
            "- Adapt the summary to the JD family:",
            "  - platform/distributed roles: emphasize systems, APIs, reliability, scale",
            "  - business-backend delivery roles: emphasize architecture, delivery, ownership, cross-functional execution",
            "  - customer-facing solutions / FAE / technical pre-sales roles: emphasize demos, integrations, troubleshooting, technical communication, and adoption support",
            "- Align to the company's problem space without claiming direct domain expertise unless it is clearly grounded by prior experience",
            "- Prefer broader believable product or workflow framing over company-specific domain claims when the domain match is only transferable",
            "- For customer-facing solutions / FAE / technical pre-sales roles, do not imply direct domain ownership or hardware expertise unless clearly grounded by prior experience",
            "- Use natural first-pass recruiter language, not compressed jargon blocks",
            "- Keep the summary readable in one pass; do not stack too many systems or tools into a single clause",
            "",
            "SKILLS:",
            "- Category: comma-separated values only",
            "- No sentences",
            "- Exactly one category per line",
            "- Never merge multiple category labels into one line",
            "- Each category label must be separate from its values",
            "- Skill items must be plain phrases separated by commas",
            "- Do not use slashes, parentheses, brackets, or qualifier-style annotations inside skill items",
            "- Each skill item must represent exactly one skill or capability",
            "- Do not pack multiple skills into one item",
            "- Must include both:",
            "  - Core skills from the problem",
            "  - Supporting skills needed to build, deploy, scale, monitor, secure, and debug the system",
            "- Must represent a complete system-capable toolkit",
            "- Supporting skills must come from system behavior, not keyword stuffing",
            "- The final skills must feel derived, not copied",
            "- The section must answer: what languages and technologies is this person hands-on with?",
            "- Include only relevant, believable, day-to-day skills",
            "- The skills section is for scanability; the experience section is where those skills are proven through usage",
            "- Keep the JD-aligned stack visible when the role clearly favors a primary language or framework family",
            "- Include both named technologies and the broader engineering capabilities demonstrated by the work",
            "- Broader skills should capture how the candidate operates as an engineer, such as object-oriented backend development, application logic, debugging, tuning, delivery, and UI development when supported by the work",
            "- If the bullets are adapted toward a target stack, the skills section must still reflect the broader engineering context behind those bullets",
            "- The skills section must not collapse into only a narrow tool list",
            "- Order categories for recruiter scanability: strongest hands-on languages first, then backend/frontend, then data, cloud, messaging, observability, devops, security, testing, and broader system concepts",
            "- Do not repeat the same skill or concept across multiple categories",
            "- Prefer crisp hands-on skill names over phrase-heavy restatements of the same capability",
            "- Do not try to complete every JD keyword with a matching tool if the candidate's background does not strongly support it",
            "- Prefer the smallest believable set of hands-on technologies over a perfect-looking stack match",
            "- Expected pattern:",
            "  - Programming Languages: Python, Java, SQL",
            "  - Backend Engineering: REST API design, Application logic, Service architecture",
            "  - Testing & Quality: Unit testing, Integration testing, Debugging",
            "- Avoid packed or descriptive items like 'AWS EC2 Lambda S3', 'JWT OAuth2', or 'Python expertise for backend APIs'",
            "",
            "EXPERIENCE:",
            "- Follow the fixed company, location, and date structure below exactly",
            "- The experience title field must contain only the role title text",
            "- Never repeat company name, location, or dates inside the role title field",
            "- Bullet count per company must match exactly",
            f"- Each bullet must be {EXPERIENCE_BULLET_WORD_MIN}-{EXPERIENCE_BULLET_WORD_MAX} words",
            "- Recent and relevant roles should do more of the selling than older roles",
            "- Older or less relevant roles should stay supportive and concise",
            "- Expected experience pattern:",
            "  - Company/location line",
            "  - Role title and dates line",
            "  - 1 bullet per achievement",
            "  - Each bullet is one complete production-level accomplishment",
            "",
            "BULLET STRUCTURE (MANDATORY):",
            "Each bullet must follow:",
            "[Strong Verb] + [System built/optimized] + using [1-3 tools] + under [constraint or engineering decision] + resulting in [grounded measurable impact or a concrete qualitative outcome].",
            "",
            "Each bullet must include:",
            "- Real system context",
            "- 1-3 tools or relevant technical skills",
            "- At least one:",
            "  - constraint such as scale, latency, concurrency, failures",
            "  - or engineering decision such as caching, batching, async, indexing",
            "- Use a metric only when that exact number is grounded in candidate/profile evidence or the immutable experience blueprint",
            "- Never invent, estimate, infer, or borrow a number from the JD to make a bullet look measurable",
            "- When no grounded metric exists, state a concrete qualitative outcome such as improved reliability, clearer ownership, faster resolution, safer delivery, or reduced manual work without adding a number",
            "- Use active language and show what changed because of the work",
            "- Keep one main idea per bullet; do not cram multiple unrelated systems into the same sentence",
            "",
            "ANTI-GENERIC FILTER:",
            "Before finalizing each bullet, ask:",
            "\"Can this apply to 1000 engineers?\"",
            "If yes, rewrite with:",
            "- specific system",
            "- real constraint",
            "- technical decision",
            "",
            "TOOL USAGE RULE:",
            "- Minimum: 1 tool",
            "- Maximum: 3 tools",
            "- Tools must be tied to action",
            "- No buzzword stacking",
            "- Mention specific technologies where they add useful proof and context, not just decoration",
            "- Prefer simpler believable technical wording over highly specific infrastructure substitution when both would make the same point",
            "- Do not introduce named infrastructure products, platforms, or observability tools unless they materially improve clarity and feel realistically grounded in the candidate's work",
            "",
            "SKILL DERIVATION RULE:",
            "- Use analysis.skills_mentioned deliberately",
            "- Skills should reflect what the JD explicitly needs to solve the main problem and run the surrounding system in production",
            "- Ask: what is required to build, run, scale, and debug this system?",
            "- Do not stop at JD-facing skills alone",
            "- Make the skills ATS-friendly by including the important language from the JD naturally, but only when it fits the problem and system",
            "- Prioritize the strongest and most relevant hands-on skills first",
            "",
            "ORIGINALITY RULE:",
            "- Preserve originality",
            "- Bullets must sound like specific engineering work from the candidate's background, not templated JD paraphrases",
            "- Use JD-relevant capabilities, but map them through believable transferable systems rather than forcing exact stack matches everywhere",
            "- Prefer analogous systems the candidate could realistically have built over perfect keyword alignment",
            "- Tailor by emphasis and detail selection, not by rewriting history",
            "- Do not rename the candidate's historical roles just to match the target role family",
            "- If the target role is FAE, solutions engineering, sales engineering, or technical pre-sales, preserve believable engineering titles and pivot the summary and bullets toward customer-facing work instead",
            "- When a very specific modern stack detail is not necessary, prefer the simpler believable description of the work",
            "- Prefer grounded engineering descriptions over named-tool substitution when either would communicate the same capability",
            "",
            "PROJECT STORY RULE:",
            "- Each company must read as one coherent project story",
            "- Early bullets establish system and problem",
            "- Middle bullets show implementation and decisions",
            "- Later bullets show validation, scale, reliability, or impact",
            "- Do not let every company become the same platform story; keep each company aligned to its anchor",
            "- Keep strong realism boundaries by company and era: do not leak later specialization backward into earlier roles, and do not force every employer into the target JD's role family",
            "",
            "ATS RULE:",
            "- Align language and phrasing with the JD naturally",
            "- Include relevant keywords and qualifications where they fit credibly",
            "- Optimize for ATS compatibility without sounding like keyword stuffing",
            "- The resume should appear strongly aligned to the role, but still read well to a human recruiter in under 10 seconds",
            "- Write for recruiter and hiring-manager scan first, not for imaginary robot rejection",
            "",
            "SUMMARY AND BULLET IMPACT RULE:",
            "- Focus on accomplishments more than responsibilities",
            "- Use measurable achievements only when the exact metric is grounded in candidate/profile evidence or an immutable experience blueprint",
            "- Never invent, estimate, or infer a metric; JD numbers are requirements, not candidate evidence",
            "- When no grounded number exists, make impact visible through a concrete qualitative result such as reliability, clarity, adoption, maintainability, safer delivery, or reduced manual effort",
            "- Be specific instead of hand-wavy whenever the candidate could realistically defend the detail",
            "- Do not force exact years of experience into the summary unless that count is explicitly grounded by the candidate profile or clearly implied by the fixed timeline",
            "- Prefer a compact positioning summary over a dense stack summary",
            "- Preserve an exact grounded metric when useful; never round, soften, estimate, or manufacture a number",
            "- Avoid hyper-specific business impact numbers, revenue figures, or scale claims unless they feel strongly defensible from the candidate's role and company context",
            "",
            "HUMANIZATION RULE:",
            "- The final writing must sound human, specific, and professional",
            "- Use nondramatic language",
            "- Avoid stiff, overly polished, repetitive, or obviously AI-generated phrasing",
            "- Vary sentence openings and structures across bullets",
            "- Replace generic phrases with specific engineering language when possible",
            "- Keep strong action-driven tone, but make it sound natural and believable",
            "- The result should read like authentic resume writing from a strong engineer, not marketing copy",
            "- If a summary or bullet sounds like benchmark distributed-systems copy, simplify it into more natural resume language",
            "- Prefer natural title and summary phrasing that a hiring manager would recognize instantly without mentally rewriting it",
            "- Prefer simpler sentence structure over dense, over-engineered wording",
            "- Avoid stacked noun phrases like 'lead-to-cash and ingestion/retrieval systems' when a simpler phrase would say the same thing",
            "- Avoid resume bullets that sound too perfectly templated; natural variation is better than rigid symmetry",
            "",
            "HUMANIZATION EXAMPLES:",
            "- Less human: 'Led GTM platform delivery by designing lead-to-cash and ingestion/retrieval systems using APIs, Salesforce, and middleware under tight SLAs, improving pipeline visibility by 28%.'",
            "- More human: 'Built automated lead-routing and reporting workflows across Salesforce and middleware, improving pipeline visibility and cutting manual handoffs for GTM teams.'",
            "- Less human: 'Directed applied-AI retrieval workflows using APIs and Python under privacy and latency constraints, delivering a 22% improvement in relevancy.'",
            "- More human: 'Improved retrieval workflows in Python and APIs, raising result quality while keeping latency and privacy requirements in line for customer-facing search.'",
            "",
            "TIMELINE RULE:",
            "- Ensure realistic technology progression across roles",
            "- Only use technologies in a company section if they fit that time period, the company's anchor work, and believable exposure progression",
            "- Favor realistic evolution of experience over dramatic stack jumps",
            "",
            "FINAL VALIDATION (MANDATORY BEFORE OUTPUT):",
            "- Title format correct",
            "- Summary within word count",
            "- Skills are system-capable, including core and supporting skills",
            "- Bullet counts per company correct",
            "- Each bullet has system + tool + constraint/decision + either a grounded metric or a concrete qualitative outcome",
            "- Each company reads as one coherent project story",
            "- Skills follow the expected one-item-per-skill pattern",
            "",
            "Do not output validation steps. Only output the final result matching the schema.",
            "",
            "Fixed experience blueprints:",
            *blueprint_lines,
        ]
    )


def build_ai_resume_core_prompt() -> str:
    return "\n".join(
        [
            "You are a resume reconstruction engine.",
            "Build only the core resume sections: Updated Title, Updated Summary, and Updated Skills.",
            "Assume the candidate has 4+ years of experience.",
            "Use the JD analysis as the source of truth.",
            "This is a targeted fit document for recruiter first-scan clarity, not a full biography.",
            "Do not mirror the JD. Do not invent unrealistic tools or fake expertise.",
            "Write naturally, specifically, and without keyword stuffing.",
            "",
            "TITLE RULES:",
            "- Natural human job title phrasing",
            f"- {TITLE_WORD_MIN}-{TITLE_WORD_MAX} words",
            "- Preserve seniority when clearly signaled",
            "- Reflect the core problem, not tool names",
            "- If the JD title is already clean and standard, stay close to it instead of over-optimizing it",
            "",
            "SUMMARY RULES:",
            f"- {SUMMARY_WORD_MIN}-{SUMMARY_WORD_MAX} words",
            "- Build from the core problem, target system, and strongest transferable evidence",
            "- Include systems built, technologies used, and problems solved",
            "- Do not dump tools or force exact years unless clearly grounded",
            "- Use nondramatic, recruiter-readable language",
            "- Keep the writing easy to scan in one pass; avoid dense multi-clause phrasing and stacked jargon",
            "- Match the summary style to the JD family: systems/reliability for platform roles, ownership/delivery for senior backend roles, and customer-facing integration/adoption support for solutions or pre-sales roles",
            "- Align to the company's domain without pretending direct domain specialization when the evidence is only adjacent or transferable",
            "- For customer-facing solutions / FAE / technical pre-sales roles, pivot the summary without pretending the candidate held that exact title historically",
            "- Prefer one clear positioning statement over two compressed half-ideas",
            "",
            "SKILLS RULES:",
            "- Category: comma-separated values only",
            "- Exactly one category per line",
            "- Never merge category labels",
            "- Use only allowed categories from the schema",
            "- Skill items must be plain comma-separated phrases",
            "- Do not use slashes, parentheses, brackets, or qualifier-style annotations inside skill items",
            "- Each skill item must represent exactly one skill or capability",
            "- Do not pack multiple skills into one item",
            "- Include both core JD-facing skills and supporting production-system skills",
            "- Answer: what languages and technologies is this person hands-on with?",
            "- Include only relevant, believable, day-to-day skills",
            "- Prioritize the strongest and most relevant hands-on skills first",
            "- Keep the primary JD-aligned stack visible when the role clearly favors one",
            "- Include broader engineering capabilities shown by the work, not just named tools",
            "- The section must balance specific technologies with broader product-engineering or backend-engineering capabilities",
            "- Do not repeat the same skill or concept across categories",
            "- Prefer concrete hands-on skill names over abstract resume phrasing",
            "- Do not overfill the section with every plausible JD-adjacent tool; include only the strongest believable technologies",
            "- Expected pattern:",
            "  - Programming Languages: Java, SQL, JavaScript",
            "  - Backend Engineering: REST API design, Application logic, Object-oriented development",
            "  - Testing & Quality: Unit testing, Integration testing, Debugging",
            "",
            "ATS AND TONE RULES:",
            "- Align naturally to the JD",
            "- Keep human readability first",
            "- Sound like authentic resume writing, not marketing copy",
            "- If a skill name feels like a fragment from a sentence rather than a real recruiter-scan term, rewrite it",
            "- Do not leave truncated or malformed items in the final section",
            "",
            "Return only the final result matching the schema.",
        ]
    )


def build_ai_resume_title_summary_prompt(prompt_family_key: str = "software_engineering") -> str:
    family_rules = {
        "software_engineering": [
            "- adapt by role family, culture signals, and the skills, responsibilities, and workflows mentioned in the analysis object",
            "- surface the strongest JD-mentioned technologies and workflows naturally in the summary when they fit the candidate-shaped story",
            "- platform roles: emphasize systems, reliability, APIs, scale",
            "- backend delivery roles: emphasize ownership, execution, architecture",
            "- customer-facing solutions roles: emphasize integrations, troubleshooting, technical communication",
        ],
        "data_engineering": [
            "- adapt by role family and emphasize SQL, pipelines, warehousing, orchestration, data quality, and reliable data delivery",
            "- mention frontend work only as supporting capability for data users when relevant",
            "- keep the summary focused on data systems and operational outcomes rather than generic software engineering language",
        ],
        "data_science": [
            "- emphasize modeling, experimentation, feature work, model evaluation, ML platforms, and measurable decision or product impact",
            "- mention concrete ML and data tools when grounded in the JD, such as Python, SQL, pandas, scikit-learn, PyTorch, TensorFlow, MLflow, Databricks, SageMaker, or Vertex AI",
            "- do not frame data science roles as data engineering unless pipelines are clearly central to the JD",
        ],
        "agentic_ai_engineering": [
            "- emphasize AI-agent infrastructure, agent orchestration, tool protocols, LLM APIs, governance, policy controls, and production reliability",
            "- surface MCP, tool calling, function calling, OpenAI, Anthropic, LangChain, LangGraph, vector stores, evals, tracing, and policy tools when grounded in the JD",
            "- frame the role as agentic AI infrastructure rather than generic distributed systems or backend engineering",
        ],
        "platform_systems": [
            "- emphasize scale, reliability, APIs, observability, and system performance",
            "- prioritize platform constraints, architecture tradeoffs, and resilient delivery over product UI language",
        ],
        "security_engineering": [
            "- emphasize security engineering, identity, cloud security, application security, compliance, detection, incident response, and risk reduction",
            "- mention security tools, frameworks, and standards when they are grounded in the JD",
            "- do not frame the role as backend engineering unless backend work is clearly central to the JD",
        ],
        "analyst_data": [
            "- emphasize SQL, dashboards, reporting, insights, metrics, and stakeholder decision support",
            "- frame the role around analysis, measurement, and business impact rather than software delivery",
            "- mention tools and workflows that support insight generation, experimentation, and communication",
            "- preserve analyst stack terms like Excel, Power BI, Tableau, Looker, and domain systems when the JD mentions them",
            "- if the JD does not explicitly mention a named analyst tool or platform, use generic analyst workflow language instead of inventing one",
            "- if the JD does not mention named tools, prefer phrases like reporting workflows, dashboarding, requirements support, data analysis, or stakeholder communication instead of vendor names",
        ],
        "analyst_business": [
            "- emphasize requirements, process analysis, KPI reporting, stakeholder communication, and turning findings into execution plans",
            "- frame the role around business workflows, analysis, and cross-functional clarity rather than engineering implementation",
            "- preserve business-system and operations tools like Excel, Jira, Confluence, ERP, WMS, CRM, SAP, Oracle, Workday, PeopleSoft, Banner, Manhattan, and Blue Yonder when they are mentioned",
            "- if the JD does not explicitly mention a named enterprise platform, use generic analyst and process language instead of inventing one",
            "- if the JD does not mention named tools, prefer phrases like requirements documentation, business readiness, testing support, product backlog support, KPI monitoring, or stakeholder engagement instead of vendor names",
        ],
        "analyst_marketing": [
            "- emphasize campaign analysis, attribution, funnel metrics, experimentation, and marketing reporting",
            "- frame the role around growth insights, customer behavior analysis, and cross-functional communication rather than engineering delivery",
            "- preserve marketing analytics and reporting tools like Excel, BI platforms, CRM systems, and attribution-oriented tooling when the JD mentions them",
            "- if the JD does not explicitly mention a named marketing or CRM platform, use generic analytics language instead of inventing one",
            "- if the JD does not mention named tools, prefer phrases like campaign reporting, funnel analysis, segmentation, lifecycle measurement, or stakeholder insights instead of vendor names",
        ],
        "gtm_engineering": [
            "- emphasize GTM automation, CRM and revops workflows, routing, enrichment, outbound systems, reporting, and cross-functional execution",
            "- frame the role around building and improving go-to-market systems rather than generic product engineering or generic analysis work",
            "- preserve GTM stack terms like Clay, Salesforce, HubSpot, Outreach, Apollo, Marketo, 6sense, Gong, Customer.io, ZoomInfo, and sequencing or enrichment tools when the JD mentions them",
            "- if the JD does not explicitly mention a named GTM platform, use generic GTM workflow language instead of inventing one",
        ],
        "solutions_customer": [
            "- emphasize integrations, troubleshooting, technical communication, stakeholder support, and adoption outcomes",
            "- keep the tone customer-facing and execution-oriented without pretending the candidate held the exact target title historically",
        ],
    }
    selected_rules = family_rules.get(prompt_family_key, family_rules["software_engineering"])
    return "\n".join(
        [
            "You are a resume reconstruction engine.",
            "Build only Updated Title and Updated Summary.",
            "Assume the candidate has 4+ years of experience.",
            "Use the analysis object as the source of truth.",
            "Do not copy JD wording or invent expertise.",
            "",
            "TITLE:",
            f"- {TITLE_WORD_MIN}-{TITLE_WORD_MAX} words",
            "- natural human title",
            "- preserve seniority when clearly signaled",
            "- stay close to a clean JD title",
            "- do not turn tool names into the title",
            "",
            "SUMMARY:",
            f"- {SUMMARY_WORD_MIN}-{SUMMARY_WORD_MAX} words",
            "- build from the company problem, hire problem, target system, and strongest transferable evidence",
            "- prioritize the top_requirements first; do not try to cover the whole JD",
            "- surface at most the 3-4 most important requirements prominently and naturally",
            "- include systems, technologies, and problems solved",
            "- do not state an explicit years-of-experience count unless it is clearly safe and helpful",
            "- align to the company's domain without overclaiming direct domain expertise",
            "- use domain_terms only when the wording is supported by real or adjacent evidence",
            "- every important JD term used in the summary must feel provable from the candidate story, not borrowed from the posting",
            "- do not echo company marketing language, product slogans, or copied business phrasing from the JD",
            "- prefer transferable product and workflow framing over company-specific wording when the domain match is only adjacent",
            "- optimize for credible fit, not exhaustive keyword coverage",
            "- keep the phrasing natural and easy to read aloud; avoid dense stacked clauses and resume-speak",
            "- prefer one clear central idea over a list-like sentence full of tools and workflows",
            *selected_rules,
            "",
            "Return only the final result matching the schema.",
        ]
    )


def build_ai_resume_skills_prompt(prompt_family_key: str = "software_engineering") -> str:
    family_rules = {
        "software_engineering": [
            "- prioritize named languages, frameworks, databases, cloud services, CI/CD tools, monitoring tools, and enterprise platforms",
            "- keep JD-mentioned languages, frameworks, platforms, and tools visible when they fit the category",
            "- do not add abstract engineering concepts unless they are named directly in the JD or clearly required to make the category readable",
        ],
        "data_engineering": [
            "- prioritize named data tools, databases, warehouses, orchestration tools, BI tools, SQL, Python, PySpark, and cloud data services",
            "- Data Engineering should include concrete orchestration or transformation tools when relevant: Airflow, Dagster, Prefect, dbt, AWS Glue, Azure Data Factory, Databricks, Spark, PySpark",
            "- Data & Storage should include concrete warehouses or databases when relevant: Snowflake, BigQuery, Redshift, Databricks, PostgreSQL, SQL Server, Oracle, S3, ADLS",
            "- keep frontend or API tools secondary unless the JD clearly makes them central",
            "- keep generic data capabilities out of skills unless they are named directly in the JD or already supported by the selected skills",
        ],
        "data_science": [
            "- prioritize ML and statistical tools, languages, notebooks, model platforms, data stores, and experiment tracking tools",
            "- Machine Learning & Statistics should include concrete items when relevant: scikit-learn, pandas, NumPy, SciPy, PyTorch, TensorFlow, XGBoost, LightGBM, statsmodels, MLflow, SageMaker, Vertex AI, Databricks ML",
            "- Data & Storage should include concrete databases, warehouses, or lakehouse tools when relevant: Snowflake, BigQuery, Databricks, Redshift, PostgreSQL, MongoDB, S3",
            "- avoid generic phrases such as predictive modeling, feature engineering, statistical analysis, machine learning workflows, or model evaluation unless the exact phrase appears in the JD",
        ],
        "agentic_ai_engineering": [
            "- prioritize agent infrastructure and LLM stack tools such as MCP, Model Context Protocol, tool calling, function calling, OpenAI API, Anthropic API, LangChain, LangGraph, AutoGen, CrewAI, Semantic Kernel, LlamaIndex, or Agents SDK when they fit the JD",
            "- include enterprise agent governance and observability tools when relevant: Open Policy Agent, Guardrails, LangSmith, Langfuse, Helicone, OpenTelemetry, MLflow, or Weights & Biases",
            "- Data & Storage should include agent memory and vector-store databases when relevant: Pinecone, Weaviate, Chroma, FAISS, pgvector, Milvus, Qdrant, Redis, PostgreSQL, MongoDB, or BigQuery",
            "- for agent orchestration or RAG-style roles, include at least one concrete vector or memory store in Data & Storage when it fits the JD context",
            "- include communication and orchestration infrastructure when relevant: Kafka, RabbitMQ, Temporal, gRPC, WebSockets, or Kubernetes",
            "- replace placeholder phrases with concrete tools when the JD supports them",
            "- never output placeholder skills such as Workflow engines, Automated pipelines, Distributed systems, Multi-agent systems, Programmable governance logic, Governance frameworks, Agent orchestration, or Communication standards",
        ],
        "platform_systems": [
            "- prioritize platform, reliability, observability, distributed-systems, and infrastructure terms",
            "- prioritize named infrastructure, observability, security, networking, operating-system, cloud, and deployment tools",
            "- prefer concrete systems tools and capabilities over product-oriented frontend language",
            "- do not use broad concepts like distributed systems, reliability, performance, or software design unless the JD names them directly or the selected skills make them clearly necessary",
        ],
        "security_engineering": [
            "- prioritize security tools, IAM platforms, auth protocols, SIEM and detection tools, vulnerability scanners, secrets-management tools, cloud-security services, endpoint tools, and compliance frameworks",
            "- Security & Auth should include concrete enterprise auth protocols and platforms when relevant: OAuth 2.0, OpenID Connect, SAML, JWT, SSO, MFA, RBAC, ABAC, Okta, Auth0, Microsoft Entra ID, Azure AD, Amazon Cognito, Ping Identity, Duo, HashiCorp Vault, or AWS KMS",
            "- include security standards and frameworks such as OWASP, NIST, ISO 27001, SOC 2, HIPAA, PCI DSS, CIS Benchmarks, and MITRE ATT&CK when they appear in the JD",
            "- keep Backend Engineering and frontend frameworks out of security skills unless the JD explicitly names them",
        ],
        "analyst_data": [
            "- prioritize SQL, querying, dashboards, reporting, data visualization, metrics, and experimentation terms",
            "- prefer analysis tools, BI platforms, and insight-generation capabilities over engineering infrastructure categories",
            "- preserve Excel, Power BI, Tableau, Looker, Python, R, and domain reporting systems prominently when the JD mentions them",
            "- if the JD does not explicitly mention a named analyst tool, do not invent one; use strong generic analyst capabilities instead",
            "- for analyst roles, keep process, reporting, stakeholder, and KPI terms in the analyst categories instead of forcing them into engineering categories",
            "- if the category is Tools & Platforms and the JD does not mention named tools, use generic items like reporting platforms, documentation systems, workflow tools, testing tools, or business systems instead of vendor names",
        ],
        "analyst_business": [
            "- prioritize business analysis, reporting, requirements, process improvement, KPI tracking, and stakeholder communication terms",
            "- prefer workflow, planning, and insight-delivery capabilities over software-engineering abstractions",
            "- preserve Excel, BI tools, Jira, Confluence, ERP, WMS, CRM, SAP, Oracle, Workday, PeopleSoft, Banner, Manhattan, and Blue Yonder terms prominently when the JD mentions them",
            "- if the JD does not explicitly mention a named enterprise platform, do not invent one; use generic business-analysis capabilities instead",
            "- keep budget tracking, risk management, traceability, UAT, and stakeholder work inside analyst-oriented categories rather than engineering categories",
            "- if the category is Tools & Platforms and the JD does not mention named tools, use generic items like documentation systems, workflow tools, product support systems, testing tools, or business systems instead of vendor names",
        ],
        "analyst_marketing": [
            "- prioritize campaign analysis, attribution, funnel metrics, experimentation, segmentation, dashboards, and reporting terms",
            "- prefer growth, lifecycle, and measurement capabilities over engineering infrastructure categories",
            "- preserve Excel, BI tools, CRM tools, Salesforce, and attribution or lifecycle measurement terms prominently when the JD mentions them",
            "- if the JD does not explicitly mention a named marketing platform, do not invent one; use generic marketing-analytics capabilities instead",
            "- keep campaign metrics, segmentation, reporting, and stakeholder insights inside analyst-oriented categories rather than engineering categories",
            "- if the category is Tools & Platforms and the JD does not mention named tools, use generic items like analytics platforms, reporting tools, CRM systems, or lifecycle tools instead of vendor names",
        ],
        "gtm_engineering": [
            "- prioritize CRM workflows, GTM automation, routing, enrichment, outbound systems, pipeline reporting, and revops terms",
            "- prefer practical workflow and systems terminology over generic software-engineering abstractions",
            "- preserve GTM stack tools like Clay, Salesforce, HubSpot, Outreach, Apollo, Marketo, 6sense, Gong, Customer.io, ZoomInfo, Smartlead, Instantly, HeyReach, Nooks, and Warmly when the JD mentions them",
            "- if the JD does not explicitly mention a named GTM tool, do not invent one; use strong generic GTM workflow capabilities instead",
            "- keep reporting, pipeline visibility, lifecycle operations, stakeholder coordination, and experiment-oriented skills inside GTM-oriented categories rather than generic engineering ones",
        ],
        "solutions_customer": [
            "- prioritize integrations, troubleshooting, customer-facing platforms, reporting, and communication-friendly technical tools",
            "- keep the section practical and delivery-oriented rather than deeply platform-centric",
        ],
    }
    selected_rules = family_rules.get(prompt_family_key, family_rules["software_engineering"])
    return "\n".join(
        [
            "You are a resume reconstruction engine.",
            "Build only Updated Skills.",
            "Assume the candidate has 4+ years of experience.",
            "Use the analysis object as the source of truth.",
            "You will receive an exact ordered list of allowed skill categories.",
            "Fill only those categories and keep them in the same order.",
            "Use the role family, responsibilities, workflows, and unified skills_mentioned list from the analysis object.",
            "Let top_requirements influence ordering and emphasis, not invention.",
            "",
            "SKILLS:",
            "- use only the provided categories",
            "- do not invent new categories",
            "- each item must be one concrete tool, platform, language, framework, database, cloud service, enterprise system, or concise capability name",
            "- no explanations, no qualifier text, no mini-sentences",
            "- derive skills from demonstrated work and believable transferable evidence, not just JD wording",
            "- prefer exact product and technology names over abstract wording whenever the JD supports them",
            "- include tools explicitly named in the JD first",
            "- only keep a JD term when it would still look honest if a recruiter asked where it shows up in the experience",
            "- include closely related enterprise tools only when they fit the JD's domain, category, and role family",
            "- do not use vague filler like 'data-driven solutions', 'deployment strategies', or 'technical discussions'",
            "- do not add broad software concepts such as software design, system design, event-driven systems, debugging, or stakeholder communication unless the exact phrase appears in the JD or it is clearly needed as a standard skill label",
            "- do not repeat the same concept across categories",
            "- skip a category only if it is truly irrelevant; otherwise fill it with 2-5 strong items",
            "- each item must read like a real recruiter-searchable skill, not a broken fragment or half sentence",
            "- if an item looks truncated, awkward, abstract, or too descriptive, rewrite it into a clean recruiter-scan term or remove it",
            "- if a domain-specific term is not supported by the candidate story, leave it out instead of forcing coverage",
            "- for analyst families, prefer JD-grounded tools first; if the JD does not name tools, use generic capability labels instead of common vendor names",
            *selected_rules,
            "- expected style:",
            "  - Programming Languages: TypeScript, JavaScript, Python",
            "  - Backend Engineering: Node.js, GraphQL, Spring Boot",
            "  - Data & Storage: MongoDB, BigQuery, PostgreSQL",
            "",
            "Return only the final result matching the schema.",
        ]
    )


def build_ai_resume_experience_prompt(prompt_family_key: str = "software_engineering") -> str:
    blueprint_lines = []
    for blueprint in current_experience_blueprints():
        bullet_rule = f"{blueprint['bullet_min']}" if blueprint["bullet_min"] == blueprint["bullet_max"] else f"{blueprint['bullet_min']}-{blueprint['bullet_max']}"
        blueprint_lines.append(
            f"- {blueprint['company']} | {blueprint['location']} | {blueprint['dates']} | bullets: {bullet_rule} | anchor: {blueprint['anchor']}"
        )

    family_rules = {
        "software_engineering": [
            "- recent roles should highlight implementation, APIs, systems, delivery, and engineering impact",
        ],
        "data_engineering": [
            "- recent roles should highlight pipelines, warehousing, orchestration, data quality, reporting data flows, and grounded operational improvement",
            "- describe systems and workflows in data terms rather than generic product-engineering language",
        ],
        "data_science": [
            "- recent roles should highlight model development, experimentation, feature work, evaluation, deployment support, and grounded business or product impact",
            "- describe systems and outcomes in ML or data-science terms rather than pipeline-engineering terms unless pipelines are central to the JD",
            "- do not introduce ML libraries or model platforms unless they appear in the JD or selected skills",
        ],
        "agentic_ai_engineering": [
            "- recent roles should highlight agent orchestration, LLM API integration, tool execution, governance controls, retrieval or memory, evals, tracing, and production reliability",
            "- use agentic AI infrastructure framing rather than generic backend or distributed-systems framing",
            "- do not introduce MCP, agent frameworks, vector databases, or governance tools unless they appear in the JD or selected skills",
        ],
        "platform_systems": [
            "- recent roles should highlight scale, observability, reliability, infrastructure, and performance tradeoffs",
        ],
        "security_engineering": [
            "- recent roles should highlight security controls, identity and access, vulnerability remediation, cloud security, compliance evidence, detection, and incident response",
            "- use security-engineering framing rather than backend feature-delivery framing",
            "- mention compliance frameworks only when they are present in the JD or selected skills",
            "- do not introduce backend frameworks unless they already appear in the JD or selected skills",
        ],
        "analyst_data": [
            "- recent roles should highlight SQL analysis, dashboards, reporting, experimentation, insight delivery, and decision support",
            "- describe workflows and outcomes in analyst terms rather than engineering implementation language",
            "- prioritize metrics, reporting accuracy, adoption, time saved, reconciliation, data validation, and stakeholder-facing outcomes when they fit the candidate-shaped story",
            "- if the JD does not mention named analyst tools, keep bullets tool-light and workflow-heavy instead of inventing platforms",
        ],
        "analyst_business": [
            "- recent roles should highlight requirements, process analysis, KPI reporting, stakeholder communication, and turning findings into action",
            "- use analyst-style business workflow language rather than engineering-system language where appropriate",
            "- prioritize process improvement, requirements clarity, UAT, reporting accuracy, reconciliation, turnaround time, and stakeholder alignment outcomes",
            "- if the JD does not mention named enterprise platforms, keep bullets tool-light and process-heavy instead of inventing systems",
        ],
        "analyst_marketing": [
            "- recent roles should highlight campaign measurement, attribution, funnel analysis, segmentation, reporting, and growth insights",
            "- use marketing and analytics workflow language rather than engineering-system language where appropriate",
            "- prioritize conversion metrics, campaign performance, cohort insights, attribution, reporting adoption, and experiment outcomes",
            "- if the JD does not mention named marketing tools, keep bullets tool-light and measurement-heavy instead of inventing platforms",
        ],
        "gtm_engineering": [
            "- recent roles should highlight CRM and revops workflows, GTM automation, routing, enrichment, outbound systems, reporting, and cross-functional execution",
            "- use GTM systems and operations language rather than generic product-engineering or generic analyst language where appropriate",
            "- prioritize pipeline visibility, lifecycle automation, routing accuracy, enrichment quality, campaign or outbound efficiency, and stakeholder adoption outcomes",
            "- if the JD does not mention named GTM tools, keep bullets tool-light and workflow-heavy instead of inventing platforms",
            "- only use named GTM platforms that already appear in the JD or selected skills; otherwise use generic phrases like CRM workflow, enrichment workflow, sequencing platform, or middleware",
        ],
        "solutions_customer": [
            "- recent roles should highlight integrations, troubleshooting, customer support, demos, adoption, and technical communication",
        ],
    }
    return "\n".join(
        [
            "You are a resume reconstruction engine.",
            "Build only the Professional Experience section for a tailored target-fit resume.",
            "Assume the candidate has 4+ years of experience.",
            "Use the JD analysis and the existing core resume sections as the source of truth.",
            "Do not mirror the JD. Do not invent unrealistic tools or fake expertise.",
            "Map JD-relevant capabilities through believable transferable systems.",
            "",
            "EXPERIENCE RULES:",
            "- Follow the fixed company, location, and date structure exactly",
            "- The title field must contain only the role title",
            "- Never put company name, location, dates, or separators into the title field",
            "- Invalid title example: 'McKinsey & Company | CA, USA | May 2025 – Present'",
            "- Valid title example: 'Integration Engineer'",
            "- Preserve natural title phrasing",
            "- Do not rewrite historical titles to imitate the target role family",
            "- Keep experience titles coherent with the overall career lane, but allow JD-aligned retitling when the bullets credibly support it",
            "- Bullet count per company must match exactly",
            f"- Each bullet must be {EXPERIENCE_BULLET_WORD_MIN}-{EXPERIENCE_BULLET_WORD_MAX} words",
            "- Recent and relevant roles should do more of the selling",
            "- Focus on the top_requirements first; do not try to force all JD requirements into the section",
            "- Use domain_terms only when the bullet can support them honestly through a system, workflow, action, or measurable result",
            *family_rules.get(prompt_family_key, family_rules["software_engineering"]),
            "",
            "BULLET FORMULA:",
            "[Strong Verb] + [System built/optimized] + using [1-3 tools] + under [constraint or engineering decision] + resulting in [grounded measurable impact or a concrete qualitative outcome].",
            "",
            "Each bullet must include:",
            "- real system context",
            "- 1-3 tools or relevant technical skills",
            "- a constraint or engineering decision",
            "- a measurable metric only when the exact number is grounded in candidate/profile evidence or the immutable experience blueprint",
            "- otherwise a concrete qualitative outcome that explains what improved or changed",
            "- never invent, estimate, infer, or borrow a number from the JD",
            "- active language showing what changed because of the work",
            "- one main accomplishment per bullet",
            "- natural sentence flow instead of visibly templated clause stacking",
            "- every important JD term used in a bullet must be backed by the bullet itself, not just implied by the role",
            "",
            "ORIGINALITY AND GROUNDING RULES:",
            "- Preserve originality",
            "- Prefer simpler believable technical wording over named-tool substitution",
            "- Do not introduce named infrastructure products unless they materially improve clarity and feel realistically grounded",
            "- Do not introduce named platforms, products, or vendors that are missing from the JD or selected skills just because they are common for the role family",
            "- If a bullet sounds like benchmark distributed-systems copy, simplify it into more natural resume language",
            "- Tailor by emphasis and detail selection, not by rewriting history",
            "- Prefer proving a smaller number of important requirements over weakly name-checking many requirements",
            "- If the target role is FAE, solutions engineering, sales engineering, or technical pre-sales, preserve believable engineering titles and shift the bullets toward demos, integrations, troubleshooting, customer communication, and adoption support only where that remains grounded",
            "- Keep each company aligned to its own realistic role family and time period instead of forcing perfect JD symmetry across all roles",
            "- Use metrics only when the exact value is present in supplied evidence; never create a softer or rounded number",
            "- Avoid revenue, dollar-value, exact-user-count, or very sharp throughput claims unless they are especially well-supported by the candidate's role context",
            "",
            "PROJECT STORY RULE:",
            "- Each company must read as one coherent project story",
            "- Early bullets establish role scope and the strongest top-requirement overlap",
            "- The first two bullets of relevant recent roles should carry the strongest evidence for the most important JD requirements",
            "- Middle bullets show implementation and decisions",
            "- Later bullets show validation, reliability, scale, or impact",
            "",
            "Fixed experience blueprints:",
            *blueprint_lines,
            "",
            "Return only the final result matching the schema.",
        ]
    )


def build_ai_resume_experience_subset_prompt(blueprints: list[dict], prompt_family_key: str = "software_engineering") -> str:
    blueprint_lines = []
    for blueprint in blueprints:
        bullet_rule = f"{blueprint['bullet_min']}" if blueprint["bullet_min"] == blueprint["bullet_max"] else f"{blueprint['bullet_min']}-{blueprint['bullet_max']}"
        blueprint_lines.append(
            f"- {blueprint['key']} | {blueprint['company']} | {blueprint['location']} | {blueprint['dates']} | bullets: {bullet_rule} | anchor: {blueprint['anchor']}"
        )

    family_rules = {
        "software_engineering": [
            "- preliminary skills should guide the stack used in bullets; do not invent a different stack from the skills section",
        ],
        "data_engineering": [
            "- preliminary skills should guide the stack used in bullets; prioritize SQL, pipelines, warehousing, orchestration, and data-quality workflows",
            "- describe systems and impacts in data workflow terms",
        ],
        "data_science": [
            "- preliminary skills should guide the stack used in bullets; prioritize model development, experimentation, feature work, evaluation, ML platforms, and grounded decision or product impact",
            "- use ML or data-science framing rather than pipeline-engineering framing unless pipelines are central to the JD",
            "- do not introduce ML libraries or model platforms unless they appear in the JD or preliminary skills",
        ],
        "agentic_ai_engineering": [
            "- preliminary skills should guide the stack used in bullets; prioritize agent orchestration, LLM APIs, MCP or tool protocols, governance controls, retrieval or memory, evals, tracing, and production reliability",
            "- use agentic AI infrastructure framing rather than generic backend or distributed-systems framing",
            "- do not introduce MCP, agent frameworks, vector databases, or governance tools unless they appear in the JD or preliminary skills",
        ],
        "platform_systems": [
            "- preliminary skills should guide the stack used in bullets; prioritize infrastructure, reliability, observability, scale, and system tradeoffs",
        ],
        "security_engineering": [
            "- preliminary skills should guide the stack used in bullets; prioritize security controls, IAM, vulnerability management, cloud security, SIEM or detection, compliance, and incident response",
            "- use security-engineering framing rather than backend feature-delivery framing",
            "- do not introduce backend frameworks unless they already appear in the JD or preliminary skills",
            "- do not introduce compliance frameworks unless they already appear in the JD or preliminary skills",
        ],
        "analyst_data": [
            "- preliminary skills should guide the stack used in bullets; prioritize reporting, SQL analysis, dashboards, experimentation, and insight delivery",
            "- use workflow, stakeholder, and business-impact framing rather than engineering implementation framing when appropriate",
            "- prefer analyst proof points such as reporting adoption, accuracy, time saved, reconciliation, KPI visibility, and decision support impact",
            "- do not introduce named BI or analyst tools in bullets unless the JD or preliminary skills already include them",
        ],
        "analyst_business": [
            "- preliminary skills should guide the stack used in bullets; prioritize requirements, process analysis, reporting, KPI tracking, and stakeholder communication",
            "- use business workflow framing rather than engineering implementation framing when appropriate",
            "- prefer analyst proof points such as UAT, requirements clarity, process-cycle reduction, reporting accuracy, exception handling, and stakeholder alignment",
            "- do not introduce named ERP, WMS, CRM, or enterprise tools in bullets unless the JD or preliminary skills already include them",
        ],
        "analyst_marketing": [
            "- preliminary skills should guide the stack used in bullets; prioritize campaign reporting, attribution, funnel analysis, experimentation, and growth insights",
            "- use marketing workflow framing rather than engineering implementation framing when appropriate",
            "- prefer analyst proof points such as campaign lift, funnel conversion, cohort trends, reporting adoption, and experiment outcomes",
            "- do not introduce named CRM, BI, or marketing platforms in bullets unless the JD or preliminary skills already include them",
        ],
        "gtm_engineering": [
            "- preliminary skills should guide the stack used in bullets; prioritize CRM workflows, GTM automation, routing, enrichment, outbound systems, reporting, and revops coordination",
            "- use GTM workflow framing rather than generic product-engineering language when appropriate",
            "- prefer GTM proof points such as routing accuracy, enrichment coverage, pipeline visibility, campaign or outbound efficiency, adoption, and stakeholder alignment outcomes",
            "- do not introduce named GTM, CRM, sequencing, or enrichment platforms in bullets unless the JD or preliminary skills already include them",
            "- if a named GTM tool is not already present in the JD or preliminary skills, rewrite it as a generic workflow or platform reference instead of adding the tool name",
        ],
        "solutions_customer": [
            "- preliminary skills should guide the stack used in bullets; prioritize integrations, troubleshooting, customer enablement, and adoption support",
        ],
    }
    return "\n".join(
        [
            "You are a resume reconstruction engine.",
            "Build only the Professional Experience entries requested.",
            "Assume the candidate has 4+ years of experience.",
            "Use the analysis object, preliminary skills, and immutable experience blueprints as the source of truth.",
            "Do not mirror the JD or invent unrealistic expertise.",
            "Tailor by emphasis, not by rewriting history.",
            "",
            "RULES:",
            "- follow the fixed company, location, and date structure exactly",
            "- keep historical titles believable",
            "- the title field must contain only the role title",
            "- never put company name, location, dates, or separators into the title field",
            "- invalid title example: 'McKinsey & Company | CA, USA | May 2025 – Present'",
            "- valid title example: 'Integration Engineer'",
            "- do not rewrite titles to imitate the target role",
            "- keep experience titles coherent with the overall career lane, but allow JD-aligned retitling when the bullets credibly support it",
            "- recent roles should sell harder than older roles",
            f"- each bullet must be {EXPERIENCE_BULLET_WORD_MIN}-{EXPERIENCE_BULLET_WORD_MAX} words",
            "- prioritize the top_requirements first instead of trying to mention the whole JD",
            "",
            "BULLET DESIGN:",
            "- the first bullet under each company is a simple summary bullet in plain language",
            "- the first bullet must be 25-40 words; the ideal range is 25-30 words",
            "- the first bullet should describe the role and scope clearly without becoming dense",
            "- do not make the first bullet shorter than 25 words",
            "- do not treat the first bullet like a compact fragment; write it as a full accomplishment sentence",
            "- for recent relevant roles, the first two bullets should carry the strongest evidence for the most important JD requirements",
            "- all later bullets should follow:",
            "  - What: the skill, keyword, or qualification",
            "  - How: how it was used",
            "  - Why: why it mattered or what changed",
            "",
            "BULLET FORMULA:",
            "[Strong Verb] + [System or workflow] + using [1-3 tools] + under [constraint or engineering decision] + resulting in [grounded measurable impact or a concrete qualitative outcome].",
            "",
            "Each bullet must include:",
            "- real system or workflow context",
            "- 1-3 tools or technical skills from the preliminary skills or supporting stack",
            "- a constraint or engineering decision",
            "- a measurable metric only when the exact number is grounded in candidate/profile evidence or the immutable experience blueprint",
            "- otherwise a concrete qualitative outcome that explains what improved or changed",
            "- never invent, estimate, infer, or borrow a number from the JD",
            "- one main accomplishment per bullet",
            "- if a JD term appears, the bullet itself must prove it with an action, workflow, system, or measurable result",
            *family_rules.get(prompt_family_key, family_rules["software_engineering"]),
            "- older roles should use the lighter, earlier-career portion of the preliminary skills instead of inheriting the most modern or specialized parts of the stack",
            "- keep KPMG and Trigent technology choices believable for 2020-2022, their company anchors, and normal exposure progression",
            "- do not backfill newer tools, AI frameworks, or unusually convenient target-stack substitutions into older roles unless the anchor strongly supports them",
            "- if a bullet wants to mention a named platform that is not already in the JD or preliminary skills, replace it with a generic workflow phrase instead",
            "- prefer simpler wording over dense clause chains when both communicate the same accomplishment",
            "- avoid bullets that read like a rigid template; vary rhythm and sentence structure naturally",
            "- prefer proving fewer important requirements strongly over loosely name-checking many requirements",
            "",
            "Keep each company as one coherent project story.",
            "Use metrics only when the exact value is present in supplied evidence; otherwise use a concrete qualitative outcome.",
            "Keep company sections realistic to their role family and time period.",
            "",
            "Fixed experience blueprints:",
            *blueprint_lines,
            "",
            "Return only the final result matching the schema.",
        ]
    )


def build_ai_reachout_prompt() -> str:
    return "\n".join(
        [
            "You write concise LinkedIn reachout notes for engineering candidates.",
            "Write one short message under 300 characters total.",
            "Use a compact, warm, high-signal style.",
            "Do not write one dense paragraph.",
            "Use exactly 4 short lines separated by single line breaks.",
            "Line 1: greeting with name, then 'keeping this short'.",
            "Line 2: one short introduction line about the candidate.",
            "Line 3: one short fit line tied to role-relevant skills or product fit.",
            "Line 4: direct ask for an interview and brief thanks.",
            "Keep each line short and punchy.",
            "Use only facts grounded in the provided resume and JD.",
            "Do not invent companies, internships, metrics, or domain expertise.",
            "Do not use bullets, emojis, hashtags, or quotes.",
            "Do not mention character limits in the message.",
            "Return only the final result matching the schema.",
        ]
    )


def build_ai_followup_prompt() -> str:
    return "\n".join(
        [
            "You answer application follow-up questions as the candidate in first person.",
            "Base every answer on the job description, the resume text, and the question.",
            "Do not invent experience that is not supported by the resume.",
            "If something is new or only partially supported, say that honestly and explain how the candidate approached learning or solving it.",
            "Keep the answer concise.",
            "Target roughly 60 to 110 words.",
            "If the question is very simple, a shorter answer is better.",
            "Do not go beyond 130 words.",
            "",
            "COMMUNICATION STYLE:",
            "- use simple, everyday English",
            "- keep sentences short and easy to say out loud",
            "- avoid difficult words, corporate jargon, buzzwords, and textbook language",
            "- sound natural, human, and easy to talk to",
            "",
            "TONE:",
            "- calm",
            "- friendly",
            "- confident without sounding overconfident",
            "- thoughtful and genuine",
            "",
            "HOW TO ANSWER:",
            "- acknowledge the question naturally",
            "- answer the main point first",
            "- explain the reasoning using a real experience or simple example when helpful",
            "- finish naturally and stop when the answer is complete",
            "- do not add extra points after the answer is already complete",
            "",
            "STORYTELLING:",
            "- explain experience like talking to a coworker",
            "- do not force STAR or any formal interview framework",
            "- focus on what happened, how it was approached, and what came out of it",
            "",
            "CONVERSATION RULES:",
            "- it should feel like a discussion, not a presentation",
            "- do not sound rehearsed or overly polished",
            "- natural phrases like 'I think', 'Honestly', 'Usually', 'From my experience', 'At that point', 'That's what we did', 'That's how it worked', 'So after that', and 'One thing I noticed' are fine when they fit naturally",
            "",
            "MINDSET:",
            "- do not pretend to know everything",
            "- focus on solving problems instead of showing off knowledge",
            "- explain the reasoning behind decisions before talking about tools or technologies",
            "- prefer real situations over abstract claims",
            "",
            "AVOID:",
            "- corporate buzzwords",
            "- interview clichés",
            "- long complicated sentences",
            "- over-explaining",
            "- generic motivational statements",
            "- repeating the question in the answer",
            "- talking longer than needed",
            "",
            "Return only the final answer text.",
        ]
    )


def build_ai_core_review_prompt() -> str:
    return "\n".join(
        [
            "You review only the resume summary and skills section for a tailored target-fit resume.",
            "Use the analysis object as the source of truth.",
            "Judge whether the current summary and skills are ready to keep or should be revised.",
            "Use top_requirements as the primary scoring lens, not the whole JD.",
            "Use domain_terms carefully; flag them when the wording sounds like unsupported domain ownership instead of credible adjacent evidence.",
            "Focus on three risks:",
            "- summary that sounds copied from company or JD wording, too generic, or mis-emphasized for the role",
            "- skills that include broad capabilities instead of named tools, miss obvious JD tools, or are awkwardly categorized",
            "- wording that sounds stiff, overpacked, truncated, or visibly AI-generated instead of natural resume writing",
            "Also flag summaries or skills that weakly name-check too many requirements instead of proving the most important ones.",
            "Flag summaries that stack too many tools, systems, or clauses into one sentence.",
            "Flag summaries that mention important JD terms without making them feel provable from the candidate story.",
            "Flag skills that read like broken fragments, process phrases, or abstract concepts instead of named recruiter-searchable tools.",
            "Flag skills that look like they were pulled from the JD but do not seem grounded in the candidate's likely experience.",
            "Do not flag a skills section just because it could include more adjacent tools; refinement must not broaden the stack.",
            "Do not review professional experience.",
            "Be concise and practical.",
            "Return only the final result matching the schema.",
        ]
    )


def build_ai_core_correction_prompt() -> str:
    return "\n".join(
        [
            "You refine the final resume title system, summary, and skills for a tailored target-fit resume.",
            "Use the analysis object and current draft as the source of truth.",
            "Inspect the current top title, summary, skills, and experience titles. Improve them only if needed, and otherwise keep them close to the draft.",
            "Follow the role family and the JD facts from the analysis object.",
            "Use top_requirements as the primary priorities, and use secondary_requirements only as support.",
            "Use the skills_mentioned list, responsibilities, and workflows to keep the strongest role match visible.",
            "Use only the provided skill categories and keep them in the provided order.",
            "Focus on sharper role emphasis, cleaner summary phrasing, more concrete believable skills, and coherent market-standard titles.",
            "Do not let the refinement smooth a data, platform, AI application, or solutions role back into generic software-engineering language.",
            "Do not replace strong concrete stack or workflow terms with broader wording just because it sounds cleaner.",
            "If the summary mentions years of experience at all, it must say 4+ years and never anything higher.",
            "Do not try to cover the whole JD. Prove the top requirements clearly instead.",
            "Every important JD term kept in the summary or skills must feel provable from the candidate story.",
            "Use domain_terms only when the wording is honestly supported; otherwise prefer adjacent workflow language.",
            "Remove weak JD mirroring, unsupported domain claims, and broad filler before adding anything new.",
            "Do not copy JD wording directly.",
            "Make the writing sound human and recruiter-natural, not optimized or assembled.",
            "Break up dense phrasing, remove stacked jargon, and rewrite truncated skill items into clean terms.",
            "Review experience titles together as one career story.",
            "Experience titles may differ, but they must stay in the same semantic lane for the detected role family.",
            "Avoid abrupt lane switching across companies unless the bullet context clearly forces it.",
            "Top resume title and experience titles should support the same overall career narrative.",
            "Do not rewrite experience bullets, company names, locations, or dates.",
            "Return only the final result matching the schema.",
        ]
    )


def resume_word_count_prompt_rules(*, include_experience_bullets: bool = False) -> list[str]:
    rules = [
        "WORD COUNT RULES (MANDATORY):",
        f"- top resume title must be {TITLE_WORD_MIN}-{TITLE_WORD_MAX} words",
        f"- summary must be {SUMMARY_WORD_MIN}-{SUMMARY_WORD_MAX} words",
        f"- every experience title must be {TITLE_WORD_MIN}-{TITLE_WORD_MAX} words",
    ]
    if include_experience_bullets:
        rules.extend([
            f"- every experience bullet must be {EXPERIENCE_BULLET_WORD_MIN}-{EXPERIENCE_BULLET_WORD_MAX} words",
            "- preserve the required bullet count for every active experience role",
        ])
    rules.extend([
        "- count the final returned wording after all edits",
        "- do not return a synthesis or proposal that falls outside any required range",
        "",
    ])
    return rules


def build_ai_final_synthesis_prompt() -> str:
    return "\n".join(
        [
            "You perform the final synthesis for a tailored resume after all experience bullets have been generated.",
            "Use the raw job description, JD analysis, preliminary skills, complete generated experience, and immutable active experience blueprints as evidence.",
            "Return a top resume title, summary, final skills, and one coherent work title for every active stable role key.",
            "",
            *resume_word_count_prompt_rules(),
            "SUMMARY:",
            "- write in a simple, natural human tone",
            "- ground every claim in the generated experience bullets or independently supported profile evidence in the active blueprints",
            "- transferable capabilities may be discussed when the experience demonstrates them",
            "- treat a vertical or domain named by the JD as target context, not proof that the candidate previously worked in it",
            "- never claim prior experience, expertise, ownership, or results in a JD vertical or domain merely because the JD mentions it",
            "- never say the candidate is applying experience or capabilities to that vertical unless the generated experience or active blueprints independently support that connection",
            "- avoid copied JD language, generic filler, stacked jargon, and unsupported years-of-experience claims",
            "",
            "TOP TITLE AND WORK TITLES:",
            "- use standard market titles containing only role-title text",
            "- make all work titles read as one coherent career family and believable hierarchy across the fixed dates",
            "- align emphasis toward the target role without rewriting history into unrelated role families",
            "- preserve believable seniority progression and the technical or functional lane proven by each role's bullets",
            "- do not include companies, locations, dates, separators, or explanatory text in a title",
            "",
            "FINAL SKILLS:",
            "- use only the supplied categories and return them in the exact supplied category order",
            "- ground skills in the generated experience and preliminary skills; JD wording alone is not evidence",
            "- keep concrete recruiter-searchable tools and capabilities, with at least two items per included category",
            "- do not introduce unsupported named tools, platforms, or domain expertise",
            "",
            "EXPERIENCE TITLES:",
            "- return exactly one title for every active stable role key supplied in the schema",
            "- do not return titles for inactive or unknown role keys",
            "- do not rewrite bullets, companies, locations, or dates",
            "",
            "Return only the final result matching the schema.",
        ]
    )


def ai_analysis_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "company_name": {"type": "string"},
            "company_description": {"type": "string"},
            "company_domain": {"type": "string"},
            "culture_signals": {"type": "array", "items": {"type": "string"}},
            "target_role": {"type": "string"},
            "role_family": {"type": "string"},
            "generation_route_key": {"type": "string", "enum": sorted(GENERATION_ROUTE_CONFIG.keys())},
            "core_problem": {"type": "string"},
            "hire_problem": {"type": "string"},
            "desired_outcomes": {"type": "array", "items": {"type": "string"}},
            "top_requirements": {"type": "array", "items": {"type": "string"}},
            "secondary_requirements": {"type": "array", "items": {"type": "string"}},
            "evidence_terms": {"type": "array", "items": {"type": "string"}},
            "domain_terms": {"type": "array", "items": {"type": "string"}},
            "system_description": {"type": "string"},
            "responsibilities": {"type": "array", "items": {"type": "string"}},
            "workflows": {"type": "array", "items": {"type": "string"}},
            "skills_mentioned": {"type": "array", "items": {"type": "string"}},
            "behavioral_signals": {"type": "array", "items": {"type": "string"}},
            "gaps": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "company_name",
            "company_description",
            "company_domain",
            "culture_signals",
            "target_role",
            "role_family",
            "generation_route_key",
            "core_problem",
            "hire_problem",
            "desired_outcomes",
            "top_requirements",
            "secondary_requirements",
            "evidence_terms",
            "domain_terms",
            "system_description",
            "responsibilities",
            "workflows",
            "skills_mentioned",
            "behavioral_signals",
            "gaps",
        ],
    }


def ai_resume_schema(blueprints: list[dict] | None = None) -> dict:
    allowed_skill_categories = sorted(ALLOWED_SKILL_CATEGORIES)
    skill_item_schema = {
        "type": "string",
        "minLength": 2,
        "maxLength": 48,
        "pattern": r"^[A-Za-z0-9+#.&' -]+$",
    }
    blueprints = current_experience_blueprints() if blueprints is None else blueprints
    experience_properties = {}
    required_experience_keys = []
    for blueprint in blueprints:
        experience_properties[blueprint["key"]] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": blueprint["bullet_min"],
                    "maxItems": blueprint["bullet_max"],
                },
            },
            "required": ["title", "bullets"],
        }
        required_experience_keys.append(blueprint["key"])

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "updated_title": {"type": "string"},
            "updated_summary": {"type": "string"},
            "updated_skills": {
                "type": "array",
                "minItems": 6,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "category": {"type": "string", "enum": allowed_skill_categories},
                        "items": {
                            "type": "array",
                            "items": skill_item_schema,
                            "minItems": 2,
                        },
                    },
                    "required": ["category", "items"],
                },
            },
            "experience": {
                "type": "object",
                "additionalProperties": False,
                "properties": experience_properties,
                "required": required_experience_keys,
            },
        },
        "required": ["updated_title", "updated_summary", "updated_skills", "experience"],
    }


def ai_resume_core_schema() -> dict:
    allowed_skill_categories = sorted(ALLOWED_SKILL_CATEGORIES)
    skill_item_schema = {
        "type": "string",
        "minLength": 2,
        "maxLength": 48,
        "pattern": r"^[A-Za-z0-9+#.&' -]+$",
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "updated_title": {"type": "string"},
            "updated_summary": {"type": "string"},
            "updated_skills": {
                "type": "array",
                "minItems": 6,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "category": {"type": "string", "enum": allowed_skill_categories},
                        "items": {
                            "type": "array",
                            "items": skill_item_schema,
                            "minItems": 2,
                        },
                    },
                    "required": ["category", "items"],
                },
            },
        },
        "required": ["updated_title", "updated_summary", "updated_skills"],
    }


def ai_title_summary_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "updated_title": {"type": "string"},
            "updated_summary": {"type": "string"},
        },
        "required": ["updated_title", "updated_summary"],
    }


def ai_skills_schema(allowed_skill_categories: list[str] | None = None) -> dict:
    allowed_skill_categories = allowed_skill_categories or sorted(ALLOWED_SKILL_CATEGORIES)
    skill_item_schema = {
        "type": "string",
        "minLength": 2,
        "maxLength": 48,
        "pattern": r"^[A-Za-z0-9+#.&' -]+$",
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "updated_skills": {
                "type": "array",
                "minItems": min(6, len(allowed_skill_categories)),
                "maxItems": len(allowed_skill_categories),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "category": {"type": "string", "enum": allowed_skill_categories},
                        "items": {"type": "array", "items": skill_item_schema, "minItems": 2, "maxItems": 5},
                    },
                    "required": ["category", "items"],
                },
            },
        },
        "required": ["updated_skills"],
    }


def ai_experience_schema(blueprints: list[dict] | None = None) -> dict:
    blueprints = blueprints or current_experience_blueprints()
    experience_properties = {}
    required_experience_keys = []
    for blueprint in blueprints:
        experience_properties[blueprint["key"]] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": blueprint["bullet_min"],
                    "maxItems": blueprint["bullet_max"],
                },
            },
            "required": ["title", "bullets"],
        }
        required_experience_keys.append(blueprint["key"])

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "experience": {
                "type": "object",
                "additionalProperties": False,
                "properties": experience_properties,
                "required": required_experience_keys,
            },
        },
        "required": ["experience"],
    }


def ai_experience_subset_schema(blueprints: list[dict]) -> dict:
    experience_properties = {}
    required_experience_keys = []
    for blueprint in blueprints:
        experience_properties[blueprint["key"]] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": blueprint["bullet_min"],
                    "maxItems": blueprint["bullet_max"],
                },
            },
            "required": ["title", "bullets"],
        }
        required_experience_keys.append(blueprint["key"])

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "experience": {
                "type": "object",
                "additionalProperties": False,
                "properties": experience_properties,
                "required": required_experience_keys,
            },
        },
        "required": ["experience"],
    }


def ai_reachout_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "message": {"type": "string"},
            "char_count": {"type": "integer"},
        },
        "required": ["message", "char_count"],
    }


def ai_core_review_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary_status": {"type": "string", "enum": ["keep", "revise"]},
            "skills_status": {"type": "string", "enum": ["keep", "revise"]},
            "summary_notes": {"type": "string"},
            "skills_notes": {"type": "string"},
        },
        "required": ["summary_status", "skills_status", "summary_notes", "skills_notes"],
    }


def ai_core_correction_schema(allowed_skill_categories: list[str] | None = None, blueprints: list[dict] | None = None) -> dict:
    allowed_skill_categories = allowed_skill_categories or sorted(ALLOWED_SKILL_CATEGORIES)
    blueprints = blueprints or []
    skill_item_schema = {
        "type": "string",
        "minLength": 2,
        "maxLength": 48,
        "pattern": r"^[A-Za-z0-9+#.&' -]+$",
    }
    title_properties = {
        blueprint["key"]: {"type": "string"}
        for blueprint in blueprints
    }
    required_title_keys = [blueprint["key"] for blueprint in blueprints]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "updated_title": {"type": "string"},
            "updated_summary": {"type": "string"},
            "updated_skills": {
                "type": "array",
                "minItems": min(6, len(allowed_skill_categories)),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "category": {"type": "string", "enum": allowed_skill_categories},
                        "items": {"type": "array", "items": skill_item_schema, "minItems": 2},
                    },
                    "required": ["category", "items"],
                },
            },
            "experience_titles": {
                "type": "object",
                "additionalProperties": False,
                "properties": title_properties,
                "required": required_title_keys,
            },
        },
        "required": ["updated_title", "updated_summary", "updated_skills", "experience_titles"],
    }


def ai_final_synthesis_schema(allowed_skill_categories: list[str], active_blueprints: list[dict]) -> dict:
    return ai_core_correction_schema(allowed_skill_categories, active_blueprints)


DEFAULT_ROLE_TITLES_BY_PROMPT_FAMILY = {
    "software_engineering": {
        "mckinsey": "Software Engineer",
        "uber": "Software Engineer",
        "kpmg": "Software Engineer",
        "trigent": "Frontend Developer",
    },
    "data_engineering": {
        "mckinsey": "Data Engineer",
        "uber": "Data Engineer",
        "kpmg": "Java Full Stack Developer",
        "trigent": "Frontend Developer",
    },
    "platform_systems": {
        "mckinsey": "Platform Engineer",
        "uber": "Platform Engineer",
        "kpmg": "Software Engineer",
        "trigent": "Frontend Developer",
    },
    "analyst_data": {
        "mckinsey": "Data Analyst",
        "uber": "Operations Analyst",
        "kpmg": "Reporting Analyst",
        "trigent": "Frontend Developer",
    },
    "analyst_business": {
        "mckinsey": "Business Analyst",
        "uber": "Operations Analyst",
        "kpmg": "Business Analyst",
        "trigent": "Frontend Developer",
    },
    "analyst_marketing": {
        "mckinsey": "Product Analyst",
        "uber": "Operations Analyst",
        "kpmg": "Business Analyst",
        "trigent": "Frontend Developer",
    },
    "gtm_engineering": {
        "mckinsey": "GTM Systems Analyst",
        "uber": "Business Systems Analyst",
        "kpmg": "Business Analyst",
        "trigent": "Frontend Developer",
    },
    "solutions_customer": {
        "mckinsey": "Technical Analyst",
        "uber": "Technical Analyst",
        "kpmg": "Business Analyst",
        "trigent": "Frontend Developer",
    },
}

INTEGRATION_ROLE_FAMILY_DEFAULT_TITLES = {
    "mckinsey": "Integration Engineer",
    "uber": "Software Engineer",
    "kpmg": "Software Engineer",
    "trigent": "Frontend Developer",
}

def default_role_title_for_prompt_family(blueprint_key: str, prompt_family_key: str) -> str:
    family_defaults = DEFAULT_ROLE_TITLES_BY_PROMPT_FAMILY.get(
        prompt_family_key,
        DEFAULT_ROLE_TITLES_BY_PROMPT_FAMILY["software_engineering"],
    )
    return family_defaults.get(
        blueprint_key,
        DEFAULT_ROLE_TITLES_BY_PROMPT_FAMILY["software_engineering"].get(blueprint_key, "Software Engineer"),
    )


def default_role_title_for_analysis(blueprint_key: str, analysis_payload: dict | None = None) -> str:
    prompt_family_key = prompt_family_key_for_analysis(analysis_payload)
    role_family = str((analysis_payload or {}).get("role_family", "")).strip().lower()
    target_role = str((analysis_payload or {}).get("target_role", "")).strip().lower()
    combined = f"{role_family} {target_role}"
    if "integration" in combined and prompt_family_key == "software_engineering":
        return INTEGRATION_ROLE_FAMILY_DEFAULT_TITLES.get(blueprint_key, "Software Engineer")
    return default_role_title_for_prompt_family(blueprint_key, prompt_family_key)


def invalid_experience_title_reason(raw_title: str, blueprint: dict) -> str | None:
    title = (raw_title or "").strip()
    if not title:
        return "missing title"

    cleaned = title.replace("\n", " ").strip()
    cleaned = re.sub(r"\s*\|\s*", " | ", cleaned)
    for fragment in (blueprint["company"], blueprint["location"], blueprint["dates"]):
        cleaned = cleaned.replace(fragment, "")
    cleaned = re.sub(r"(?:\s*\|\s*){2,}", " | ", cleaned)
    cleaned = re.sub(r"^\s*\|\s*", "", cleaned)
    cleaned = re.sub(r"\s*\|\s*$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" |")

    if not cleaned or cleaned in {blueprint["company"], blueprint["location"], blueprint["dates"]}:
        return "metadata echo"
    return None


def collect_invalid_experience_titles(experience_payload: dict, blueprints: list[dict]) -> list[dict]:
    failures: list[dict] = []
    experience = experience_payload.get("experience") or {}
    for blueprint in blueprints:
        entry = experience.get(blueprint["key"]) or {}
        raw_title = str(entry.get("title", "")).strip()
        reason = invalid_experience_title_reason(raw_title, blueprint)
        if reason:
            failures.append(
                {
                    "company": blueprint["company"],
                    "raw_title": raw_title,
                    "reason": reason,
                }
            )
    return failures


def resolve_experience_title(raw_title: str, blueprint: dict, analysis_payload: dict | None = None) -> tuple[str, str | None]:
    prompt_family_key = prompt_family_key_for_analysis(analysis_payload)
    fallback_title = str(blueprint.get("default_title", "")).strip() or default_role_title_for_analysis(blueprint["key"], analysis_payload)
    title = (raw_title or "").strip()
    invalid_reason = invalid_experience_title_reason(title, blueprint)
    if invalid_reason == "missing title":
        return fallback_title, f"{blueprint['company']}: model returned an empty title field, so fallback title '{fallback_title}' was applied."

    cleaned = title.replace("\n", " ").strip()
    cleaned = re.sub(r"\s*\|\s*", " | ", cleaned)

    # Remove repeated company/location/date fragments if the model echoes metadata.
    for fragment in (blueprint["company"], blueprint["location"], blueprint["dates"]):
        cleaned = cleaned.replace(fragment, "")

    cleaned = re.sub(r"(?:\s*\|\s*){2,}", " | ", cleaned)
    cleaned = re.sub(r"^\s*\|\s*", "", cleaned)
    cleaned = re.sub(r"\s*\|\s*$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" |")

    # If the title is still effectively empty or just looks like metadata, fall back.
    if invalid_reason == "metadata echo":
        return fallback_title, (
            f"{blueprint['company']}: model returned metadata instead of a role title -> '{title}'. "
            f"After removing company/location/date nothing valid remained, so fallback title '{fallback_title}' was applied."
        )

    # If the model stuffed a whole line with separators, keep only the first non-metadata segment.
    if "|" in cleaned:
        segments = [segment.strip() for segment in cleaned.split("|") if segment.strip()]
        segments = [segment for segment in segments if segment not in {blueprint["company"], blueprint["location"], blueprint["dates"]}]
        if segments:
            cleaned = segments[0]

    return cleaned or fallback_title, None


def format_generated_resume_text(resume_payload: dict, experience_blueprints: list[dict] | None = None) -> str:
    normalized_skills = normalize_updated_skills(resume_payload.get("updated_skills", []))
    lines = [
        "Updated Title",
        resume_payload["updated_title"].strip(),
        "",
        "Updated Summary",
        resume_payload["updated_summary"].strip(),
        "",
        "Updated Skills",
    ]

    for skill in normalized_skills:
        items = [item.strip() for item in skill.get("items", []) if item.strip()]
        if not items:
            continue
        lines.append(f"{skill['category'].strip()}: {', '.join(items)}.")

    lines.extend(["", "Professional Experience", ""])

    experience = resume_payload.get("experience", {})
    analysis_payload = resume_payload.get("_analysis") or {}
    enabled_keys = resume_payload.get("_enabled_experience_keys")
    blueprint_source = experience_blueprints if experience_blueprints is not None else current_experience_blueprints()
    for blueprint in filter_blueprints_by_enabled_keys(blueprint_source, enabled_keys):
        entry = experience.get(blueprint["key"], {})
        title, _ = resolve_experience_title(entry.get("title") or "", blueprint, analysis_payload)
        bullets = [bullet.strip() for bullet in entry.get("bullets", []) if bullet.strip()]

        lines.append(f"{blueprint['company']} | {blueprint['location']}")
        lines.append(f"{title} | {blueprint['dates']}")
        for bullet in bullets:
            lines.append(f"• {bullet}")
        lines.append("")

    return "\n".join(lines).strip()


def format_core_resume_text(core_payload: dict) -> str:
    normalized_skills = normalize_updated_skills(core_payload.get("updated_skills", []))
    lines = [
        "Updated Title",
        core_payload["updated_title"].strip(),
        "",
        "Updated Summary",
        core_payload["updated_summary"].strip(),
        "",
        "Updated Skills",
    ]

    for skill in normalized_skills:
        items = [item.strip() for item in skill.get("items", []) if item.strip()]
        if not items:
            continue
        lines.append(f"{skill['category'].strip()}: {', '.join(items)}.")

    lines.extend(["", "Professional Experience", ""])
    return "\n".join(lines).strip()


def format_title_summary_text(payload: dict) -> str:
    return "\n".join(
        [
            "Updated Title",
            str(payload.get("updated_title", "")).strip(),
            "",
            "Updated Summary",
            str(payload.get("updated_summary", "")).strip(),
        ]
    ).strip()


def format_skills_text(payload: dict) -> str:
    normalized_skills = normalize_updated_skills(payload.get("updated_skills", []))
    lines = ["Updated Skills"]
    for skill in normalized_skills:
        items = [item.strip() for item in skill.get("items", []) if item.strip()]
        if items:
            lines.append(f"{skill['category'].strip()}: {', '.join(items)}.")
    return "\n".join(lines).strip()


def merge_core_sections(title_summary_payload: dict, skills_payload: dict) -> dict:
    return {
        "updated_title": str(title_summary_payload.get("updated_title", "")).strip(),
        "updated_summary": str(title_summary_payload.get("updated_summary", "")).strip(),
        "updated_skills": normalize_updated_skills(skills_payload.get("updated_skills", [])),
    }


def merge_resume_payloads(core_payload: dict, experience_payload: dict) -> dict:
    return {
        "updated_title": core_payload.get("updated_title", ""),
        "updated_summary": core_payload.get("updated_summary", ""),
        "updated_skills": normalize_updated_skills(core_payload.get("updated_skills", [])),
        "experience": experience_payload.get("experience", {}),
        "_analysis": core_payload.get("_analysis", {}),
        "_enabled_experience_keys": experience_payload.get("_enabled_experience_keys")
        or core_payload.get("_enabled_experience_keys")
        or list(EXPERIENCE_BLUEPRINT_KEYS),
    }


def ai_session_active_blueprints(session: dict) -> list[dict]:
    ensure_ai_session_state(session)
    return filter_blueprints_by_enabled_keys(
        current_experience_blueprints(),
        session.get("enabled_experience_keys"),
    )


def ai_session_combined_experience(session: dict) -> dict:
    ensure_ai_session_state(session)
    experience: dict[str, dict] = {}
    experience.update((session.get("experience_recent") or {}).get("experience") or {})
    experience.update((session.get("experience_older") or {}).get("experience") or {})
    return {
        "experience": experience,
        "_enabled_experience_keys": normalize_enabled_experience_keys(
            session.get("enabled_experience_keys")
        ),
    }


def ai_session_canonical_resume(
    session: dict,
    active_blueprints: list[dict] | None = None,
) -> dict:
    ensure_ai_session_state(session)
    blueprints = active_blueprints if active_blueprints is not None else ai_session_active_blueprints(session)
    core = session.get("core_resume")
    if not core and session.get("title_summary") and session.get("skills"):
        core = merge_core_sections(session["title_summary"], session["skills"])
    experience = ai_session_combined_experience(session).get("experience") or {}
    return _canonical_editable_resume(
        {
            **(core or {}),
            "experience": experience,
        },
        blueprints,
    )


def format_ai_session_resume(
    session: dict,
    active_blueprints: list[dict] | None = None,
) -> str:
    ensure_ai_session_state(session)
    blueprints = active_blueprints if active_blueprints is not None else ai_session_active_blueprints(session)
    canonical = ai_session_canonical_resume(session, blueprints)
    payload = {
        **canonical,
        "_analysis": session.get("analysis") or {},
        "_enabled_experience_keys": [blueprint["key"] for blueprint in blueprints],
    }
    return format_generated_resume_text(payload, blueprints)


def _split_ai_session_experience(experience: dict) -> tuple[dict, dict]:
    recent_keys = set(EXPERIENCE_BLUEPRINT_KEYS[:2])
    recent = {
        "experience": {
            key: copy.deepcopy(value)
            for key, value in experience.items()
            if key in recent_keys
        }
    }
    older = {
        "experience": {
            key: copy.deepcopy(value)
            for key, value in experience.items()
            if key not in recent_keys
        }
    }
    return recent, older


def update_ai_session_structured_resume(
    session: dict,
    resume_payload: dict,
    active_blueprints: list[dict],
) -> None:
    canonical = _canonical_editable_resume(resume_payload, active_blueprints)
    session["title_summary"] = {
        "updated_title": canonical["updated_title"],
        "updated_summary": canonical["updated_summary"],
    }
    session["skills"] = {"updated_skills": copy.deepcopy(canonical["updated_skills"])}
    session["core_resume"] = merge_core_sections(session["title_summary"], session["skills"])
    session["core_resume"]["_analysis"] = session.get("analysis") or {}
    session["core_resume"]["_enabled_experience_keys"] = [blueprint["key"] for blueprint in active_blueprints]
    recent, older = _split_ai_session_experience(canonical["experience"])
    session["experience_recent"] = recent
    session["experience_older"] = older
    session["resume_content"] = format_ai_session_resume(session, active_blueprints)


def parse_ai_session_resume_content(
    content: str,
    session: dict,
    active_blueprints: list[dict],
) -> dict:
    normalized_content = str(content or "").strip()
    errors, _warnings = validate_updated_content(normalized_content)
    if errors:
        raise ValueError("Current resume content is invalid: " + " | ".join(errors))

    parsed = parse_updated_content_to_resume(normalized_content, load_base_resume())
    parsed_skills = []
    for item in parsed.get("technical_skills") or []:
        if not isinstance(item, dict):
            continue
        raw_items = item.get("items", [])
        items = (
            [str(value).strip() for value in raw_items if str(value).strip()]
            if isinstance(raw_items, list)
            else [value.strip() for value in str(raw_items).split(",") if value.strip()]
        )
        parsed_skills.append({
            "category": str(item.get("category", "")).strip(),
            "items": items,
        })

    parsed_experience = parsed.get("experience") if isinstance(parsed.get("experience"), list) else []
    experience = {}
    for index, blueprint in enumerate(active_blueprints):
        entry = parsed_experience[index] if index < len(parsed_experience) and isinstance(parsed_experience[index], dict) else {}
        experience[blueprint["key"]] = {
            "title": str(entry.get("title", "")).strip(),
            "bullets": [
                str(bullet).strip()
                for bullet in (entry.get("bullets") or [])
                if str(bullet).strip()
            ],
        }

    canonical = {
        "updated_title": str(parsed.get("title", "")).strip(),
        "updated_summary": str(parsed.get("summary", "")).strip(),
        "updated_skills": normalize_updated_skills(parsed_skills),
        "experience": experience,
    }
    structural_issues = []
    if not canonical["updated_title"]:
        structural_issues.append("Updated title is empty.")
    if not canonical["updated_summary"]:
        structural_issues.append("Updated summary is empty.")
    if not canonical["updated_skills"]:
        structural_issues.append("Updated skills are empty.")
    for blueprint in active_blueprints:
        entry = canonical["experience"][blueprint["key"]]
        if not entry["title"]:
            structural_issues.append(f"{blueprint['company']} is missing a role title.")
        if not entry["bullets"]:
            structural_issues.append(f"{blueprint['company']} is missing experience bullets.")
    if structural_issues:
        raise ValueError("Current resume content is invalid: " + " | ".join(structural_issues))
    return canonical


def mark_ai_session_audit_kept_current(session: dict) -> None:
    if session.get("audit_status") in AI_AUDIT_STALEABLE_STATUSES:
        session["audit_status"] = "kept_current"
        session["audit_proposal"] = None


def accept_ai_session_resume_content(
    session: dict,
    content: str,
    active_blueprints: list[dict],
) -> bool:
    current = ai_session_canonical_resume(session, active_blueprints)
    parsed = parse_ai_session_resume_content(content, session, active_blueprints)
    changed = canonical_json_hash(current) != canonical_json_hash(parsed)
    if changed:
        update_ai_session_structured_resume(session, parsed, active_blueprints)
        session["resume_revision"] = int(session.get("resume_revision") or 1) + 1
        session["has_manual_resume_edits"] = True
        mark_ai_session_audit_kept_current(session)
        capture_ai_session_resume_version(
            session,
            "manual",
            active_blueprints,
        )
    return changed


def prepare_ai_session_for_pdf(
    session: dict,
    content: str,
    enabled_experience_keys: list[str] | None,
) -> tuple[bool, list[dict]]:
    ensure_ai_session_state(session)
    previous_enabled_keys = normalize_enabled_experience_keys(
        session.get("enabled_experience_keys")
    )
    previous_blueprints = filter_blueprints_by_enabled_keys(
        current_experience_blueprints(),
        previous_enabled_keys,
    )
    if not previous_blueprints:
        raise ValueError("Keep at least one experience role enabled.")

    content_changed = accept_ai_session_resume_content(
        session,
        content,
        previous_blueprints,
    )

    next_enabled_keys = (
        normalize_enabled_experience_keys(enabled_experience_keys)
        if enabled_experience_keys is not None
        else previous_enabled_keys
    )
    active_blueprints = filter_blueprints_by_enabled_keys(
        current_experience_blueprints(),
        next_enabled_keys,
    )
    if not active_blueprints:
        raise ValueError("Keep at least one experience role enabled.")

    selection_changed = next_enabled_keys != previous_enabled_keys
    if selection_changed:
        session["enabled_experience_keys"] = next_enabled_keys
        session["resume_revision"] = int(session.get("resume_revision") or 1) + 1
        session["resume_content"] = format_ai_session_resume(session, active_blueprints)
        session["audit_status"] = "kept_current"
        session["audit_proposal"] = None
        session["has_manual_resume_edits"] = True
        capture_ai_session_resume_version(
            session,
            "manual",
            active_blueprints,
        )

    if content_changed or selection_changed:
        session["updated_at"] = time.time()
    return content_changed or selection_changed, active_blueprints


def canonical_resume_override_for_pdf(
    resume_override: dict,
    active_blueprints: list[dict],
) -> tuple[dict, dict]:
    filtered_override = apply_enabled_experience_filter(
        copy.deepcopy(resume_override),
        [blueprint["key"] for blueprint in active_blueprints],
    )
    experience_entries = (
        filtered_override.get("experience")
        if isinstance(filtered_override.get("experience"), list)
        else []
    )
    experience = {}
    for index, blueprint in enumerate(active_blueprints):
        entry = (
            experience_entries[index]
            if index < len(experience_entries)
            and isinstance(experience_entries[index], dict)
            else {}
        )
        experience[blueprint["key"]] = {
            "title": str(entry.get("title", "")).strip(),
            "bullets": [
                str(bullet).strip()
                for bullet in (entry.get("bullets") or [])
                if str(bullet).strip()
            ],
        }

    canonical = _canonical_editable_resume(
        {
            "updated_title": filtered_override.get("title", ""),
            "updated_summary": filtered_override.get("summary", ""),
            "updated_skills": normalize_updated_skills(
                filtered_override.get("technical_skills") or []
            ),
            "experience": experience,
        },
        active_blueprints,
    )
    return canonical, filtered_override


def resume_override_with_canonical_content(
    resume_override: dict,
    canonical_resume: dict,
    active_blueprints: list[dict],
) -> dict:
    synced = apply_enabled_experience_filter(
        copy.deepcopy(resume_override),
        [blueprint["key"] for blueprint in active_blueprints],
    )
    synced["title"] = canonical_resume["updated_title"]
    synced["summary"] = canonical_resume["updated_summary"]
    synced["technical_skills"] = copy.deepcopy(
        canonical_resume["updated_skills"]
    )
    experience_entries = (
        synced.get("experience")
        if isinstance(synced.get("experience"), list)
        else []
    )
    synced_experience = []
    for index, blueprint in enumerate(active_blueprints):
        existing = (
            copy.deepcopy(experience_entries[index])
            if index < len(experience_entries)
            and isinstance(experience_entries[index], dict)
            else {}
        )
        canonical_entry = canonical_resume["experience"][blueprint["key"]]
        existing["title"] = canonical_entry["title"]
        existing["bullets"] = copy.deepcopy(canonical_entry["bullets"])
        synced_experience.append(existing)
    synced["experience"] = synced_experience
    synced["_enabled_experience_keys"] = [
        blueprint["key"] for blueprint in active_blueprints
    ]
    return synced


def ai_session_state_payload(session: dict, active_blueprints: list[dict] | None = None) -> dict:
    ensure_ai_session_state(session)
    blueprints = active_blueprints if active_blueprints is not None else ai_session_active_blueprints(session)
    payload = {
        "job_description": session.get("job_description", ""),
        "analysis": session.get("analysis"),
        "title_summary": session.get("title_summary"),
        "skills": session.get("skills"),
        "core_resume": session.get("core_resume"),
        "experience_recent": session.get("experience_recent"),
        "experience_older": session.get("experience_older"),
        "enabled_experience_keys": [blueprint["key"] for blueprint in blueprints],
        "resume_content": session.get("resume_content", ""),
        "resume_revision": int(session.get("resume_revision") or 1),
        "audit_status": session.get("audit_status"),
        "audit_result": session.get("audit_result"),
        "audit_proposal": session.get("audit_proposal"),
        "audit_base_revision": session.get("audit_base_revision"),
        "audit_base_hash": session.get("audit_base_hash"),
        "audit_created_at": session.get("audit_created_at"),
        "audit_applied_at": session.get("audit_applied_at"),
        "resume_versions": copy.deepcopy(session.get("resume_versions") or {}),
        "active_resume_version": session.get("active_resume_version") or "",
    }
    if session.get("extension_draft_id"):
        payload["extension_draft_id"] = session["extension_draft_id"]
    return payload


def apply_reviewed_titles_to_experience_payload(experience_payload: dict, title_review_payload: dict) -> dict:
    merged_payload = json.loads(json.dumps(experience_payload or {}))
    experience = merged_payload.get("experience") or {}
    reviewed_titles = title_review_payload.get("experience_titles") or {}
    for key, title in reviewed_titles.items():
        if key in experience and isinstance(experience.get(key), dict):
            experience[key]["title"] = str(title or "").strip()
    merged_payload["experience"] = experience
    return merged_payload


def collect_experience_title_warnings(experience_payload: dict, analysis_payload: dict | None = None) -> list[str]:
    warnings: list[str] = []
    experience = experience_payload.get("experience") or {}
    enabled_keys = experience_payload.get("_enabled_experience_keys")
    for blueprint in filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_keys):
        entry = experience.get(blueprint["key"]) or {}
        _, warning = resolve_experience_title(entry.get("title") or "", blueprint, analysis_payload)
        if warning:
            warnings.append(warning)
    return warnings


def extract_output_text(response_payload: dict) -> str:
    top_level_output_text = response_payload.get("output_text")
    if isinstance(top_level_output_text, str) and top_level_output_text.strip():
        return top_level_output_text.strip()

    fragments: list[str] = []
    refusals: list[str] = []
    for item in response_payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                fragments.append(content["text"])
            elif content.get("type") == "refusal" and content.get("refusal"):
                refusals.append(str(content["refusal"]).strip())

    text = "".join(fragments).strip()
    if text:
        return text

    if refusals:
        raise RuntimeError("OpenAI API refused the request: " + " | ".join(refusals))

    status = str(response_payload.get("status", "")).strip()
    if status and status != "completed":
        details = response_payload.get("incomplete_details") or response_payload.get("error") or {}
        raise RuntimeError(f"OpenAI API returned no final output (status={status}, details={details})")

    raise RuntimeError("OpenAI API returned no text output")


def _post_openai_payload(
    *,
    api_key: str,
    payload: dict,
    request_timeout_seconds: int,
) -> dict:
    return _request_openai_json(
        api_key=api_key,
        url=OPENAI_API_URL,
        method="POST",
        payload=payload,
        request_timeout_seconds=request_timeout_seconds,
    )


def _request_openai_json(
    *,
    api_key: str,
    url: str,
    method: str,
    request_timeout_seconds: int,
    payload: dict | None = None,
) -> dict:
    req = urllib.request.Request(
        url,
        data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=request_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error ({exc.code}): {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc.reason}") from exc
    except (ConnectionError, TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc


def _get_openai_response_payload(
    *,
    api_key: str,
    response_id: str,
    request_timeout_seconds: int,
) -> dict:
    safe_response_id = urllib.parse.quote(str(response_id), safe="")
    return _request_openai_json(
        api_key=api_key,
        url=f"{OPENAI_API_URL}/{safe_response_id}",
        method="GET",
        request_timeout_seconds=request_timeout_seconds,
    )


def _mark_background_response_error(
    exc: Exception,
    response_id: str,
) -> Exception:
    try:
        exc.openai_response_started = True
        exc.openai_response_id = response_id
    except (AttributeError, TypeError):
        pass
    return exc


def _poll_openai_background_response(
    *,
    api_key: str,
    initial_response: dict,
    request_timeout_seconds: int,
    overall_timeout_seconds: int,
    poll_interval_seconds: float,
) -> dict:
    response_payload = initial_response
    response_id = str(response_payload.get("id", "")).strip()
    if not response_id:
        raise RuntimeError("OpenAI background response did not include a response ID.")

    deadline = time.monotonic() + max(1, overall_timeout_seconds)
    while str(response_payload.get("status", "")).strip() in {"queued", "in_progress"}:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            error = RuntimeError(
                f"OpenAI background response {response_id} did not finish within "
                f"{overall_timeout_seconds}s"
            )
            raise _mark_background_response_error(error, response_id)

        time.sleep(min(max(0.1, poll_interval_seconds), remaining))
        try:
            response_payload = _get_openai_response_payload(
                api_key=api_key,
                response_id=response_id,
                request_timeout_seconds=max(
                    1,
                    min(request_timeout_seconds, int(max(1, remaining))),
                ),
            )
        except Exception as exc:
            if _is_transient_audit_network_error(exc) and time.monotonic() < deadline:
                continue
            raise _mark_background_response_error(exc, response_id)

    return response_payload


def call_openai_structured_output(
    *,
    api_key: str,
    model: str,
    temperature: float,
    developer_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict,
    max_output_tokens: int,
    request_timeout_seconds: int,
    reasoning_effort: str = "low",
    background: bool = False,
    background_timeout_seconds: int | None = None,
    background_poll_interval_seconds: float = OPENAI_BACKGROUND_POLL_INTERVAL_SECONDS,
) -> dict:
    payload = {
        "model": model,
        "input": [
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
        "max_output_tokens": max_output_tokens,
    }

    if temperature is not None and model.startswith("gpt-4o"):
        payload["temperature"] = temperature

    if reasoning_effort and model.startswith("gpt-5"):
        payload["reasoning"] = {"effort": reasoning_effort}
    if background:
        payload["background"] = True

    http_timeout = request_timeout_seconds
    if background:
        http_timeout = min(
            request_timeout_seconds,
            OPENAI_BACKGROUND_HTTP_TIMEOUT_SECONDS,
        )
    response_payload = _post_openai_payload(
        api_key=api_key,
        payload=payload,
        request_timeout_seconds=http_timeout,
    )
    if background:
        response_payload = _poll_openai_background_response(
            api_key=api_key,
            initial_response=response_payload,
            request_timeout_seconds=http_timeout,
            overall_timeout_seconds=(
                background_timeout_seconds
                if background_timeout_seconds is not None
                else request_timeout_seconds
            ),
            poll_interval_seconds=background_poll_interval_seconds,
        )

    status = str(response_payload.get("status", "")).strip()
    if status and status != "completed":
        details = response_payload.get("incomplete_details") or response_payload.get("error") or {}
        raise RuntimeError(f"OpenAI API returned no final output (status={status}, details={details})")

    output_text = extract_output_text(response_payload)

    try:
        return json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse model output JSON: {exc}") from exc


def call_openai_text_output(
    *,
    api_key: str,
    model: str,
    temperature: float,
    developer_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    request_timeout_seconds: int,
    reasoning_effort: str = "low",
) -> str:
    payload = {
        "model": model,
        "input": [
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_output_tokens": max_output_tokens,
    }

    if temperature is not None and model.startswith("gpt-4o"):
        payload["temperature"] = temperature

    if reasoning_effort and model.startswith("gpt-5"):
        payload["reasoning"] = {"effort": reasoning_effort}
    response_payload = _post_openai_payload(
        api_key=api_key,
        payload=payload,
        request_timeout_seconds=request_timeout_seconds,
    )
    return extract_output_text(response_payload)


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w%&.+#/-]+\b", text or ""))


ANALYST_EXPLICIT_TOOL_TERMS = {
    "excel",
    "power bi",
    "tableau",
    "looker",
    "jira",
    "confluence",
    "salesforce",
    "sap",
    "oracle",
    "workday",
    "peoplesoft",
    "banner",
    "manhattan scale",
    "manhattan active",
    "blue yonder",
}

GTM_EXPLICIT_TOOL_TERMS = {
    "clay",
    "salesforce",
    "hubspot",
    "outreach",
    "apollo",
    "marketo",
    "6sense",
    "gong",
    "customer.io",
    "zoominfo",
    "smartlead",
    "instantly",
    "heyreach",
    "nooks",
    "warmly",
}

GTM_AMBIGUOUS_COMMON_NOUN_TOOLS = {"outreach"}

AUDIT_KNOWN_NAMED_TECHNOLOGY_TERMS = frozenset(
    {
        normalize_skill_dedupe_key(term)
        for term in {
            "Python",
            "Java",
            "JavaScript",
            "TypeScript",
            "SQL",
            "C#",
            "C++",
            "Rust",
            "Scala",
            "React",
            "ReactJS",
            "Next.js",
            "Node.js",
            "GraphQL",
            "gRPC",
            "Protobuf",
            "Tokio",
            "Flask",
            "FastAPI",
            "Spring Boot",
            "ASP.NET",
            "Entity Framework",
            "Snowflake",
            "PostgreSQL",
            "MySQL",
            "SQL Server",
            "Redis",
            "MongoDB",
            "AWS",
            "GCP",
            "Azure",
            "Google Cloud",
            "Docker",
            "Kubernetes",
            "Terraform",
            "Terragrunt",
            "Pulumi",
            "Helm",
            "CloudFormation",
            "AWS CDK",
            "AWS Lambda",
            "Cloud Run",
            "GKE",
            "EKS",
            "ECS",
            "GitHub Actions",
            "GitLab",
            "Jenkins",
            "ArgoCD",
            "CodePipeline",
            "Prometheus",
            "Grafana",
            "CloudWatch",
            "Datadog",
            "OpenTelemetry",
            "Cypress",
            "Jest",
            "Claude",
            "Anthropic",
            "OpenAI",
            "LangChain",
            "LangGraph",
            "AutoGen",
            "CrewAI",
            "Semantic Kernel",
            "LlamaIndex",
            "MLflow",
            "PyTorch",
            "TensorFlow",
            "scikit-learn",
            "pandas",
            "NumPy",
            "PySpark",
            "Spark",
            "Airflow",
            "Dagster",
            "Prefect",
            "dbt",
            "AWS Glue",
            "Azure Data Factory",
            "Databricks",
            "SageMaker",
            "Vertex AI",
            "Kafka",
            "Pub/Sub",
            "WebSocket",
            "JWT",
            "OAuth",
            "NixOS",
            "ROS2",
            "Workato",
            "Tray.io",
            "n8n",
        }
        | ANALYST_EXPLICIT_TOOL_TERMS
        | (GTM_EXPLICIT_TOOL_TERMS - GTM_AMBIGUOUS_COMMON_NOUN_TOOLS)
        if len(normalize_skill_dedupe_key(term)) >= 2
    }
)

ANALYST_TOOL_GENERIC_REPLACEMENTS = {
    "excel": "reporting tools",
    "power bi": "dashboard tools",
    "tableau": "dashboard tools",
    "looker": "reporting platforms",
    "jira": "workflow tools",
    "confluence": "documentation systems",
    "salesforce": "business systems",
    "sap": "business systems",
    "oracle": "business systems",
    "workday": "business systems",
    "peoplesoft": "business systems",
    "banner": "business systems",
    "wms": "warehouse systems",
    "crm": "customer systems",
    "erp": "business systems",
    "scm": "supply chain systems",
    "manhattan scale": "warehouse systems",
    "manhattan active": "warehouse systems",
    "blue yonder": "supply chain systems",
}


ANALYST_GENERIC_ALLOWED_ITEMS = {
    "data analysis",
    "budget tracking",
    "risk management",
    "stakeholder management",
    "stakeholder communication",
    "requirements gathering",
    "requirements documentation",
    "functional specifications",
    "process mapping",
    "gap analysis",
    "feasibility studies",
    "audit activities",
    "audit findings",
    "uat",
    "user acceptance testing",
    "testing scripts",
    "verification criteria",
    "kpi tracking",
    "dashboarding",
    "dashboards",
    "trend analysis",
    "variance reporting",
    "decision support",
    "insights synthesis",
    "reporting",
    "reporting accuracy",
    "stakeholder engagement",
    "cross-functional coordination",
}


def is_analyst_prompt_family(analysis_payload: dict) -> bool:
    prompt_family = prompt_family_key_for_analysis(analysis_payload)
    return prompt_family in {"analyst_data", "analyst_business", "analyst_marketing"}


def is_gtm_prompt_family(analysis_payload: dict) -> bool:
    prompt_family = prompt_family_key_for_analysis(analysis_payload)
    return prompt_family == "gtm_engineering"


def analyst_tool_not_in_jd(item: str, analysis_payload: dict) -> str | None:
    lowered_item = normalize_skill_dedupe_key(item)
    if not lowered_item:
        return None
    jd_terms = [normalize_skill_dedupe_key(term) for term in (analysis_payload.get("skills_mentioned") or [])]
    for tool in ANALYST_EXPLICIT_TOOL_TERMS:
        if tool in lowered_item:
            if any(tool in jd_term for jd_term in jd_terms):
                return None
            return tool
    return None


def analyst_tool_mentions_not_in_jd(text: str, analysis_payload: dict) -> list[str]:
    lowered_text = normalize_skill_dedupe_key(text)
    if not lowered_text:
        return []
    jd_terms = [normalize_skill_dedupe_key(term) for term in (analysis_payload.get("skills_mentioned") or [])]
    unsupported: list[str] = []
    for tool in sorted(ANALYST_EXPLICIT_TOOL_TERMS):
        if tool in lowered_text and not any(tool in jd_term for jd_term in jd_terms):
            unsupported.append(tool)
    return unsupported


def sanitize_unsupported_analyst_tools_in_text(text: str, analysis_payload: dict) -> str:
    sanitized = text or ""
    unsupported_tools = analyst_tool_mentions_not_in_jd(sanitized, analysis_payload)
    for tool in sorted(set(unsupported_tools), key=len, reverse=True):
        replacement = ANALYST_TOOL_GENERIC_REPLACEMENTS.get(tool, "business systems")
        sanitized = re.sub(re.escape(tool), replacement, sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\s{2,}", " ", sanitized).strip()
    return sanitized


def sanitize_experience_payload_for_prompt_family(experience_payload: dict, analysis_payload: dict) -> dict:
    if not is_analyst_prompt_family(analysis_payload):
        return experience_payload
    experience = experience_payload.get("experience") or {}
    for entry in experience.values():
        bullets = [str(bullet).strip() for bullet in entry.get("bullets", []) if str(bullet).strip()]
        entry["bullets"] = [sanitize_unsupported_analyst_tools_in_text(bullet, analysis_payload) for bullet in bullets]
    return experience_payload


def validate_generated_experience_evidence(experience_payload: dict, blueprints: list[dict]) -> list[str]:
    """Reject numeric metrics that are not grounded in immutable experience evidence."""
    issues: list[str] = []
    experience = experience_payload.get("experience") or {}
    for blueprint in blueprints:
        entry = experience.get(blueprint["key"]) or {}
        grounded_metric_evidence = {
            key: blueprint.get(key)
            for key in ("anchor", "metric_evidence", "evidence", "achievements", "source_bullets")
            if blueprint.get(key)
        }
        grounded_numeric_tokens = _numeric_tokens(grounded_metric_evidence)
        bullets = [str(bullet).strip() for bullet in entry.get("bullets", []) if str(bullet).strip()]
        for index, bullet in enumerate(bullets, start=1):
            numeric_tokens = _numeric_tokens(bullet)
            unsupported_tokens = sorted(numeric_tokens - grounded_numeric_tokens)
            if unsupported_tokens:
                issues.append(
                    f"{blueprint['company']} bullet {index} introduces unsupported numeric metrics: "
                    + ", ".join(unsupported_tokens)
                    + "."
                )
    return issues


def gtm_tool_not_in_jd(item: str, analysis_payload: dict) -> str | None:
    lowered_item = normalize_skill_dedupe_key(item)
    if not lowered_item:
        return None
    jd_terms = [normalize_skill_dedupe_key(term) for term in (analysis_payload.get("skills_mentioned") or [])]
    for tool in GTM_EXPLICIT_TOOL_TERMS:
        if tool in GTM_AMBIGUOUS_COMMON_NOUN_TOOLS:
            if not re.search(rf"\b{re.escape(tool)}\b", lowered_item):
                continue
        elif tool not in lowered_item:
            continue
        if any(tool in jd_term for jd_term in jd_terms):
            return None
        return tool
    return None


def gtm_tool_mentions_not_in_jd(text: str, analysis_payload: dict) -> list[str]:
    lowered_text = normalize_skill_dedupe_key(text)
    if not lowered_text:
        return []
    jd_terms = [normalize_skill_dedupe_key(term) for term in (analysis_payload.get("skills_mentioned") or [])]
    unsupported: list[str] = []
    for tool in sorted(GTM_EXPLICIT_TOOL_TERMS):
        if tool in GTM_AMBIGUOUS_COMMON_NOUN_TOOLS:
            if not re.search(rf"\b{re.escape(tool)}\b", lowered_text):
                continue
        elif tool not in lowered_text:
            continue
        if not any(tool in jd_term for jd_term in jd_terms):
            unsupported.append(tool)
    return unsupported


def validate_model_payload(model_payload: dict, enabled_experience_keys: list[str] | None = None) -> list[str]:
    issues: list[str] = []
    analysis = model_payload.get("analysis") or {}
    resume = model_payload.get("resume") or {}
    title = str(resume.get("updated_title", "")).strip()
    summary = str(resume.get("updated_summary", "")).strip()
    skills = normalize_updated_skills(resume.get("updated_skills") or [])
    experience = resume.get("experience") or {}
    jd_terms = {
        str(item).strip().lower()
        for item in (analysis.get("skills_mentioned") or [])
        if str(item).strip()
    }

    if not title:
        issues.append("Updated title is empty.")
    title_word_count = count_words(title)
    if title and not (TITLE_WORD_MIN <= title_word_count <= TITLE_WORD_MAX):
        issues.append(f"Updated title must be {TITLE_WORD_MIN}-{TITLE_WORD_MAX} words; got {title_word_count}.")

    summary_word_count = count_words(summary)
    if not summary or not (SUMMARY_WORD_MIN <= summary_word_count <= SUMMARY_WORD_MAX):
        issues.append(f"Updated summary must be {SUMMARY_WORD_MIN}-{SUMMARY_WORD_MAX} words; got {summary_word_count}.")
    if summary.lower().startswith(("results-driven", "experienced professional", "seasoned professional")):
        issues.append("Updated summary starts with generic filler.")

    if len(skills) < 6:
        issues.append("Updated skills must contain at least 6 categories.")

    seen_categories: set[str] = set()
    all_skill_items: list[str] = []
    for entry in skills:
        category = str(entry.get("category", "")).strip()
        items = expand_skill_items(entry.get("items", []))
        if not category:
            issues.append("A skills category is empty.")
            continue
        if category in seen_categories:
            issues.append(f"Duplicate skills category: {category}.")
        seen_categories.add(category)
        if category not in ALLOWED_SKILL_CATEGORIES:
            issues.append(f"Unsupported skills category: {category}.")
        if len(items) < 2:
            issues.append(f"Skills category '{category}' must contain at least 2 skills.")
        for item in items:
            if ":" in item or len(item) > 60 or "?" in item:
                issues.append(f"Skill item '{item}' in '{category}' is malformed.")
            if skill_item_looks_like_model_meta(item):
                issues.append(f"Skill item '{item}' in '{category}' contains model meta text.")
            all_skill_items.append(item.lower())

    if len(set(all_skill_items)) < max(len(all_skill_items) - 3, 1):
        issues.append("Updated skills repeat too many items across categories.")

    if jd_terms:
        matched_skill_terms = 0
        for term in jd_terms:
            if any(term in item or item in term for item in all_skill_items):
                matched_skill_terms += 1
        if matched_skill_terms < min(4, len(jd_terms)):
            issues.append("Updated skills do not sufficiently reflect the JD problem statement.")

    if not analysis.get("core_problem"):
        issues.append("Analysis is missing core_problem.")
    if not analysis.get("target_role"):
        issues.append("Analysis is missing target_role.")

    for blueprint in filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_experience_keys):
        entry = experience.get(blueprint["key"]) or {}
        role_title = str(entry.get("title", "")).strip()
        bullets = [str(bullet).strip() for bullet in entry.get("bullets", []) if str(bullet).strip()]
        if not role_title:
            issues.append(f"{blueprint['company']} is missing a role title.")
        if role_title == blueprint["location"] or role_title == blueprint["dates"]:
            issues.append(f"{blueprint['company']} has an invalid role title.")
        if not (blueprint["bullet_min"] <= len(bullets) <= blueprint["bullet_max"]):
            issues.append(
                f"{blueprint['company']} must have {blueprint['bullet_min']}-{blueprint['bullet_max']} bullets."
            )

        if not bullets:
            continue

        first_words = {re.findall(r"\b\w+\b", bullet.lower())[0] for bullet in bullets if re.findall(r"\b\w+\b", bullet.lower())}
        if len(first_words) < max(2, min(3, len(bullets))):
            issues.append(f"{blueprint['company']} bullets reuse the same opening verbs too often.")

        for index, bullet in enumerate(bullets, start=1):
            word_count = count_words(bullet)
            lower_bullet = bullet.lower()
            if not (EXPERIENCE_BULLET_WORD_MIN <= word_count <= EXPERIENCE_BULLET_WORD_MAX):
                issues.append(
                    f"{blueprint['company']} bullet {index} must be "
                    f"{EXPERIENCE_BULLET_WORD_MIN}-{EXPERIENCE_BULLET_WORD_MAX} words; got {word_count}."
                )
            if not bullet.endswith("."):
                issues.append(f"{blueprint['company']} bullet {index} must end with a period.")
            if any(pattern in lower_bullet for pattern in GENERIC_BULLET_PATTERNS):
                issues.append(f"{blueprint['company']} bullet {index} is too generic.")
            if not any(term in lower_bullet for term in SYSTEM_SIGNAL_TERMS):
                issues.append(f"{blueprint['company']} bullet {index} is missing concrete system context.")
            if not any(term in lower_bullet for term in CONSTRAINT_SIGNAL_TERMS | DECISION_SIGNAL_TERMS | SYSTEM_SIGNAL_TERMS):
                issues.append(f"{blueprint['company']} bullet {index} is missing technical depth.")
            if " using " not in lower_bullet and " with " not in lower_bullet:
                issues.append(f"{blueprint['company']} bullet {index} does not clearly follow X-Y-Z structure.")
            if jd_terms and not any(term in lower_bullet for term in jd_terms):
                issues.append(f"{blueprint['company']} bullet {index} does not use JD-relevant skills or tools.")
            if is_analyst_prompt_family(analysis):
                unsupported_tools = analyst_tool_mentions_not_in_jd(bullet, analysis)
                if unsupported_tools:
                    issues.append(
                        f"{blueprint['company']} bullet {index} introduces analyst tools not named in the JD: {', '.join(sorted(set(unsupported_tools)))}."
                    )
            if is_gtm_prompt_family(analysis):
                unsupported_tools = gtm_tool_mentions_not_in_jd(bullet, analysis)
                if unsupported_tools:
                    issues.append(
                        f"{blueprint['company']} bullet {index} introduces GTM tools not named in the JD: {', '.join(sorted(set(unsupported_tools)))}."
                    )

            forbidden_terms = FORBIDDEN_TERMS_BY_BLUEPRINT_KEY.get(blueprint["key"], set())
            if forbidden_terms and any(term in lower_bullet for term in forbidden_terms):
                issues.append(f"{blueprint['company']} bullet {index} uses technology outside the allowed timeline.")

        if count_words(" ".join(bullets[:2])) and not any(term in " ".join(bullets[:2]).lower() for term in SYSTEM_SIGNAL_TERMS):
            issues.append(f"{blueprint['company']} opening bullets do not establish the system story clearly.")

    issues.extend(
        validate_generated_experience_evidence(
            resume,
            filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_experience_keys),
        )
    )
    return issues


def validate_core_payload(core_payload: dict, analysis_payload: dict) -> list[str]:
    issues: list[str] = []
    title = str(core_payload.get("updated_title", "")).strip()
    summary = str(core_payload.get("updated_summary", "")).strip()
    skills = normalize_updated_skills(core_payload.get("updated_skills") or [])

    if not title:
        issues.append("Updated title is empty.")
    title_word_count = count_words(title)
    if title and not (TITLE_WORD_MIN <= title_word_count <= TITLE_WORD_MAX):
        issues.append(f"Updated title must be {TITLE_WORD_MIN}-{TITLE_WORD_MAX} words; got {title_word_count}.")

    summary_word_count = count_words(summary)
    if not summary or not (SUMMARY_WORD_MIN <= summary_word_count <= SUMMARY_WORD_MAX):
        issues.append(f"Updated summary must be {SUMMARY_WORD_MIN}-{SUMMARY_WORD_MAX} words; got {summary_word_count}.")
    if is_analyst_prompt_family(analysis_payload):
        unsupported_tools = analyst_tool_mentions_not_in_jd(summary, analysis_payload)
        if unsupported_tools:
            issues.append(
                "Updated summary introduces analyst tools not named in the JD: " + ", ".join(sorted(set(unsupported_tools))) + "."
            )
    if is_gtm_prompt_family(analysis_payload):
        unsupported_tools = gtm_tool_mentions_not_in_jd(summary, analysis_payload)
        if unsupported_tools:
            issues.append(
                "Updated summary introduces GTM tools not named in the JD: " + ", ".join(sorted(set(unsupported_tools))) + "."
            )

    if len(skills) < 6:
        issues.append("Updated skills must contain at least 6 categories.")

    seen_categories: set[str] = set()
    for entry in skills:
        category = str(entry.get("category", "")).strip()
        items = expand_skill_items(entry.get("items", []))
        if not category:
            issues.append("A skills category is empty.")
            continue
        if category in seen_categories:
            issues.append(f"Duplicate skills category: {category}.")
        seen_categories.add(category)
        if category not in ALLOWED_SKILL_CATEGORIES:
            issues.append(f"Unsupported skills category: {category}.")
        if len(items) < 2:
            issues.append(f"Skills category '{category}' must contain at least 2 skills.")
        for item in items:
            if ":" in item or len(item) > 60 or "?" in item:
                issues.append(f"Skill item '{item}' in '{category}' is malformed.")
            if skill_item_looks_like_model_meta(item):
                issues.append(f"Skill item '{item}' in '{category}' contains model meta text.")
            if is_analyst_prompt_family(analysis_payload):
                unsupported_tool = analyst_tool_not_in_jd(item, analysis_payload)
                if unsupported_tool:
                    issues.append(
                        f"Skill item '{item}' in '{category}' introduces analyst tool '{unsupported_tool}' that the JD did not mention."
                    )
            if is_gtm_prompt_family(analysis_payload):
                unsupported_tool = gtm_tool_not_in_jd(item, analysis_payload)
                if unsupported_tool:
                    issues.append(
                        f"Skill item '{item}' in '{category}' introduces GTM tool '{unsupported_tool}' that the JD did not mention."
                    )

    if not analysis_payload.get("core_problem"):
        issues.append("Analysis is missing core_problem.")
    if not analysis_payload.get("target_role"):
        issues.append("Analysis is missing target_role.")

    return issues


def validate_title_summary_payload(title_summary_payload: dict, analysis_payload: dict | None = None, *, summary_max_buffer: int = 0) -> list[str]:
    issues: list[str] = []
    title = str(title_summary_payload.get("updated_title", "")).strip()
    summary = str(title_summary_payload.get("updated_summary", "")).strip()
    title_word_count = count_words(title)
    summary_word_count = count_words(summary)

    if not title:
        issues.append("Updated title is empty.")
    elif not (TITLE_WORD_MIN <= title_word_count <= TITLE_WORD_MAX):
        issues.append(f"Updated title must be {TITLE_WORD_MIN}-{TITLE_WORD_MAX} words; got {title_word_count}.")

    if not summary:
        issues.append("Updated summary is empty.")
    else:
        summary_word_max = SUMMARY_WORD_MAX + max(summary_max_buffer, 0)
        if not (SUMMARY_WORD_MIN <= summary_word_count <= summary_word_max):
            if summary_word_max == SUMMARY_WORD_MAX:
                issues.append(f"Updated summary must be {SUMMARY_WORD_MIN}-{SUMMARY_WORD_MAX} words; got {summary_word_count}.")
            else:
                issues.append(
                    f"Updated summary must be {SUMMARY_WORD_MIN}-{SUMMARY_WORD_MAX} words; buffer allows up to {summary_word_max}. Got {summary_word_count}."
                )

    if analysis_payload and is_analyst_prompt_family(analysis_payload):
        unsupported_tools = analyst_tool_mentions_not_in_jd(summary, analysis_payload)
        if unsupported_tools:
            issues.append(
                "Updated summary introduces analyst tools not named in the JD: " + ", ".join(sorted(set(unsupported_tools))) + "."
            )
    if analysis_payload and is_gtm_prompt_family(analysis_payload):
        unsupported_tools = gtm_tool_mentions_not_in_jd(summary, analysis_payload)
        if unsupported_tools:
            issues.append(
                "Updated summary introduces GTM tools not named in the JD: " + ", ".join(sorted(set(unsupported_tools))) + "."
            )

    return issues


def validate_skills_only_payload(skills_payload: dict, analysis_payload: dict) -> list[str]:
    issues: list[str] = []
    skills = normalize_updated_skills(skills_payload.get("updated_skills") or [])
    if len(skills) < 6:
        issues.append("Updated skills must contain at least 6 categories.")
    seen_categories: set[str] = set()
    for entry in skills:
        category = str(entry.get("category", "")).strip()
        items = expand_skill_items(entry.get("items", []))
        if not category:
            issues.append("A skills category is empty.")
            continue
        if category in seen_categories:
            issues.append(f"Duplicate skills category: {category}.")
        seen_categories.add(category)
        if category not in ALLOWED_SKILL_CATEGORIES:
            issues.append(f"Unsupported skills category: {category}.")
        if len(items) < 2:
            issues.append(f"Skills category '{category}' must contain at least 2 skills.")
        for item in items:
            if is_analyst_prompt_family(analysis_payload):
                unsupported_tool = analyst_tool_not_in_jd(item, analysis_payload)
                if unsupported_tool:
                    issues.append(
                        f"Skill item '{item}' in '{category}' introduces analyst tool '{unsupported_tool}' that the JD did not mention."
                    )
            if is_gtm_prompt_family(analysis_payload):
                unsupported_tool = gtm_tool_not_in_jd(item, analysis_payload)
                if unsupported_tool:
                    issues.append(
                        f"Skill item '{item}' in '{category}' introduces GTM tool '{unsupported_tool}' that the JD did not mention."
                    )
    if not analysis_payload.get("core_problem"):
        issues.append("Analysis is missing core_problem.")
    return issues


def validate_experience_subset_payload(experience_payload: dict, blueprints: list[dict]) -> list[str]:
    issues: list[str] = []
    experience = experience_payload.get("experience") or {}
    for blueprint in blueprints:
        entry = experience.get(blueprint["key"]) or {}
        role_title = str(entry.get("title", "")).strip()
        bullets = [str(bullet).strip() for bullet in entry.get("bullets", []) if str(bullet).strip()]
        if not role_title:
            issues.append(f"{blueprint['company']} is missing a role title.")
        invalid_reason = invalid_experience_title_reason(role_title, blueprint)
        if invalid_reason == "metadata echo":
            issues.append(f"{blueprint['company']} returned metadata instead of a role title: '{role_title}'.")
        if not (blueprint["bullet_min"] <= len(bullets) <= blueprint["bullet_max"]):
            issues.append(f"{blueprint['company']} must have {blueprint['bullet_min']}-{blueprint['bullet_max']} bullets.")
    return issues


def validate_experience_subset_payload_with_analysis(experience_payload: dict, blueprints: list[dict], analysis_payload: dict) -> list[str]:
    issues = validate_experience_subset_payload(experience_payload, blueprints)
    if not is_analyst_prompt_family(analysis_payload):
        if not is_gtm_prompt_family(analysis_payload):
            return issues

    experience = experience_payload.get("experience") or {}
    for blueprint in blueprints:
        entry = experience.get(blueprint["key"]) or {}
        bullets = [str(bullet).strip() for bullet in entry.get("bullets", []) if str(bullet).strip()]
        for index, bullet in enumerate(bullets, start=1):
            if is_analyst_prompt_family(analysis_payload):
                unsupported_tools = analyst_tool_mentions_not_in_jd(bullet, analysis_payload)
                if unsupported_tools:
                    issues.append(
                        f"{blueprint['company']} bullet {index} introduces analyst tools not named in the JD: {', '.join(sorted(set(unsupported_tools)))}."
                    )
            if is_gtm_prompt_family(analysis_payload):
                unsupported_tools = gtm_tool_mentions_not_in_jd(bullet, analysis_payload)
                if unsupported_tools:
                    issues.append(
                        f"{blueprint['company']} bullet {index} introduces GTM tools not named in the JD: {', '.join(sorted(set(unsupported_tools)))}."
                    )
    return issues


def validate_reachout_payload(reachout_payload: dict) -> list[str]:
    issues: list[str] = []
    message = str(reachout_payload.get("message", "")).strip()
    char_count = reachout_payload.get("char_count")

    if not message:
        issues.append("Reachout message is empty.")
        return issues

    if "\n\n" in message:
        issues.append("Reachout message should stay compact.")
    if isinstance(char_count, int) and char_count != len(message):
        issues.append("Reachout character count does not match the message length.")
    if re.search(r"[•#\"“”]", message):
        issues.append("Reachout message contains unsupported formatting.")

    return issues


def validate_experience_title_review_payload(
    title_review_payload: dict,
    blueprints: list[dict],
    analysis_payload: dict,
) -> list[str]:
    issues: list[str] = []
    reviewed_titles = title_review_payload.get("experience_titles") or {}
    for blueprint in blueprints:
        title = str(reviewed_titles.get(blueprint["key"], "")).strip()
        invalid_reason = invalid_experience_title_reason(title, blueprint)
        if invalid_reason == "missing title":
            issues.append(f"{blueprint['company']} is missing a reviewed title.")
            continue
        if invalid_reason == "metadata echo":
            issues.append(f"{blueprint['company']} reviewed title is metadata instead of a role title: '{title}'.")
            continue

    return issues


def validate_final_synthesis_payload(
    synthesis_payload: dict,
    active_blueprints: list[dict],
    analysis_payload: dict,
) -> list[str]:
    order_key = skill_category_order_key_for_analysis(analysis_payload)
    ordered_categories = skill_category_order_for_key(order_key)
    normalized_skills = normalize_skills_for_order(synthesis_payload, ordered_categories)
    issues = validate_title_summary_payload(synthesis_payload, analysis_payload)
    issues.extend(validate_skills_only_payload(normalized_skills, analysis_payload))
    issues.extend(validate_experience_title_review_payload(synthesis_payload, active_blueprints, analysis_payload))
    return issues


def analyze_job_description(
    *,
    api_key: str,
    job_description: str,
) -> dict:
    analysis_user_parts = [
        f"Job description:\n{job_description.strip()}",
        "Return the full JD intelligence analysis aligned to the required schema.",
    ]

    result = call_openai_structured_output(
        api_key=api_key,
        model=ANALYSIS_MODEL,
        temperature=ANALYSIS_TEMPERATURE,
        developer_prompt=build_ai_analysis_prompt(),
        user_prompt="\n\n".join(analysis_user_parts),
        schema_name="jd_analysis",
        schema=ai_analysis_schema(),
        max_output_tokens=with_output_headroom(ANALYSIS_MAX_OUTPUT_TOKENS, MEDIUM_OUTPUT_HEADROOM),
        request_timeout_seconds=OPENAI_ANALYSIS_TIMEOUT_SECONDS,
        reasoning_effort="low",
    )
    return normalize_analysis_payload(result)


def generate_resume_from_analysis(
    *,
    api_key: str,
    job_description: str,
    analysis_payload: dict,
    revision_request: str = "",
    current_resume_content: str = "",
    memory_block: str = "",
    enabled_experience_keys: list[str] | None = None,
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    blueprints = filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_experience_keys)
    resume_user_parts = [
        f"Job description:\n{job_description.strip()}",
        "Use the full JD analysis below as the source of truth. Generate only the final resume object matching the required schema.",
        "JD analysis:",
        json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
    ]
    if revision_request.strip():
        resume_user_parts.append(f"Current refinement request:\n{revision_request.strip()}")
    if current_resume_content.strip():
        resume_user_parts.append(f"Current edited draft from the user:\n{current_resume_content.strip()}")
    if memory_block:
        resume_user_parts.append(f"Previous session memory (maximum two turns):\n{memory_block}")

    return call_openai_structured_output(
        api_key=api_key,
        model=RESUME_MODEL,
        temperature=RESUME_TEMPERATURE,
        developer_prompt=build_ai_resume_prompt(enabled_experience_keys),
        user_prompt="\n\n".join(resume_user_parts),
        schema_name="resume_generation",
        schema=ai_resume_schema(blueprints),
        max_output_tokens=with_output_headroom(RESUME_MAX_OUTPUT_TOKENS, LARGE_OUTPUT_HEADROOM),
        request_timeout_seconds=OPENAI_RESUME_TIMEOUT_SECONDS,
        reasoning_effort="low",
    )


def generate_resume_core_from_analysis(
    *,
    api_key: str,
    job_description: str,
    analysis_payload: dict,
    revision_request: str = "",
    current_resume_content: str = "",
    memory_block: str = "",
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    user_parts = [
        f"Job description:\n{job_description.strip()}",
        "Use the JD analysis below as the source of truth. Generate only Updated Title, Updated Summary, and Updated Skills.",
        "JD analysis:",
        json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
    ]
    if revision_request.strip():
        user_parts.append(f"Current refinement request:\n{revision_request.strip()}")
    if current_resume_content.strip():
        user_parts.append(f"Current edited draft from the user:\n{current_resume_content.strip()}")
    if memory_block:
        user_parts.append(f"Previous session memory (maximum two turns):\n{memory_block}")

    raw_payload = call_openai_structured_output(
        api_key=api_key,
        model=RESUME_MODEL,
        temperature=RESUME_TEMPERATURE,
        developer_prompt=build_ai_resume_core_prompt(),
        user_prompt="\n\n".join(user_parts),
        schema_name="resume_core_generation",
        schema=ai_resume_core_schema(),
        max_output_tokens=with_output_headroom(6500, LARGE_OUTPUT_HEADROOM),
        request_timeout_seconds=OPENAI_RESUME_TIMEOUT_SECONDS,
        reasoning_effort="low",
    )
    order_key = skill_category_order_key_for_analysis(analysis_payload)
    ordered_categories = skill_category_order_for_key(order_key)
    raw_payload["updated_skills"] = normalize_skills_for_order(
        {"updated_skills": raw_payload.get("updated_skills", [])},
        ordered_categories,
    )["updated_skills"]
    return raw_payload


def generate_title_summary_from_analysis(
    *,
    api_key: str,
    analysis_payload: dict,
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    prompt_family_key = prompt_family_key_for_analysis(analysis_payload)
    user_parts = [
        "Analysis:\n" + json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
    ]

    def run_generation(extra_instruction: str = "") -> dict:
        prompt_parts = list(user_parts)
        if extra_instruction:
            prompt_parts.append(extra_instruction)
        return call_openai_structured_output(
            api_key=api_key,
            model=RESUME_MODEL,
            temperature=RESUME_TEMPERATURE,
            developer_prompt=build_ai_resume_title_summary_prompt(prompt_family_key),
            user_prompt="\n\n".join(prompt_parts),
            schema_name="resume_title_summary_generation",
            schema=ai_title_summary_schema(),
            max_output_tokens=with_output_headroom(2200, SMALL_OUTPUT_HEADROOM),
            request_timeout_seconds=OPENAI_RESUME_TIMEOUT_SECONDS,
            reasoning_effort="low",
        )

    title_summary_payload = run_generation()
    validation_issues = validate_title_summary_payload(title_summary_payload, analysis_payload)
    unsupported_tool_issues = [
        issue for issue in validation_issues
        if "introduces analyst tools not named in the JD" in issue or "introduces GTM tools not named in the JD" in issue
    ]
    if unsupported_tool_issues:
        retry_lines = [
            "Previous attempt used named tools in the summary that are not supported by the JD.",
            "Rewrite the summary using JD-grounded tools or generic workflow language.",
            "If the JD does not mention a named tool, do not introduce one in the summary.",
            "Fix these exact issues:",
            *[f"- {issue}" for issue in unsupported_tool_issues],
        ]
        title_summary_payload = run_generation("\n".join(retry_lines))
    return title_summary_payload


def generate_skills_from_analysis(
    *,
    api_key: str,
    analysis_payload: dict,
    revision_context: dict | None = None,
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    prompt_family_key = prompt_family_key_for_analysis(analysis_payload)
    order_key = skill_category_order_key_for_analysis(analysis_payload)
    ordered_categories = skill_category_order_for_key(order_key)
    user_parts = [
        "Analysis:\n" + json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
        f"Skill category order key: {order_key}",
        "Fill these categories in this exact order:",
        json.dumps(ordered_categories, ensure_ascii=False),
    ]
    append_revision_context_to_prompt(user_parts, revision_context)

    def run_generation(extra_instruction: str = "", *, output_token_base: int = 2600) -> dict:
        prompt_parts = list(user_parts)
        if extra_instruction:
            prompt_parts.append(extra_instruction)
        raw_payload = call_openai_structured_output(
            api_key=api_key,
            model=RESUME_MODEL,
            temperature=RESUME_TEMPERATURE,
            developer_prompt=build_ai_resume_skills_prompt(prompt_family_key),
            user_prompt="\n\n".join(prompt_parts),
            schema_name="resume_skills_generation",
            schema=ai_skills_schema(ordered_categories),
            max_output_tokens=with_output_headroom(output_token_base, MEDIUM_OUTPUT_HEADROOM),
            request_timeout_seconds=OPENAI_RESUME_TIMEOUT_SECONDS,
            reasoning_effort="low",
        )
        return normalize_skills_for_order(raw_payload, ordered_categories)

    try:
        skills_payload = run_generation()
    except RuntimeError as exc:
        if not _is_max_output_tokens_error(exc):
            raise
        skills_payload = run_generation(
            "The previous response exhausted its output budget. Return compact schema-valid JSON with 2-5 concise items per included category.",
            output_token_base=4500,
        )
    skill_issues = validate_skills_only_payload(skills_payload, analysis_payload)
    unsupported_tool_issues = [
        issue for issue in skill_issues
        if "introduces analyst tool" in issue or "introduces GTM tool" in issue
    ]
    generic_skill_issues = [
        issue for issue in skill_issues
        if "is too generic; use a named JD tool or related enterprise tool instead" in issue
    ]
    category_skill_issues = [
        issue for issue in skill_issues
        if "belongs under" in issue
    ]
    agentic_data_issues = [
        issue for issue in skill_issues
        if "vector store or embedding store" in issue
    ]
    data_role_issues = [
        issue for issue in skill_issues
        if issue.startswith("Data engineering skills should")
        or issue.startswith("Data science skills should")
        or issue.startswith("Data analyst skills should")
    ]
    retryable_skill_issues = (
        unsupported_tool_issues
        + generic_skill_issues
        + category_skill_issues
        + agentic_data_issues
        + data_role_issues
    )
    if retryable_skill_issues:
        retry_lines = [
            "Previous attempt used unsupported tools, generic skill phrases, or weak category placement.",
            "Replace unsupported vendor names with JD-grounded tools or closely related enterprise tools when the JD clearly supports them.",
            "If the JD does not mention a named tool for Tools & Platforms, use strong generic items only for analyst or GTM roles where vendor names would be invented.",
            "Replace abstract, generic, or process-style skill phrases with concrete named tools, platforms, languages, frameworks, databases, cloud services, or enterprise systems.",
            "Fix category placement issues by moving the item to the right category or replacing it with a concrete tool that fits the current category.",
            "For agentic AI roles, include a concrete vector or memory store in Data & Storage when the JD supports it.",
            "For data engineering roles, include concrete warehouses, databases, and orchestration or transformation tools when the JD supports them.",
            "For data science roles, include concrete ML or statistics tools and model platforms when the JD supports them.",
            "For data analyst roles, include concrete query and BI tools when the JD supports them.",
            "Fix these exact issues:",
            *[f"- {issue}" for issue in retryable_skill_issues],
        ]
        skills_payload = run_generation("\n".join(retry_lines))
    return skills_payload


def review_core_sections(
    *,
    api_key: str,
    analysis_payload: dict,
    title_summary_payload: dict,
    skills_payload: dict,
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    current_core = merge_core_sections(title_summary_payload, skills_payload)
    user_parts = [
        "Analysis:",
        json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
        "Current title and summary:",
        json.dumps(
            {
                "updated_title": current_core.get("updated_title", ""),
                "updated_summary": current_core.get("updated_summary", ""),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "Current skills:",
        json.dumps({"updated_skills": current_core.get("updated_skills", [])}, ensure_ascii=False, separators=(",", ":")),
    ]
    return call_openai_structured_output(
        api_key=api_key,
        model=ANALYSIS_MODEL,
        temperature=ANALYSIS_TEMPERATURE,
        developer_prompt=build_ai_core_review_prompt(),
        user_prompt="\n\n".join(user_parts),
        schema_name="resume_core_review",
        schema=ai_core_review_schema(),
        max_output_tokens=with_output_headroom(1200, SMALL_OUTPUT_HEADROOM),
        request_timeout_seconds=OPENAI_ANALYSIS_TIMEOUT_SECONDS,
        reasoning_effort="low",
    )


def refine_core_sections(
    *,
    api_key: str,
    analysis_payload: dict,
    title_summary_payload: dict,
    skills_payload: dict,
    experience_payload: dict | None = None,
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    current_core = merge_core_sections(title_summary_payload, skills_payload)
    order_key = skill_category_order_key_for_analysis(analysis_payload)
    ordered_categories = skill_category_order_for_key(order_key)
    blueprints = filter_blueprints_by_enabled_keys(
        current_experience_blueprints(),
        (experience_payload or {}).get("_enabled_experience_keys"),
    )
    title_context = []
    experience = (experience_payload or {}).get("experience") or {}
    for blueprint in blueprints:
        entry = experience.get(blueprint["key"]) or {}
        bullets = [str(bullet).strip() for bullet in entry.get("bullets", []) if str(bullet).strip()]
        title_context.append(
            {
                "key": blueprint["key"],
                "company": blueprint["company"],
                "location": blueprint["location"],
                "dates": blueprint["dates"],
                "current_title": str(entry.get("title", "")).strip(),
                "bullets": bullets,
            }
        )
    user_parts = [
        "Analysis:",
        json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
        "Use the role family and skills_mentioned list directly.",
        f"Skill category order key: {order_key}",
        "Fill these categories in this exact order:",
        json.dumps(ordered_categories, ensure_ascii=False),
        "Candidate experience framing: 4+ years. If the summary mentions years of experience at all, use 4+ years and never anything higher.",
        "Current core:",
        json.dumps(current_core, ensure_ascii=False, separators=(",", ":")),
        "Current experience title context:",
        json.dumps(title_context, ensure_ascii=False, separators=(",", ":")),
    ]
    return call_openai_structured_output(
        api_key=api_key,
        model=RESUME_MODEL,
        temperature=RESUME_TEMPERATURE,
        developer_prompt=build_ai_core_correction_prompt(),
        user_prompt="\n\n".join(user_parts),
        schema_name="resume_core_correction",
        schema=ai_core_correction_schema(ordered_categories, blueprints),
        max_output_tokens=with_output_headroom(2600, MEDIUM_OUTPUT_HEADROOM),
        request_timeout_seconds=OPENAI_RESUME_TIMEOUT_SECONDS,
        reasoning_effort="low",
    )


def generate_final_synthesis_from_analysis(
    *,
    api_key: str,
    job_description: str,
    analysis_payload: dict,
    preliminary_skills_payload: dict,
    combined_experience_payload: dict,
    active_blueprints: list[dict],
    revision_context: dict | None = None,
    model: str = SYNTHESIS_MODEL,
    timeout_seconds: int = OPENAI_RESUME_TIMEOUT_SECONDS,
    reasoning_effort: str = SYNTHESIS_REASONING_EFFORT,
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    order_key = skill_category_order_key_for_analysis(analysis_payload)
    ordered_categories = skill_category_order_for_key(order_key)
    preliminary_skills = normalize_skills_for_order(preliminary_skills_payload, ordered_categories)
    experience_by_key = combined_experience_payload.get("experience") or {}
    complete_experience = {
        blueprint["key"]: experience_by_key.get(blueprint["key"], {})
        for blueprint in active_blueprints
    }
    user_parts = [
        f"Raw job description:\n{job_description.strip()}",
        "JD analysis:",
        json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
        "Preliminary skills:",
        json.dumps(preliminary_skills, ensure_ascii=False, separators=(",", ":")),
        f"Skill category order key: {order_key}",
        "Required skill category order:",
        json.dumps(ordered_categories, ensure_ascii=False, separators=(",", ":")),
        "Complete generated experience, including every bullet:",
        json.dumps({"experience": complete_experience}, ensure_ascii=False, separators=(",", ":")),
        "Immutable active experience blueprints and stable role keys:",
        json.dumps(active_blueprints, ensure_ascii=False, separators=(",", ":")),
    ]
    append_revision_context_to_prompt(user_parts, revision_context)
    result = call_openai_structured_output(
        api_key=api_key,
        model=model,
        temperature=RESUME_TEMPERATURE,
        developer_prompt=build_ai_final_synthesis_prompt(),
        user_prompt="\n\n".join(user_parts),
        schema_name="resume_final_synthesis",
        schema=ai_final_synthesis_schema(ordered_categories, active_blueprints),
        max_output_tokens=with_output_headroom(3000, MEDIUM_OUTPUT_HEADROOM),
        request_timeout_seconds=timeout_seconds,
        reasoning_effort=reasoning_effort,
    )
    normalized_skills = normalize_skills_for_order(result, ordered_categories)
    result["updated_title"] = str(result.get("updated_title", "")).strip()
    result["updated_summary"] = str(result.get("updated_summary", "")).strip()
    result["updated_skills"] = normalized_skills["updated_skills"]
    result["experience_titles"] = {
        blueprint["key"]: str((result.get("experience_titles") or {}).get(blueprint["key"], "")).strip()
        for blueprint in active_blueprints
    }
    return result


RESUME_QUALITY_AUDIT_MAX_CHANGE_FRACTION = 1.0
RESUME_QUALITY_AUDIT_SCORE_COMPONENTS = (
    "ats_alignment",
    "technical_credibility",
    "human_tone",
    "career_coherence",
    "evidence_quality",
)


class ResumeQualityAuditError(Exception):
    """Base exception for resume quality audit failures."""


class ResumeQualityAuditValidationError(ResumeQualityAuditError):
    def __init__(self, issues: list[str]):
        self.issues = list(dict.fromkeys(str(issue) for issue in issues if str(issue).strip()))
        super().__init__("; ".join(self.issues) or "Resume quality audit validation failed.")


class ResumeQualityAuditRepairRequiredError(ResumeQualityAuditValidationError):
    def __init__(self, diagnostics: list[dict]):
        self.diagnostics = copy.deepcopy(diagnostics)
        issues = [
            str(item.get("reason", "A required engineering patch is missing.")).strip()
            for item in diagnostics
            if isinstance(item, dict)
        ]
        super().__init__(issues or ["A required engineering patch is missing."])


class ResumeQualityAuditStaleConflictError(ResumeQualityAuditError):
    def __init__(self, expected_base_hash: str, actual_base_hash: str):
        self.expected_base_hash = expected_base_hash
        self.actual_base_hash = actual_base_hash
        super().__init__("The resume changed after the quality audit was generated.")


def _legacy_build_ai_resume_quality_audit_prompt() -> str:
    return "\n".join(
        [
            "Audit the complete tailored resume against the supplied job description and evidence.",
            "Do not role-play reviewers. Apply all four review lenses below and report only measurable, evidence-based findings.",
            "",
            *resume_word_count_prompt_rules(include_experience_bullets=True),
            "ATS AND RESUME QUALITY:",
            "- score coverage of the highest-priority requirements, standard section content, searchable terminology, clarity, and concise phrasing",
            "- flag missing high-priority terms only when the analysis identifies them and the candidate evidence can support them",
            "",
            "TECHNICAL CREDIBILITY:",
            "- verify that tools, architecture claims, scope, chronology, metrics, and role titles are internally consistent and supported",
            "- reject invented metrics, named tools, platforms, vertical experience, or seniority that is not grounded in supplied evidence",
            "",
            "RECRUITER SCREENING:",
            "- assess whether the title, first summary sentences, skills, and recent experience communicate role fit in a fast initial screen",
            "- flag generic filler, keyword stuffing, awkward model-like prose, unclear progression, and claims a recruiter could not verify",
            "",
            "HIRING-MANAGER RELEVANCE:",
            "- assess whether the resume proves the target problems, responsibilities, technical decisions, and outcomes identified in the analysis",
            "- prefer a small, concrete repair over broad rewriting; preserve strong evidence and the candidate's natural voice",
            "",
            "PROPOSAL RULES:",
            "- approved means no repair is needed; proposed_resume must be null and there must be no error finding",
            "- changes_proposed requires a complete proposed_resume with at least one real edit",
            "- blocked means a safe evidence-based repair cannot be produced; proposed_resume must be null",
            "- use stable finding ids and dot paths such as updated_summary or experience.mckinsey.bullets[0]",
            "- every proposed edit must be explained by a finding at that exact path or a parent path",
            "- never return changed paths; the backend computes them",
            "- never edit role keys, companies, locations, dates, blueprint data, or hidden/inactive roles",
            "- return a complete safe proposal even when repairing the unsupported content requires changes across more than 25% of editable units",
            "- broad repair scope alone is never a reason to return blocked",
            "- remove or rephrase every unsupported or fabricated metric, tool, platform, vertical claim, or seniority claim without replacing it with another unsupported claim",
            "- use blocked only when a complete safe repair cannot be produced from the supplied evidence",
            "- return only the audit result matching the schema",
        ]
    )


def _legacy_ai_resume_quality_audit_schema(
    active_blueprints: list[dict],
    allowed_skill_categories: list[str] | None = None,
) -> dict:
    allowed_skill_categories = allowed_skill_categories or sorted(ALLOWED_SKILL_CATEGORIES)
    experience_properties = {
        blueprint["key"]: {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": blueprint["bullet_min"],
                    "maxItems": blueprint["bullet_max"],
                },
            },
            "required": ["title", "bullets"],
        }
        for blueprint in active_blueprints
    }
    proposed_resume_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "updated_title": {"type": "string"},
            "updated_summary": {"type": "string"},
            "updated_skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "category": {"type": "string", "enum": allowed_skill_categories},
                        "items": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                    },
                    "required": ["category", "items"],
                },
                "minItems": min(6, len(allowed_skill_categories)),
            },
            "experience": {
                "type": "object",
                "additionalProperties": False,
                "properties": experience_properties,
                "required": [blueprint["key"] for blueprint in active_blueprints],
            },
        },
        "required": ["updated_title", "updated_summary", "updated_skills", "experience"],
    }
    score_schema = {"type": "integer", "minimum": 0, "maximum": 100}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["approved", "changes_proposed", "blocked"]},
            "overall_score": score_schema,
            "component_scores": {
                "type": "object",
                "additionalProperties": False,
                "properties": {name: score_schema for name in RESUME_QUALITY_AUDIT_SCORE_COMPONENTS},
                "required": list(RESUME_QUALITY_AUDIT_SCORE_COMPONENTS),
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string", "minLength": 1, "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]*$"},
                        "severity": {"type": "string", "enum": ["error", "warning", "info"]},
                        "path": {"type": "string", "minLength": 1},
                        "problem": {"type": "string", "minLength": 1},
                        "recommendation": {"type": "string", "minLength": 1},
                        "repairable": {"type": "boolean"},
                    },
                    "required": ["id", "severity", "path", "problem", "recommendation", "repairable"],
                },
            },
            "proposed_resume": {"anyOf": [{"type": "null"}, proposed_resume_schema]},
        },
        "required": ["decision", "overall_score", "component_scores", "findings", "proposed_resume"],
    }


def canonical_json_hash(payload) -> str:
    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ResumeQualityAuditValidationError([f"Resume payload is not canonical JSON: {exc}"]) from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_editable_resume(resume_payload: dict, active_blueprints: list[dict]) -> dict:
    experience = resume_payload.get("experience") if isinstance(resume_payload, dict) else {}
    experience = experience if isinstance(experience, dict) else {}
    return {
        "updated_title": str((resume_payload or {}).get("updated_title", "")).strip(),
        "updated_summary": str((resume_payload or {}).get("updated_summary", "")).strip(),
        "updated_skills": copy.deepcopy((resume_payload or {}).get("updated_skills", [])),
        "experience": {
            blueprint["key"]: {
                "title": str((experience.get(blueprint["key"]) or {}).get("title", "")).strip(),
                "bullets": copy.deepcopy((experience.get(blueprint["key"]) or {}).get("bullets", [])),
            }
            for blueprint in active_blueprints
        },
    }


def _resume_leaf_values(payload, path: str = "") -> dict[str, object]:
    if isinstance(payload, dict):
        leaves: dict[str, object] = {}
        if not payload and path:
            leaves[path] = {}
        for key in sorted(payload):
            child_path = f"{path}.{key}" if path else str(key)
            leaves.update(_resume_leaf_values(payload[key], child_path))
        return leaves
    if isinstance(payload, list):
        leaves = {}
        if not payload and path:
            leaves[path] = []
        for index, value in enumerate(payload):
            leaves.update(_resume_leaf_values(value, f"{path}[{index}]"))
        return leaves
    return {path: payload}


def compute_resume_changed_paths(
    current_resume: dict,
    proposed_resume: dict,
    active_blueprints: list[dict] | None = None,
) -> list[str]:
    if active_blueprints is not None:
        current_resume = _canonical_editable_resume(current_resume, active_blueprints)
        proposed_resume = _canonical_editable_resume(proposed_resume, active_blueprints)
    current_leaves = _resume_leaf_values(current_resume)
    proposed_leaves = _resume_leaf_values(proposed_resume)
    return sorted(
        path
        for path in set(current_leaves) | set(proposed_leaves)
        if current_leaves.get(path, object()) != proposed_leaves.get(path, object())
    )


def _legacy_resume_quality_audit_review_groups(
    changed_paths: list[str],
    active_blueprints: list[dict] | None = None,
) -> list[str]:
    groups: set[str] = set()
    indexed_skill_groups: set[str] = set()
    indexed_bullet_groups: dict[str, set[str]] = {}
    for raw_path in changed_paths or []:
        path = str(raw_path or "").strip()
        if path in {"updated_title", "updated_summary"}:
            groups.add(path)
            continue
        if path == "updated_skills":
            groups.add("updated_skills")
            continue
        skill_match = re.fullmatch(r"updated_skills\[(\d+)\](?:\..*)?", path)
        if skill_match:
            group = f"updated_skills[{skill_match.group(1)}]"
            groups.add(group)
            indexed_skill_groups.add(group)
            continue
        match = re.fullmatch(
            r"experience\.([^. \[\]]+)\.(title|bullets)(?:\[(\d+)\])?",
            path,
        )
        if match:
            role_key, field, index = match.groups()
            group = (
                f"experience.{role_key}.{field}[{index}]"
                if index is not None
                else f"experience.{role_key}.{field}"
            )
            groups.add(group)
            if field == "bullets" and index is not None:
                indexed_bullet_groups.setdefault(role_key, set()).add(group)
            continue
        raise ValueError(f"Unsupported audit changed path '{path}'.")

    if indexed_skill_groups:
        groups.discard("updated_skills")
    for role_key, indexed_groups in indexed_bullet_groups.items():
        if indexed_groups:
            groups.discard(f"experience.{role_key}.bullets")

    ordered = [
        group
        for group in ("updated_title", "updated_summary")
        if group in groups
    ]
    ordered.extend(sorted(
        (group for group in groups if re.fullmatch(r"updated_skills\[\d+\]", group)),
        key=lambda group: int(re.search(r"\d+", group).group()),
    ))
    if "updated_skills" in groups:
        ordered.append("updated_skills")
    configured_role_keys = [
        str(blueprint.get("key", "")).strip()
        for blueprint in (active_blueprints or [])
        if str(blueprint.get("key", "")).strip()
    ]
    discovered_role_keys = sorted({
        group.split(".")[1]
        for group in groups
        if group.startswith("experience.")
    })
    role_keys = configured_role_keys + [
        key for key in discovered_role_keys if key not in configured_role_keys
    ]
    for role_key in role_keys:
        title_group = f"experience.{role_key}.title"
        if title_group in groups:
            ordered.append(title_group)
        bullet_prefix = f"experience.{role_key}.bullets"
        ordered.extend(sorted(
            (
                group for group in groups
                if re.fullmatch(re.escape(bullet_prefix) + r"\[\d+\]", group)
            ),
            key=lambda group: int(re.search(r"\[(\d+)\]", group).group(1)),
        ))
        if bullet_prefix in groups:
            ordered.append(bullet_prefix)
    return ordered


def _legacy_normalize_resume_quality_audit_decisions(
    decisions,
    review_groups: list[str],
) -> dict[str, str]:
    if not isinstance(decisions, dict):
        raise ValueError("decisions must be an object mapping every review group to accept or reject.")
    expected = set(review_groups)
    supplied = set(decisions)
    missing = sorted(expected - supplied)
    unknown = sorted(supplied - expected)
    issues: list[str] = []
    if missing:
        issues.append("Missing review decisions: " + ", ".join(missing) + ".")
    if unknown:
        issues.append("Unknown review decisions: " + ", ".join(unknown) + ".")
    normalized: dict[str, str] = {}
    for group in review_groups:
        decision = str(decisions.get(group, "")).strip().lower()
        if decision not in {"accept", "reject"}:
            issues.append(f"Decision for '{group}' must be accept or reject.")
        else:
            normalized[group] = decision
    if issues:
        raise ValueError(" ".join(issues))
    return normalized


def _path_parts(path: str) -> tuple[str, ...]:
    normalized = str(path or "").strip().strip("/")
    if not normalized:
        return ()
    normalized = normalized.replace("/", ".")
    normalized = re.sub(r"\[(\d+)\]", r".\1", normalized)
    return tuple(part for part in normalized.split(".") if part)


def _finding_covers_path(finding_path: str, changed_path: str) -> bool:
    finding_parts = _path_parts(finding_path)
    changed_parts = _path_parts(changed_path)
    return bool(finding_parts) and changed_parts[:len(finding_parts)] == finding_parts


def _normalize_resume_quality_proposal(proposal: dict, active_blueprints: list[dict], ordered_categories: list[str]) -> dict:
    experience = proposal.get("experience") or {}
    normalized_skills = normalize_skills_for_order(proposal, ordered_categories)["updated_skills"]
    return {
        "updated_title": str(proposal.get("updated_title", "")).strip(),
        "updated_summary": str(proposal.get("updated_summary", "")).strip(),
        "updated_skills": normalized_skills,
        "experience": {
            blueprint["key"]: {
                "title": str((experience.get(blueprint["key"]) or {}).get("title", "")).strip(),
                "bullets": [
                    str(bullet).strip()
                    for bullet in ((experience.get(blueprint["key"]) or {}).get("bullets") or [])
                ],
            }
            for blueprint in active_blueprints
        },
    }


def _validate_quality_audit_structure(audit_result: dict, active_blueprints: list[dict]) -> list[str]:
    issues: list[str] = []
    if not isinstance(audit_result, dict):
        return ["Audit result must be an object."]
    allowed_result_keys = {
        "decision",
        "overall_score",
        "component_scores",
        "findings",
        "proposed_resume",
        "base_hash",
        "changed_paths",
        "change_fraction",
    }
    extra_result_keys = set(audit_result) - allowed_result_keys
    if extra_result_keys:
        issues.append("Audit result contains unsupported fields: " + ", ".join(sorted(extra_result_keys)) + ".")

    decision = audit_result.get("decision")
    if decision not in {"approved", "changes_proposed", "blocked"}:
        issues.append("Audit decision must be approved, changes_proposed, or blocked.")
    for label, score in [("overall_score", audit_result.get("overall_score"))]:
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
            issues.append(f"{label} must be an integer from 0 to 100.")
    component_scores = audit_result.get("component_scores")
    if not isinstance(component_scores, dict) or set(component_scores) != set(RESUME_QUALITY_AUDIT_SCORE_COMPONENTS):
        issues.append("component_scores must contain exactly the five required score components.")
    else:
        for name in RESUME_QUALITY_AUDIT_SCORE_COMPONENTS:
            score = component_scores.get(name)
            if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
                issues.append(f"component_scores.{name} must be an integer from 0 to 100.")

    findings = audit_result.get("findings")
    if not isinstance(findings, list):
        issues.append("findings must be an array.")
        findings = []
    finding_ids: set[str] = set()
    required_finding_keys = {"id", "severity", "path", "problem", "recommendation", "repairable"}
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict) or set(finding) != required_finding_keys:
            issues.append(f"Finding {index} must contain exactly the required fields.")
            continue
        finding_id = str(finding.get("id", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", finding_id):
            issues.append(f"Finding {index} has an invalid stable id.")
        elif finding_id in finding_ids:
            issues.append(f"Finding id '{finding_id}' is duplicated.")
        finding_ids.add(finding_id)
        if finding.get("severity") not in {"error", "warning", "info"}:
            issues.append(f"Finding {index} has an invalid severity.")
        if not str(finding.get("path", "")).strip():
            issues.append(f"Finding {index} is missing a path.")
        if not str(finding.get("problem", "")).strip():
            issues.append(f"Finding {index} is missing a problem.")
        if not str(finding.get("recommendation", "")).strip():
            issues.append(f"Finding {index} is missing a recommendation.")
        if not isinstance(finding.get("repairable"), bool):
            issues.append(f"Finding {index} repairable must be boolean.")

    proposal = audit_result.get("proposed_resume")
    if proposal is None:
        return issues
    if not isinstance(proposal, dict):
        issues.append("proposed_resume must be null or an object.")
        return issues
    required_resume_keys = {"updated_title", "updated_summary", "updated_skills", "experience"}
    if set(proposal) != required_resume_keys:
        issues.append("proposed_resume must contain exactly the editable resume fields.")
    if not isinstance(proposal.get("updated_skills"), list):
        issues.append("proposed_resume.updated_skills must be an array.")
    else:
        for index, entry in enumerate(proposal["updated_skills"]):
            if not isinstance(entry, dict) or set(entry) != {"category", "items"}:
                issues.append(f"proposed_resume.updated_skills[{index}] contains unsupported fields.")
            elif not isinstance(entry.get("items"), list) or not all(isinstance(item, str) for item in entry["items"]):
                issues.append(f"proposed_resume.updated_skills[{index}].items must contain only strings.")
    experience = proposal.get("experience")
    active_keys = [blueprint["key"] for blueprint in active_blueprints]
    if not isinstance(experience, dict) or set(experience) != set(active_keys):
        issues.append("proposed_resume.experience must contain exactly the active stable role keys.")
    else:
        for role_key in active_keys:
            entry = experience.get(role_key)
            if not isinstance(entry, dict) or set(entry) != {"title", "bullets"}:
                issues.append(f"proposed_resume.experience.{role_key} may contain only title and bullets.")
            elif not isinstance(entry.get("bullets"), list) or not all(isinstance(bullet, str) for bullet in entry["bullets"]):
                issues.append(f"proposed_resume.experience.{role_key}.bullets must contain only strings.")
    return issues


_AUDIT_NUMERIC_TOKEN_RE = re.compile(
    r"(?<![\w])(?:[$€£]\s*)?\d[\d,]*(?:\.\d+)?(?:\s*(?:%|percent(?:age)?s?|[xX]|\+))?",
    flags=re.IGNORECASE,
)

_AUDIT_METRIC_UNIT_RE = re.compile(
    r"^\s*(?:"
    r"milliseconds?|msecs?|ms|seconds?|secs?|minutes?|mins?|hours?|days?|weeks?|months?|years?|"
    r"bytes?|kb|mb|gb|tb|kib|mib|gib|tib|"
    r"users?|customers?|clients?|accounts?|requests?|queries?|transactions?|events?|records?|rows?|"
    r"documents?|files?|messages?|calls?|jobs?|tasks?|workflows?|pipelines?|services?|apis?|endpoints?|"
    r"deployments?|releases?|incidents?|defects?|bugs?|tickets?|teams?|regions?|markets?|portfolios?|"
    r"applications?|systems?|nodes?|containers?|instances?|models?|experiments?|tests?"
    r")\b",
    flags=re.IGNORECASE,
)

_AUDIT_METRIC_RELATION_RE = re.compile(
    r"(?:"
    r"reduc(?:e|ed|ing)|decreas(?:e|ed|ing)|increas(?:e|ed|ing)|improv(?:e|ed|ing)|"
    r"cut|lower(?:ed|ing)?|rais(?:e|ed|ing)|boost(?:ed|ing)?|grew|grow(?:n|ing)?|"
    r"sav(?:e|ed|ing)|achiev(?:e|ed|ing)|maintain(?:ed|ing)?|reach(?:ed|ing)?|"
    r"eliminat(?:e|ed|ing)|accelerat(?:e|ed|ing)|latency|throughput|accuracy|"
    r"availability|uptime|reliability|conversion|adoption|coverage|cost|revenue|volume|rate|time"
    r")\b.{0,48}\b(?:by|to|from|at|under|over|within|of)\s*$",
    flags=re.IGNORECASE,
)


def _numeric_text_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _numeric_text_values(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _numeric_text_values(item)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield str(value)


def _numeric_match_is_metric(text: str, match: re.Match) -> bool:
    raw = match.group(0)
    before = text[max(0, match.start() - 96):match.start()]
    after = text[match.end():match.end() + 48]
    if re.search(r"[$€£]|%|percent(?:age)?s?|\d\s*[xX+]\s*$", raw, flags=re.IGNORECASE):
        return True
    if _AUDIT_METRIC_UNIT_RE.search(after):
        return True
    return bool(_AUDIT_METRIC_RELATION_RE.search(before))


def _numeric_tokens(value) -> set[str]:
    tokens: set[str] = set()
    for text_value in _numeric_text_values(value):
        for match in _AUDIT_NUMERIC_TOKEN_RE.finditer(text_value):
            if not _numeric_match_is_metric(text_value, match):
                continue
            token = re.sub(r"\s+", "", match.group(0).lower()).replace(",", "")
            token = re.sub(r"percent(?:age)?s?", "%", token)
            tokens.add(token)
    return tokens


def _text_evidence_blob(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()


def _candidate_quality_audit_evidence(
    current_resume: dict,
    active_blueprints: list[dict],
) -> dict:
    return {
        "current_resume": current_resume,
        "experience_blueprints": [
            {
                "key": blueprint.get("key"),
                "anchor": blueprint.get("anchor", ""),
                "default_title": blueprint.get("default_title", ""),
            }
            for blueprint in active_blueprints
        ],
    }


def _new_skill_grounding_issues(
    current_resume: dict,
    proposal: dict,
    active_blueprints: list[dict],
) -> list[str]:
    candidate_blob = normalize_skill_dedupe_key(_text_evidence_blob(
        _candidate_quality_audit_evidence(current_resume, active_blueprints)
    ))
    current_items = {
        normalize_skill_dedupe_key(item)
        for entry in normalize_updated_skills(current_resume.get("updated_skills") or [])
        for item in expand_skill_items(entry.get("items", []))
    }
    issues: list[str] = []
    for entry in normalize_updated_skills(proposal.get("updated_skills") or []):
        for item in expand_skill_items(entry.get("items", [])):
            normalized_item = normalize_skill_dedupe_key(item)
            if normalized_item in current_items:
                continue
            if normalized_item and normalized_item in candidate_blob:
                continue
            item_terms = [term for term in normalized_item.split() if len(term) >= 3]
            if item_terms and all(term in candidate_blob for term in item_terms):
                continue
            issues.append(
                f"New skill '{item}' is not grounded in the current resume or active experience evidence."
            )
    return issues


def _new_named_claim_issues(
    current_resume: dict,
    proposal: dict,
    analysis_payload: dict,
    active_blueprints: list[dict],
    changed_paths: list[str],
) -> list[str]:
    candidate_evidence = _candidate_quality_audit_evidence(current_resume, active_blueprints)
    candidate_blob = _text_evidence_blob(candidate_evidence)
    normalized_candidate_blob = normalize_skill_dedupe_key(candidate_blob)
    proposed_leaves = _resume_leaf_values(proposal)
    issues: list[str] = []
    reported_named_claims: set[tuple[str, str]] = set()

    def add_issue(message: str) -> None:
        if message not in issues:
            issues.append(message)

    def add_named_issue(path: str, claim: str) -> None:
        normalized_claim = normalize_skill_dedupe_key(claim)
        claim_key = (path, normalized_claim)
        if normalized_claim and claim_key not in reported_named_claims:
            reported_named_claims.add(claim_key)
            add_issue(f"{path} introduces unsupported named tool or technical claim '{claim}'.")

    def normalized_phrase_present(normalized_text: str, normalized_phrase: str) -> bool:
        if not normalized_text or not normalized_phrase:
            return False
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])",
                normalized_text,
                flags=re.IGNORECASE,
            )
        )

    for path in changed_paths:
        value = proposed_leaves.get(path)
        if not isinstance(value, str):
            continue
        normalized_value = normalize_skill_dedupe_key(value)
        for token_match in re.finditer(r"\b[A-Za-z][A-Za-z0-9+#.-]*\b", value):
            token = token_match.group(0)
            preceding_text = value[:token_match.start()].rstrip()
            starts_sentence = not preceding_text or preceding_text[-1:] in ".!?"
            technical_shape = (
                (any(character.isupper() for character in token[1:]) and any(character.islower() for character in token))
                or (token.isupper() and len(token) > 1)
                or any(character in token for character in "+#")
                or (
                    not starts_sentence
                    and len(token) >= 3
                    and token[0].isupper()
                    and token[1:].islower()
                )
            )
            normalized_token = token.lower()
            if technical_shape and normalized_token not in candidate_blob:
                add_named_issue(path, token)

        for technology_term in sorted(AUDIT_KNOWN_NAMED_TECHNOLOGY_TERMS, key=lambda term: (-len(term), term)):
            if normalized_phrase_present(normalized_candidate_blob, technology_term):
                continue
            if normalized_phrase_present(normalized_value, technology_term):
                add_named_issue(path, technology_term)

    target_skill_terms = {
        normalize_skill_dedupe_key(term)
        for term in analysis_payload.get("skills_mentioned") or []
        if normalize_skill_dedupe_key(term)
    }
    for target_term in sorted(target_skill_terms):
        if target_term in normalized_candidate_blob:
            continue
        target_pattern = re.compile(rf"(?<![\w]){re.escape(target_term)}(?![\w])", flags=re.IGNORECASE)
        for path in changed_paths:
            value = proposed_leaves.get(path)
            if isinstance(value, str) and target_pattern.search(normalize_skill_dedupe_key(value)):
                add_named_issue(path, target_term)

    domain_terms = [
        str(term).strip().lower()
        for term in (
            list(analysis_payload.get("domain_terms") or [])
            + [analysis_payload.get("company_domain", "")]
        )
        if str(term).strip()
    ]
    for domain_term in domain_terms:
        if domain_term in candidate_blob:
            continue
        for path in changed_paths:
            value = proposed_leaves.get(path)
            if isinstance(value, str) and domain_term in value.lower():
                add_issue(f"{path} introduces unsupported vertical claim '{domain_term}'.")
    return issues


def _legacy_validate_resume_quality_audit_result(
    audit_result: dict,
    *,
    current_resume: dict,
    analysis_payload: dict,
    active_blueprints: list[dict],
    max_change_fraction: float = RESUME_QUALITY_AUDIT_MAX_CHANGE_FRACTION,
) -> dict:
    issues = _validate_quality_audit_structure(audit_result, active_blueprints)
    if issues:
        raise ResumeQualityAuditValidationError(issues)

    decision = audit_result["decision"]
    findings = audit_result["findings"]
    proposal = audit_result.get("proposed_resume")
    if decision == "approved":
        if proposal is not None:
            issues.append("approved requires proposed_resume to be null.")
        if any(finding.get("severity") == "error" for finding in findings):
            issues.append("approved cannot contain error findings.")
    elif decision == "changes_proposed" and proposal is None:
        issues.append("changes_proposed requires a proposed_resume.")
    elif decision == "blocked" and proposal is not None:
        issues.append("blocked requires proposed_resume to be null.")

    normalized_proposal = None
    changed_paths: list[str] = []
    change_fraction = 0.0
    if proposal is not None:
        order_key = skill_category_order_key_for_analysis(analysis_payload)
        ordered_categories = skill_category_order_for_key(order_key)
        raw_categories = [str(entry.get("category", "")).strip() for entry in proposal.get("updated_skills", [])]
        expected_categories = [category for category in ordered_categories if category in raw_categories]
        if raw_categories != expected_categories:
            issues.append("proposed_resume.updated_skills must use the required category order without duplicates.")

        normalized_proposal = _normalize_resume_quality_proposal(proposal, active_blueprints, ordered_categories)
        issues.extend(validate_core_payload(normalized_proposal, analysis_payload))
        issues.extend(validate_skills_only_payload(normalized_proposal, analysis_payload))
        issues.extend(validate_experience_subset_payload_with_analysis(normalized_proposal, active_blueprints, analysis_payload))
        issues.extend(
            validate_experience_title_review_payload(
                {
                    "experience_titles": {
                        role_key: entry.get("title", "")
                        for role_key, entry in normalized_proposal["experience"].items()
                    }
                },
                active_blueprints,
                analysis_payload,
            )
        )

        current_editable = _canonical_editable_resume(current_resume, active_blueprints)
        changed_paths = compute_resume_changed_paths(current_editable, normalized_proposal)
        if decision == "changes_proposed" and not changed_paths:
            issues.append("changes_proposed requires at least one actual change.")
        if decision != "changes_proposed" and changed_paths:
            issues.append(f"{decision} cannot include an applicable changed proposal.")

        uncovered_paths = [
            path
            for path in changed_paths
            if not any(_finding_covers_path(finding.get("path", ""), path) for finding in findings)
        ]
        if uncovered_paths:
            issues.append("Findings do not explain changed paths: " + ", ".join(uncovered_paths) + ".")

        current_unit_count = len(_resume_leaf_values(current_editable))
        proposed_unit_count = len(_resume_leaf_values(normalized_proposal))
        editable_unit_count = max(current_unit_count, proposed_unit_count, 1)
        change_fraction = len(changed_paths) / editable_unit_count
        if change_fraction > max_change_fraction:
            issues.append(
                f"Proposal changes {len(changed_paths)} of {editable_unit_count} editable units "
                f"({change_fraction:.1%}), exceeding the {max_change_fraction:.0%} limit."
            )

        candidate_evidence = _candidate_quality_audit_evidence(current_editable, active_blueprints)
        grounded_numeric_tokens = _numeric_tokens(candidate_evidence)
        proposed_leaves = _resume_leaf_values(normalized_proposal)
        for path in changed_paths:
            value = proposed_leaves.get(path)
            if not isinstance(value, str):
                continue
            unsupported_tokens = sorted(_numeric_tokens(value) - grounded_numeric_tokens)
            if unsupported_tokens:
                issues.append(f"{path} introduces unsupported numeric metrics: {', '.join(unsupported_tokens)}.")

        issues.extend(_new_skill_grounding_issues(current_editable, normalized_proposal, active_blueprints))
        issues.extend(
            _new_named_claim_issues(
                current_editable,
                normalized_proposal,
                analysis_payload,
                active_blueprints,
                changed_paths,
            )
        )

    if issues:
        raise ResumeQualityAuditValidationError(issues)

    normalized_findings = [
        {
            "id": str(finding["id"]).strip(),
            "severity": finding["severity"],
            "path": str(finding["path"]).strip(),
            "problem": str(finding["problem"]).strip(),
            "recommendation": str(finding["recommendation"]).strip(),
            "repairable": finding["repairable"],
        }
        for finding in findings
    ]
    return {
        "decision": decision,
        "overall_score": audit_result["overall_score"],
        "component_scores": {
            name: audit_result["component_scores"][name]
            for name in RESUME_QUALITY_AUDIT_SCORE_COMPONENTS
        },
        "findings": normalized_findings,
        "proposed_resume": normalized_proposal,
        "base_hash": canonical_json_hash(current_resume),
        "changed_paths": changed_paths,
        "change_fraction": change_fraction,
    }


def _legacy_generate_resume_quality_audit(
    *,
    api_key: str,
    job_description: str,
    analysis_payload: dict,
    current_resume: dict,
    active_blueprints: list[dict],
    model: str = AUDIT_MODEL,
    timeout_seconds: int = OPENAI_RESUME_TIMEOUT_SECONDS,
    reasoning_effort: str = AUDIT_REASONING_EFFORT,
    max_change_fraction: float = RESUME_QUALITY_AUDIT_MAX_CHANGE_FRACTION,
) -> dict:
    order_key = skill_category_order_key_for_analysis(analysis_payload)
    ordered_categories = skill_category_order_for_key(order_key)
    user_parts = [
        f"Raw job description:\n{job_description.strip()}",
        "JD analysis and grounded profile evidence:",
        json.dumps(compact_analysis_for_generation(analysis_payload), ensure_ascii=False, separators=(",", ":")),
        "Canonical current structured resume:",
        json.dumps(current_resume, ensure_ascii=False, separators=(",", ":")),
        "Immutable active experience blueprints and stable role keys:",
        json.dumps(active_blueprints, ensure_ascii=False, separators=(",", ":")),
        "Required skill category order:",
        json.dumps(ordered_categories, ensure_ascii=False, separators=(",", ":")),
    ]
    result = call_openai_structured_output(
        api_key=api_key,
        model=model,
        temperature=RESUME_TEMPERATURE,
        developer_prompt=build_ai_resume_quality_audit_prompt(),
        user_prompt="\n\n".join(user_parts),
        schema_name="resume_quality_audit",
        schema=ai_resume_quality_audit_schema(active_blueprints, ordered_categories),
        max_output_tokens=with_output_headroom(4200, MEDIUM_OUTPUT_HEADROOM),
        request_timeout_seconds=timeout_seconds,
        reasoning_effort=reasoning_effort,
    )
    return validate_resume_quality_audit_result(
        result,
        current_resume=current_resume,
        analysis_payload=analysis_payload,
        active_blueprints=active_blueprints,
        max_change_fraction=max_change_fraction,
    )


def _legacy_apply_resume_quality_audit_proposal(
    *,
    expected_base_hash: str,
    current_resume: dict,
    audit_result: dict,
    analysis_payload: dict,
    active_blueprints: list[dict],
    max_change_fraction: float = RESUME_QUALITY_AUDIT_MAX_CHANGE_FRACTION,
) -> dict:
    actual_base_hash = canonical_json_hash(current_resume)
    if not expected_base_hash or expected_base_hash != actual_base_hash:
        raise ResumeQualityAuditStaleConflictError(expected_base_hash, actual_base_hash)
    validated = validate_resume_quality_audit_result(
        audit_result,
        current_resume=current_resume,
        analysis_payload=analysis_payload,
        active_blueprints=active_blueprints,
        max_change_fraction=max_change_fraction,
    )
    if validated["decision"] != "changes_proposed" or validated["proposed_resume"] is None:
        raise ResumeQualityAuditValidationError(["Audit result has no applicable proposal."])
    return copy.deepcopy(validated["proposed_resume"])


apply_resume_quality_proposal = _legacy_apply_resume_quality_audit_proposal


def _legacy_resolve_resume_quality_audit_decisions(
    *,
    expected_base_hash: str,
    current_resume: dict,
    audit_result: dict,
    decisions,
    analysis_payload: dict,
    active_blueprints: list[dict],
    max_change_fraction: float = RESUME_QUALITY_AUDIT_MAX_CHANGE_FRACTION,
) -> tuple[dict, list[str], bool]:
    full_proposal = apply_resume_quality_audit_proposal(
        expected_base_hash=expected_base_hash,
        current_resume=current_resume,
        audit_result=audit_result,
        analysis_payload=analysis_payload,
        active_blueprints=active_blueprints,
        max_change_fraction=max_change_fraction,
    )
    current_editable = _canonical_editable_resume(current_resume, active_blueprints)
    changed_paths = compute_resume_changed_paths(current_editable, full_proposal)
    review_groups = resume_quality_audit_review_groups(changed_paths, active_blueprints)
    normalized_decisions = normalize_resume_quality_audit_decisions(decisions, review_groups)
    all_rejected = all(decision == "reject" for decision in normalized_decisions.values())
    if all_rejected:
        return copy.deepcopy(current_editable), review_groups, True

    missing = object()

    def resolve_indexed_list(
        current_items: list,
        proposed_items: list,
        group_prefix: str,
    ) -> list:
        selected: list = []
        for index in range(max(len(current_items), len(proposed_items))):
            current_item = current_items[index] if index < len(current_items) else missing
            proposed_item = proposed_items[index] if index < len(proposed_items) else missing
            group = f"{group_prefix}[{index}]"
            decision = normalized_decisions.get(group)
            if decision == "accept":
                item = proposed_item
            elif decision == "reject":
                item = current_item
            elif current_item == proposed_item:
                item = current_item
            else:
                raise ValueError(f"Missing indexed review decision for '{group}'.")
            if item is not missing:
                selected.append(copy.deepcopy(item))
        return selected

    resolved = copy.deepcopy(current_editable)
    for group, decision in normalized_decisions.items():
        if decision != "accept":
            continue
        if group in {"updated_title", "updated_summary"}:
            resolved[group] = copy.deepcopy(full_proposal[group])
            continue
        if group == "updated_skills":
            resolved["updated_skills"] = copy.deepcopy(full_proposal["updated_skills"])
            continue
        if group.startswith("updated_skills["):
            continue
        match = re.fullmatch(r"experience\.([^.]+)\.(title|bullets)(?:\[(\d+)\])?", group)
        if not match:
            raise ValueError(f"Unsupported audit review group '{group}'.")
        role_key, field, index = match.groups()
        if field == "title":
            resolved["experience"][role_key]["title"] = copy.deepcopy(
                full_proposal["experience"][role_key]["title"]
            )
        elif index is None:
            resolved["experience"][role_key]["bullets"] = copy.deepcopy(
                full_proposal["experience"][role_key]["bullets"]
            )

    if any(group.startswith("updated_skills[") for group in normalized_decisions):
        resolved["updated_skills"] = resolve_indexed_list(
            current_editable["updated_skills"],
            full_proposal["updated_skills"],
            "updated_skills",
        )
    for role_key in current_editable["experience"]:
        bullet_prefix = f"experience.{role_key}.bullets"
        if any(group.startswith(f"{bullet_prefix}[") for group in normalized_decisions):
            resolved["experience"][role_key]["bullets"] = resolve_indexed_list(
                current_editable["experience"][role_key]["bullets"],
                full_proposal["experience"][role_key]["bullets"],
                bullet_prefix,
            )

    mixed_result = {
        key: copy.deepcopy(value)
        for key, value in audit_result.items()
        if key in {
            "decision", "overall_score", "component_scores", "findings",
            "proposed_resume", "base_hash", "changed_paths", "change_fraction",
        }
    }
    mixed_result["decision"] = "changes_proposed"
    mixed_result["proposed_resume"] = resolved
    validated = validate_resume_quality_audit_result(
        mixed_result,
        current_resume=current_editable,
        analysis_payload=analysis_payload,
        active_blueprints=active_blueprints,
        max_change_fraction=max_change_fraction,
    )
    return copy.deepcopy(validated["proposed_resume"]), review_groups, False


# Quality audit schema v2 returns reviewable patches instead of repeating the
# entire resume. These definitions intentionally replace the legacy v1 helpers
# above while keeping their public function names stable for API callers.
RESUME_QUALITY_AUDIT_SCHEMA_VERSION = "2"
RESUME_QUALITY_AUDIT_MAX_OUTPUT_TOKENS = 8000
RESUME_QUALITY_AUDIT_RETRY_MAX_OUTPUT_TOKENS = 12000


def _audit_text_schema(*, nullable: bool = False) -> dict:
    text_schema = {"type": "string", "minLength": 1}
    return {"anyOf": [{"type": "null"}, text_schema]} if nullable else text_schema


def _audit_evidence_refs_schema() -> dict:
    return {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
        "minItems": 1,
    }


def _audit_change_common_properties() -> dict:
    return {
        "change_id": {
            "type": "string",
            "minLength": 1,
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        },
        "reason": {"type": "string", "minLength": 1},
        "supported_by": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["technical_recruiter", "hiring_manager", "principal_engineer"],
            },
            "minItems": 1,
        },
    }


def _empty_resume_quality_audit_changes() -> dict:
    return {
        "top_title": None,
        "summary": None,
        "experience_titles": [],
        "skills": {
            "category_removals": [],
            "category_additions": [],
            "skill_removals": [],
            "skill_additions": [],
            "category_order": None,
        },
        "experience": [],
    }


def ai_resume_quality_audit_schema(
    active_blueprints: list[dict],
    allowed_skill_categories: list[str] | None = None,
) -> dict:
    allowed_categories = allowed_skill_categories or sorted(ALLOWED_SKILL_CATEGORIES)
    active_keys = [str(blueprint["key"]) for blueprint in active_blueprints]
    common = _audit_change_common_properties()
    evidence_refs = _audit_evidence_refs_schema()
    replacement_change = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **common,
            "suggested": {"type": "string", "minLength": 1},
            "evidence_refs": evidence_refs,
        },
        "required": ["change_id", "suggested", "reason", "supported_by", "evidence_refs"],
    }
    skill_removal = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **common,
            "category": {"type": "string", "enum": allowed_categories},
            "skill": {"type": "string", "minLength": 1},
        },
        "required": ["change_id", "category", "skill", "reason", "supported_by"],
    }
    skill_addition = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **common,
            "category": {"type": "string", "enum": allowed_categories},
            "skill": {"type": "string", "minLength": 1},
            "evidence_refs": evidence_refs,
        },
        "required": [
            "change_id", "category", "skill", "reason", "supported_by",
            "evidence_refs",
        ],
    }
    category_removal = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **common,
            "category": {"type": "string", "enum": allowed_categories},
        },
        "required": ["change_id", "category", "reason", "supported_by"],
    }
    category_addition = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **common,
            "category": {"type": "string", "enum": allowed_categories},
            "skills": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 2,
            },
            "insert_after_category": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "enum": allowed_categories},
                ]
            },
            "evidence_refs": evidence_refs,
        },
        "required": [
            "change_id", "category", "skills", "insert_after_category",
            "reason", "supported_by", "evidence_refs",
        ],
    }
    category_order = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **common,
            "suggested": {
                "type": "array",
                "items": {"type": "string", "enum": allowed_categories},
                "minItems": 1,
            },
        },
        "required": ["change_id", "suggested", "reason", "supported_by"],
    }
    experience_title = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **common,
            "role_key": {"type": "string", "enum": active_keys},
            "suggested": {"type": "string", "minLength": 1},
            "evidence_refs": evidence_refs,
        },
        "required": [
            "change_id", "role_key", "suggested", "reason", "supported_by",
            "evidence_refs",
        ],
    }
    bullet_group = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **common,
            "removals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "bullet_number": {"type": "integer", "minimum": 1},
                    },
                    "required": ["bullet_number"],
                },
            },
            "additions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "new_position": {"type": "integer", "minimum": 1},
                        "new_bullet": {"type": "string", "minLength": 1},
                        "replaces_bullet_numbers": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1},
                        },
                        "evidence_refs": evidence_refs,
                    },
                    "required": [
                        "new_position", "new_bullet",
                        "replaces_bullet_numbers", "evidence_refs",
                    ],
                },
            },
        },
        "required": [
            "change_id", "reason", "supported_by", "removals", "additions",
        ],
    }
    experience_change = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "role_key": {"type": "string", "enum": active_keys},
            "company": {"type": "string", "minLength": 1},
            "current_bullet_count": {"type": "integer", "minimum": 0},
            "proposed_bullet_count": {"type": "integer", "minimum": 0},
            "reason": {"type": "string", "minLength": 1},
            "change_groups": {
                "type": "array",
                "items": bullet_group,
                "minItems": 1,
            },
        },
        "required": [
            "role_key", "company", "current_bullet_count",
            "proposed_bullet_count", "reason", "change_groups",
        ],
    }
    manual_finding = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {
                "type": "string",
                "minLength": 1,
                "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
            },
            "severity": {"type": "string", "enum": ["error", "warning", "info"]},
            "path": {"type": "string", "minLength": 1},
            "problem": {"type": "string", "minLength": 1},
            "recommendation": {"type": "string", "minLength": 1},
            "evidence_refs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
        },
        "required": [
            "id", "severity", "path", "problem",
            "recommendation", "evidence_refs",
        ],
    }
    score_schema = {"type": "integer", "minimum": 0, "maximum": 100}
    reviewer_priorities = {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
        "minItems": 1,
        "maxItems": 5,
    }
    review_basis = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "advertised_job_title": _audit_text_schema(nullable=True),
            "normalized_market_title": {"type": "string", "minLength": 1},
            "top_title_assessment": {
                "type": "string",
                "enum": ["aligned", "change_recommended"],
            },
            "experience_title_assessment": {
                "type": "string",
                "enum": ["coherent", "change_recommended"],
            },
            "title_rationale": {"type": "string", "minLength": 1},
            "technical_recruiter_priorities": reviewer_priorities,
            "hiring_manager_priorities": reviewer_priorities,
            "principal_engineer_priorities": reviewer_priorities,
        },
        "required": [
            "advertised_job_title", "normalized_market_title",
            "top_title_assessment", "experience_title_assessment",
            "title_rationale",
            "technical_recruiter_priorities", "hiring_manager_priorities",
            "principal_engineer_priorities",
        ],
    }
    non_blocking_gap = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {
                "type": "string",
                "minLength": 1,
                "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
            },
            "path": {"type": "string", "minLength": 1},
            "kind": {
                "type": "string",
                "enum": [
                    "unsupported_engineering",
                    "named_technology",
                    "domain_context",
                    "application_condition",
                    "credential_or_duration",
                    "withheld_patch",
                ],
            },
            "gap": {"type": "string", "minLength": 1},
            "impact": {"type": "string", "minLength": 1},
            "evidence_refs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
        },
        "required": ["id", "path", "kind", "gap", "impact", "evidence_refs"],
    }
    requirement_resolution = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "requirement_id": {
                "type": "string",
                "minLength": 1,
                "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
            },
            "requirement": {"type": "string", "minLength": 1},
            "priority": {
                "type": "string",
                "enum": ["critical", "important", "secondary"],
            },
            "claim_type": {
                "type": "string",
                "enum": [
                    "engineering_capability",
                    "named_technology",
                    "domain_context",
                    "application_condition",
                    "credential_or_duration",
                ],
            },
            "evidence_fit": {
                "type": "string",
                "enum": ["direct", "transferable", "none"],
            },
            "resume_action": {
                "type": "string",
                "enum": ["already_covered", "patch_required", "gap_only"],
            },
            "status": {
                "type": "string",
                "enum": [
                    "already_covered",
                    "patched_direct",
                    "patched_transferable",
                    "unresolved",
                ],
            },
            "evidence_refs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "change_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
                },
            },
            "reason": {"type": "string", "minLength": 1},
        },
        "required": [
            "requirement_id", "requirement", "priority", "claim_type",
            "evidence_fit", "resume_action", "status", "evidence_refs",
            "change_ids", "reason",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string", "enum": [RESUME_QUALITY_AUDIT_SCHEMA_VERSION]},
            "decision": {
                "type": "string",
                "enum": ["approved", "changes_suggested", "manual_attention"],
            },
            "overall_score": score_schema,
            "review_summary": {"type": "string", "minLength": 1},
            "review_basis": review_basis,
            "component_scores": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    name: score_schema
                    for name in RESUME_QUALITY_AUDIT_SCORE_COMPONENTS
                },
                "required": list(RESUME_QUALITY_AUDIT_SCORE_COMPONENTS),
            },
            "manual_findings": {
                "type": "array",
                "items": manual_finding,
                "maxItems": 12,
            },
            "non_blocking_gaps": {
                "type": "array",
                "items": non_blocking_gap,
                "maxItems": 10,
            },
            "requirement_resolutions": {
                "type": "array",
                "items": requirement_resolution,
                "minItems": 1,
                "maxItems": 12,
            },
            "changes": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "top_title": {"anyOf": [{"type": "null"}, replacement_change]},
                    "summary": {"anyOf": [{"type": "null"}, replacement_change]},
                    "experience_titles": {
                        "type": "array",
                        "items": experience_title,
                    },
                    "skills": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "category_removals": {
                                "type": "array",
                                "items": category_removal,
                            },
                            "category_additions": {
                                "type": "array",
                                "items": category_addition,
                            },
                            "skill_removals": {
                                "type": "array",
                                "items": skill_removal,
                            },
                            "skill_additions": {
                                "type": "array",
                                "items": skill_addition,
                            },
                            "category_order": {
                                "anyOf": [{"type": "null"}, category_order]
                            },
                        },
                        "required": [
                            "category_removals", "category_additions",
                            "skill_removals", "skill_additions",
                            "category_order",
                        ],
                    },
                    "experience": {
                        "type": "array",
                        "items": experience_change,
                    },
                },
                "required": [
                    "top_title", "summary", "experience_titles",
                    "skills", "experience",
                ],
            },
        },
        "required": [
            "schema_version", "decision", "overall_score", "review_summary",
            "review_basis", "component_scores", "manual_findings",
            "non_blocking_gaps", "requirement_resolutions", "changes",
        ],
    }


def build_ai_resume_quality_audit_prompt() -> str:
    return "\n".join(
        [
            "You are the final resume review panel. Work in one pass from three explicit points of view:",
            "1. Technical recruiter: recruiter recognition, advertised-title alignment, ATS terminology, scan order, and credible career progression.",
            "2. Hiring manager: direct evidence for the role's real outcomes, ownership, collaboration, and business or customer value.",
            "3. Principal engineer: technical accuracy, system depth, believable scope, engineering judgment, and coherent growth across roles.",
            "Return one unified patch-only decision. Never repeat the full resume.",
            "",
            "INPUT AUTHORITY:",
            "- read the authoritative advertised job title and raw JD before reviewing the resume",
            "- the advertised title is the primary title signal; actual JD responsibilities clarify its meaning",
            "- candidate evidence limits what may be claimed",
            "- the supplied JD analysis is advisory; override it when it conflicts with the advertised title or raw JD",
            "- current generated titles are drafts to evaluate, not facts to preserve",
            "- user-edited content deserves extra preservation, but may still receive a material, evidence-supported patch",
            "",
            "MANDATORY TITLE AND CAREER REVIEW:",
            "- evaluate the top resume title first on every review",
            "- use a common real-world market title that a recruiter would search for and immediately connect to the posted role",
            "- prefer the advertised title when it is market-standard; otherwise use its closest standard equivalent",
            "- avoid creative hybrids, vague labels, domain invention, and titles selected only because some keywords overlap",
            "- evaluate every experience title against the same target story and its own bullets",
            "- titles may differ by level or specialization, but together must show a believable career path toward the target role",
            "- recent roles should provide the strongest target alignment; older roles must remain truthful to their evidence",
            "- suggest complete title replacements whenever the current titles fail these checks",
            "",
            "FULL RESUME REVIEW:",
            "- build the review_basis first: normalized market title, explicit top-title and experience-title assessments with rationale, and the most important priorities from each point of view",
            "- derive the important JD requirements before proposing any resume change",
            "- for every important requirement, search the complete candidate evidence manifest across all roles, projects, certifications, and upstream-validated claims",
            "- classify each requirement by claim_type, evidence_fit, resume_action, and status before writing patches",
            "- engineering capabilities with direct or transferable evidence are resume-addressable and must use resume_action patch_required unless already covered",
            "- a patch-required requirement must return a complete title, summary, skill, or experience patch and link its exact change_ids",
            "- create safe patches for direct evidence and for genuinely transferable evidence before declaring a requirement unresolved",
            "- patched_transferable means the candidate evidence demonstrates the same underlying capability without pretending to have an unsupported exact tool, employer context, duration, or industry",
            "- unresolved is allowed only after the complete evidence manifest has been exhausted and no defensible wording can cover the requirement",
            "- then judge ATS alignment, technical credibility, natural human tone, evidence quality, and career coherence",
            "- verify that title, summary, skills, and experience tell the same supported professional story",
            "- prioritize the strongest three or four JD requirements and place their best supported evidence early",
            "- skills must be supported by experience evidence and use useful, standard categories",
            "- reject vague claims, keyword stuffing, robotic phrasing, implausible seniority, and unsupported domain ownership",
            "- preserve strong wording; recommend only changes that materially improve interview-readiness",
            "- do not score, flag, or propose a change solely because existing content is outside a word-count range",
            "- do not mention word-count compliance in the review summary, findings, reasons, or recommendations",
            "",
            "NON-RESUME REQUIREMENTS TO IGNORE FOR PATCHING:",
            "- warehouse installation, warehouse commissioning, conveyor-system operation, warehouse-site work, and warehouse or logistics domain context are not resume repair targets",
            "- travel percentage, willingness to travel, on-site attendance, relocation, work location, shift availability, physical requirements, work authorization, citizenship, security clearance, background checks, driver's licenses, degrees, certifications, and minimum years are application conditions or credentials, not experience bullets to invent",
            "- classify these as domain_context, application_condition, or credential_or_duration with evidence_fit none, resume_action gap_only, status unresolved, and empty change_ids",
            "- do not create title, summary, skill, or experience patches for these requirements and do not lower the resume decision solely because they are absent",
            "- when a JD mixes an ignored context with an engineering capability, ignore the context but repair the underlying engineering capability when direct or transferable evidence exists",
            "",
            "EVIDENCE RULES:",
            "- the job description is targeting context and never candidate evidence",
            "- the resume under review cannot prove its own new claims",
            "- every added title, summary, skill, category, or bullet must cite supplied evidence ids",
            "- never introduce a metric, tool, platform, vertical, responsibility, or seniority absent from cited evidence",
            "- upstream_validated evidence may be rephrased but not expanded into a stronger claim",
            "- projects and certifications are valid evidence when explicitly supplied in the candidate evidence manifest",
            "- do not mistake an exact-tool gap for a capability gap when supported adjacent evidence can be framed truthfully",
            "- unsupported JD requirements belong in non_blocking_gaps only after evidence-first resolution; do not turn unsupported facts into resume claims",
            "",
            "DECISION AND PATCH RULES:",
            "- approved requires empty changes and no error finding",
            "- changes_suggested requires at least one complete safe patch",
            "- manual_attention is only for a genuine factual or candidacy blocker that cannot be repaired safely; return empty changes",
            "- an unsupported optional improvement or ordinary JD gap is not manual_attention",
            "- every change_id must be unique and stable",
            "- every patched requirement must reference the exact change_ids that resolve it",
            "- already_covered and unresolved requirements must use an empty change_ids list",
            "- patch_required must use patched_direct or patched_transferable and must have at least one linked change_id",
            "- gap_only must use unresolved, empty change_ids, and no resume patch",
            "- every requirement evidence reference must exist in the supplied evidence manifest",
            "- every change identifies which reviewer points of view support it",
            "- title and summary changes must return the complete replacement text",
            "- skill removals and additions must identify the exact category and item",
            "- bullet numbers are one-based and refer to the original resume",
            "- a rewritten bullet is one atomic change group containing the original removal and complete replacement",
            f"- any new or replacement experience bullet must be {EXPERIENCE_BULLET_WORD_MIN}-{EXPERIENCE_BULLET_WORD_MAX} words after final wording",
            f"- if materially changing the top title or an experience title, its replacement must be {TITLE_WORD_MIN}-{TITLE_WORD_MAX} words",
            f"- if materially changing the summary, its replacement must be {SUMMARY_WORD_MIN}-{SUMMARY_WORD_MAX} words",
            "- new_position is one-based in the final bullet list",
            "- preserve each active role's required bullet-count range",
            "- do not leave a skill category with only one item; preserve supported skills or explicitly remove the category when the full category is unsupported",
            "- never modify companies, locations, dates, role keys, or inactive roles",
            "- give one concise reason for every change",
            "- return only JSON matching the supplied schema",
        ]
    )


def build_ai_resume_quality_audit_repair_prompt(
    original_input: dict,
    previous_result: dict,
    diagnostics: list[dict],
) -> str:
    repair_input = {
        "original_review_input": original_input,
        "previous_review_result": previous_result,
        "required_patch_diagnostics": diagnostics,
    }
    return (
        "Correct the previous patch review. Preserve every valid prior conclusion and patch, "
        "but repair each item in required_patch_diagnostics. Every listed item is a "
        "resume-addressable engineering requirement with candidate evidence, so it must return "
        "a grounded direct or transferable patch with valid evidence_refs and linked change_ids. "
        "Do not convert it to gap_only or unresolved. Do not create patches for warehouse "
        "installation, warehouse commissioning, conveyor operations, travel, location, or other "
        "application conditions. Return one complete schema-valid patch review JSON, not only the "
        "corrected fragments.\n"
        + json.dumps(repair_input, ensure_ascii=False, separators=(",", ":"))
    )


def _quality_audit_evidence_manifest(
    current_resume: dict,
    active_blueprints: list[dict],
    candidate_profile: dict | None = None,
) -> dict[str, dict]:
    manifest: dict[str, dict] = {}
    for blueprint in active_blueprints:
        role_key = str(blueprint.get("key", "")).strip()
        for field in (
            "anchor", "metric_evidence", "evidence",
            "achievements", "source_bullets", "default_title",
        ):
            value = blueprint.get(field)
            if value:
                manifest[f"profile.{role_key}.{field}"] = {
                    "source": "profile",
                    "value": copy.deepcopy(value),
                }
        role = ((current_resume.get("experience") or {}).get(role_key) or {})
        if str(role.get("title", "")).strip():
            manifest[f"upstream.{role_key}.title"] = {
                "source": "upstream_validated",
                "value": str(role["title"]).strip(),
            }
        for index, bullet in enumerate(role.get("bullets") or [], start=1):
            manifest[f"upstream.{role_key}.bullet.{index}"] = {
                "source": "upstream_validated",
                "value": str(bullet).strip(),
            }
    for category in normalize_updated_skills(current_resume.get("updated_skills") or []):
        category_key = re.sub(r"[^a-z0-9]+", "-", category["category"].lower()).strip("-")
        for index, skill in enumerate(category.get("items") or [], start=1):
            manifest[f"upstream.skills.{category_key}.{index}"] = {
                "source": "upstream_validated",
                "value": str(skill).strip(),
            }
    profile = candidate_profile if isinstance(candidate_profile, dict) else {}
    for project_index, project in enumerate(profile.get("projects") or [], start=1):
        if not isinstance(project, dict):
            continue
        name = str(project.get("name", "")).strip()
        if name:
            manifest[f"profile.project.{project_index}.name"] = {
                "source": "profile",
                "value": name,
            }
        for bullet_index, bullet in enumerate(project.get("bullets") or [], start=1):
            text = str(bullet).strip()
            if text:
                manifest[f"profile.project.{project_index}.bullet.{bullet_index}"] = {
                    "source": "profile",
                    "value": text,
                }
    for index, certification in enumerate(profile.get("certifications") or [], start=1):
        text = str(certification).strip()
        if text:
            manifest[f"profile.certification.{index}"] = {
                "source": "profile",
                "value": text,
            }
    for entry in profile.get("experience_history") or []:
        if not isinstance(entry, dict):
            continue
        role_key = str(entry.get("key", "")).strip()
        if not role_key:
            continue
        metadata = {
            field: str(entry.get(field, "")).strip()
            for field in ("company", "location", "title", "dates")
            if str(entry.get(field, "")).strip()
        }
        if metadata:
            manifest[f"profile.{role_key}.history"] = {
                "source": "profile",
                "value": metadata,
            }
    return manifest


QUALITY_AUDIT_IGNORED_REQUIREMENT_PATTERNS = (
    (
        "domain_context",
        re.compile(
            r"\b(?:warehouse(?:[- ]site)?\s+(?:installation|commissioning|operations?)|"
            r"conveyor(?:[- ]systems?)?|warehouse logistics|supply[- ]chain domain)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "application_condition",
        re.compile(
            r"\b(?:travel|on[- ]site|onsite|relocat(?:e|ion)|shift availability|"
            r"work authorization|sponsorship|citizenship|security clearance|"
            r"background check|driver'?s? licen[cs]e|physical requirements?|"
            r"lift(?:ing)?\s+\d+)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_or_duration",
        re.compile(
            r"\b(?:bachelor'?s?|master'?s?|ph\.?d\.?|degree|certification|"
            r"\d+\+?\s+years?(?:\s+of)?\s+experience)\b",
            re.IGNORECASE,
        ),
    ),
)


def _quality_audit_ignored_requirement_claim_type(requirement: str) -> str:
    text = str(requirement or "").strip()
    for claim_type, pattern in QUALITY_AUDIT_IGNORED_REQUIREMENT_PATTERNS:
        if pattern.search(text):
            return claim_type
    return ""


def _quality_audit_gap_kind(claim_type: str) -> str:
    normalized = str(claim_type or "").strip()
    if normalized in {
        "named_technology", "domain_context", "application_condition",
        "credential_or_duration",
    }:
        return normalized
    return "unsupported_engineering"


def _quality_audit_preflight(
    current_resume: dict,
    active_blueprints: list[dict],
) -> dict:
    skills = normalize_updated_skills(current_resume.get("updated_skills") or [])
    normalized_skills = [
        normalize_skill_dedupe_key(item)
        for entry in skills
        for item in expand_skill_items(entry.get("items") or [])
    ]
    duplicates = sorted({
        item for item in normalized_skills
        if item and normalized_skills.count(item) > 1
    })
    return {
        "skill_categories": [entry["category"] for entry in skills],
        "duplicate_skills": duplicates,
        "experience": {
            blueprint["key"]: {
                "company": blueprint.get("company", ""),
                "current_bullet_count": len(
                    ((current_resume.get("experience") or {}).get(blueprint["key"]) or {}).get("bullets") or []
                ),
                "required_bullet_min": blueprint["bullet_min"],
                "required_bullet_max": blueprint["bullet_max"],
            }
            for blueprint in active_blueprints
        },
    }


def _quality_audit_change_records(changes: dict) -> list[dict]:
    records: list[dict] = []
    for section in ("top_title", "summary"):
        change = changes.get(section)
        if isinstance(change, dict):
            records.append({"section": section, **change})
    for change in changes.get("experience_titles") or []:
        records.append({"section": "experience_title", **change})
    skills = changes.get("skills") or {}
    for field in (
        "category_removals", "category_additions",
        "skill_removals", "skill_additions",
    ):
        for change in skills.get(field) or []:
            records.append({"section": f"skills.{field}", **change})
    if isinstance(skills.get("category_order"), dict):
        records.append({"section": "skills.category_order", **skills["category_order"]})
    for role in changes.get("experience") or []:
        all_removals = [
            int(removal.get("bullet_number", 0))
            for group in role.get("change_groups") or []
            for removal in group.get("removals") or []
        ]
        all_additions = [
            addition
            for group in role.get("change_groups") or []
            for addition in group.get("additions") or []
        ]
        for change in role.get("change_groups") or []:
            records.append({
                "section": "experience",
                "role_key": role.get("role_key"),
                "company": role.get("company"),
                "current_bullet_count": role.get("current_bullet_count"),
                "proposed_bullet_count": role.get("proposed_bullet_count"),
                "role_all_removals": all_removals,
                "role_addition_count": len(all_additions),
                "role_reason": role.get("reason"),
                **change,
            })
    return records


def resume_quality_audit_review_groups(
    changed_paths_or_result,
    active_blueprints: list[dict] | None = None,
) -> list:
    if isinstance(changed_paths_or_result, dict):
        return copy.deepcopy(changed_paths_or_result.get("review_groups") or [])
    # Legacy callers can still obtain their path groups while stored v1
    # proposals are being marked stale.
    return globals()["_legacy_resume_quality_audit_review_groups"](
        changed_paths_or_result,
        active_blueprints,
    )

def _selected_quality_audit_changes(
    changes: dict,
    selected_ids: set[str],
) -> dict:
    selected = _empty_resume_quality_audit_changes()
    for section in ("top_title", "summary"):
        change = changes.get(section)
        if isinstance(change, dict) and change.get("change_id") in selected_ids:
            selected[section] = copy.deepcopy(change)
    selected["experience_titles"] = [
        copy.deepcopy(change)
        for change in changes.get("experience_titles") or []
        if change.get("change_id") in selected_ids
    ]
    skills = changes.get("skills") or {}
    for field in (
        "category_removals", "category_additions",
        "skill_removals", "skill_additions",
    ):
        selected["skills"][field] = [
            copy.deepcopy(change)
            for change in skills.get(field) or []
            if change.get("change_id") in selected_ids
        ]
    order_change = skills.get("category_order")
    if isinstance(order_change, dict) and order_change.get("change_id") in selected_ids:
        selected["skills"]["category_order"] = copy.deepcopy(order_change)
    for role in changes.get("experience") or []:
        groups = [
            copy.deepcopy(group)
            for group in role.get("change_groups") or []
            if group.get("change_id") in selected_ids
        ]
        if groups:
            removal_count = len({
                int(removal.get("bullet_number", 0))
                for group in groups
                for removal in group.get("removals") or []
            })
            addition_count = sum(
                len(group.get("additions") or [])
                for group in groups
            )
            current_count = int(role.get("current_bullet_count") or 0)
            selected["experience"].append({
                **{key: copy.deepcopy(role.get(key)) for key in (
                    "role_key", "company", "current_bullet_count",
                    "reason",
                )},
                "proposed_bullet_count": current_count - removal_count + addition_count,
                "change_groups": groups,
            })
    return selected


def _apply_quality_audit_changes(
    current_resume: dict,
    changes: dict,
    active_blueprints: list[dict],
) -> dict:
    resolved = _canonical_editable_resume(current_resume, active_blueprints)
    if isinstance(changes.get("top_title"), dict):
        resolved["updated_title"] = str(changes["top_title"]["suggested"]).strip()
    if isinstance(changes.get("summary"), dict):
        resolved["updated_summary"] = str(changes["summary"]["suggested"]).strip()
    for change in changes.get("experience_titles") or []:
        role_key = str(change.get("role_key", "")).strip()
        if role_key in resolved["experience"]:
            resolved["experience"][role_key]["title"] = str(change["suggested"]).strip()

    skill_rows = [
        {
            "category": entry["category"],
            "items": list(entry.get("items") or []),
        }
        for entry in normalize_updated_skills(resolved.get("updated_skills") or [])
    ]
    skills = changes.get("skills") or {}
    removed_categories = {
        str(change.get("category", "")).strip()
        for change in skills.get("category_removals") or []
    }
    skill_rows = [
        row for row in skill_rows
        if row["category"] not in removed_categories
    ]
    for change in skills.get("category_additions") or []:
        category = str(change["category"]).strip()
        if any(row["category"] == category for row in skill_rows):
            continue
        row = {
            "category": category,
            "items": [str(item).strip() for item in change.get("skills") or [] if str(item).strip()],
        }
        after = str(change.get("insert_after_category") or "").strip()
        insert_index = next(
            (index + 1 for index, existing in enumerate(skill_rows) if existing["category"] == after),
            len(skill_rows),
        )
        skill_rows.insert(insert_index, row)
    for change in skills.get("skill_removals") or []:
        category = str(change["category"]).strip()
        skill = normalize_skill_dedupe_key(change["skill"])
        for row in skill_rows:
            if row["category"] == category:
                row["items"] = [
                    item for item in row["items"]
                    if normalize_skill_dedupe_key(item) != skill
                ]
    for change in skills.get("skill_additions") or []:
        category = str(change["category"]).strip()
        row = next((entry for entry in skill_rows if entry["category"] == category), None)
        if row is None:
            row = {"category": category, "items": []}
            skill_rows.append(row)
        skill = str(change["skill"]).strip()
        if normalize_skill_dedupe_key(skill) not in {
            normalize_skill_dedupe_key(item) for item in row["items"]
        }:
            row["items"].append(skill)
    order_change = skills.get("category_order")
    if isinstance(order_change, dict):
        requested = list(dict.fromkeys(order_change.get("suggested") or []))
        order_index = {category: index for index, category in enumerate(requested)}
        skill_rows.sort(key=lambda row: (order_index.get(row["category"], len(requested)), row["category"]))
    resolved["updated_skills"] = [row for row in skill_rows if row["items"]]

    for role_change in changes.get("experience") or []:
        role_key = str(role_change.get("role_key", "")).strip()
        if role_key not in resolved["experience"]:
            continue
        original = list(resolved["experience"][role_key]["bullets"])
        removals = {
            int(removal["bullet_number"])
            for group in role_change.get("change_groups") or []
            for removal in group.get("removals") or []
        }
        bullets = [
            bullet for index, bullet in enumerate(original, start=1)
            if index not in removals
        ]
        additions = [
            addition
            for group in role_change.get("change_groups") or []
            for addition in group.get("additions") or []
        ]
        for addition in sorted(additions, key=lambda item: int(item["new_position"])):
            position = max(1, min(int(addition["new_position"]), len(bullets) + 1))
            bullets.insert(position - 1, str(addition["new_bullet"]).strip())
        resolved["experience"][role_key]["bullets"] = bullets
    return resolved


def _quality_audit_resume_validation_issues(
    proposal: dict,
    analysis_payload: dict,
    active_blueprints: list[dict],
) -> list[str]:
    issues: list[str] = []
    raw_skills = proposal.get("updated_skills")
    if not isinstance(raw_skills, list):
        issues.append("Updated skills must be a list.")
    else:
        raw_categories: set[str] = set()
        for entry in raw_skills:
            if not isinstance(entry, dict):
                issues.append("Every skills category must be an object.")
                continue
            category = str(entry.get("category", "")).strip()
            items = expand_skill_items(entry.get("items") or [])
            if category in raw_categories:
                issues.append(f"Duplicate skills category: {category}.")
            raw_categories.add(category)
            if len(items) < 2:
                issues.append(
                    f"Skills category '{category or 'Unnamed'}' must retain at least 2 skills."
                )
        if len(raw_skills) < 6:
            issues.append("Updated skills must retain at least 6 categories.")
    issues.extend(validate_core_payload(proposal, analysis_payload))
    issues.extend(validate_skills_only_payload(proposal, analysis_payload))
    issues.extend(validate_experience_subset_payload_with_analysis(
        proposal,
        active_blueprints,
        analysis_payload,
    ))
    issues.extend(validate_experience_title_review_payload(
        {
            "experience_titles": {
                role_key: role.get("title", "")
                for role_key, role in (proposal.get("experience") or {}).items()
            }
        },
        active_blueprints,
        analysis_payload,
    ))
    return list(dict.fromkeys(issues))


def _quality_audit_grounding_issue(
    record: dict,
    evidence_manifest: dict[str, dict],
    analysis_payload: dict,
) -> str:
    refs = record.get("evidence_refs") or []
    additions = record.get("additions") or []
    if additions:
        refs = [
            ref
            for addition in additions
            for ref in addition.get("evidence_refs") or []
        ]
    unknown = sorted({str(ref) for ref in refs if str(ref) not in evidence_manifest})
    if unknown:
        return "Unknown evidence references: " + ", ".join(unknown) + "."
    if not refs:
        return ""
    cited_evidence_blob = _text_evidence_blob([
        evidence_manifest[str(ref)]["value"] for ref in refs
    ])
    section = str(record.get("section", ""))
    role_key = str(record.get("role_key", "")).strip()
    if section in {"experience", "experience_title"} and role_key:
        retained_evidence = [
            item["value"]
            for evidence_id, item in evidence_manifest.items()
            if evidence_id.startswith(f"profile.{role_key}.")
            or evidence_id.startswith(f"upstream.{role_key}.")
        ]
    else:
        retained_evidence = [item["value"] for item in evidence_manifest.values()]
    grounded_evidence_blob = _text_evidence_blob(
        [cited_evidence_blob, *retained_evidence]
    )
    proposed_values: list[str] = []
    if record.get("suggested"):
        proposed_values.append(str(record["suggested"]))
    if record.get("skill"):
        proposed_values.append(str(record["skill"]))
    proposed_values.extend(str(item) for item in record.get("skills") or [])
    proposed_values.extend(
        str(addition.get("new_bullet", ""))
        for addition in additions
    )
    proposed_blob = "\n".join(proposed_values)
    unsupported_metrics = sorted(
        _numeric_tokens(proposed_blob) - _numeric_tokens(grounded_evidence_blob)
    )
    if unsupported_metrics:
        return "Unsupported numeric claims: " + ", ".join(unsupported_metrics) + "."
    normalized_evidence = normalize_skill_dedupe_key(grounded_evidence_blob)
    normalized_proposal = normalize_skill_dedupe_key(proposed_blob)
    for term in sorted(AUDIT_KNOWN_NAMED_TECHNOLOGY_TERMS, key=lambda value: (-len(value), value)):
        if term in normalized_proposal and term not in normalized_evidence:
            return f"Unsupported named tool or technical claim '{term}'."
    domain_terms = [
        normalize_skill_dedupe_key(term)
        for term in (
            list(analysis_payload.get("domain_terms") or [])
            + [analysis_payload.get("company_domain", "")]
        )
        if normalize_skill_dedupe_key(term)
    ]
    for term in domain_terms:
        if term in normalized_proposal and term not in normalized_evidence:
            return f"Unsupported vertical claim '{term}'."
    return ""


def _quality_audit_patch_structure_issue(
    record: dict,
    current_resume: dict,
    active_blueprints: list[dict],
) -> str:
    if not str(record.get("reason", "")).strip():
        return "The change is missing a reason."
    section = str(record.get("section", ""))
    evidence_required = section in {
        "top_title",
        "summary",
        "experience_title",
        "skills.category_additions",
        "skills.skill_additions",
    }
    if evidence_required and not record.get("evidence_refs"):
        return "The change is missing candidate evidence references."
    if section in {"top_title", "summary", "experience_title"}:
        if not str(record.get("suggested", "")).strip():
            return "The replacement text is empty."
    blueprint_by_key = {
        str(blueprint.get("key", "")).strip(): blueprint
        for blueprint in active_blueprints
    }
    if section == "experience_title":
        role_key = str(record.get("role_key", "")).strip()
        if role_key not in blueprint_by_key:
            return f"Unknown or inactive role key '{role_key}'."
    current_skills = {
        row["category"]: {
            normalize_skill_dedupe_key(item)
            for item in row.get("items") or []
        }
        for row in normalize_updated_skills(current_resume.get("updated_skills") or [])
    }
    if section == "skills.category_removals":
        category = str(record.get("category", "")).strip()
        if category not in current_skills:
            return f"Skill category '{category}' is not present."
    elif section == "skills.category_additions":
        category = str(record.get("category", "")).strip()
        if category in current_skills:
            return f"Skill category '{category}' already exists."
        if len([item for item in record.get("skills") or [] if str(item).strip()]) < 2:
            return "A new skill category must contain at least two skills."
    elif section == "skills.skill_removals":
        category = str(record.get("category", "")).strip()
        skill = normalize_skill_dedupe_key(record.get("skill", ""))
        if category not in current_skills or skill not in current_skills[category]:
            return f"Skill '{record.get('skill', '')}' is not present in '{category}'."
    elif section == "skills.skill_additions":
        category = str(record.get("category", "")).strip()
        skill = normalize_skill_dedupe_key(record.get("skill", ""))
        if not skill:
            return "The added skill is empty."
        if category in current_skills and skill in current_skills[category]:
            return f"Skill '{record.get('skill', '')}' already exists in '{category}'."
    elif section == "skills.category_order":
        suggested = [str(item).strip() for item in record.get("suggested") or []]
        if not suggested or len(suggested) != len(set(suggested)):
            return "Category order must contain unique category names."
    elif section == "experience":
        role_key = str(record.get("role_key", "")).strip()
        blueprint = blueprint_by_key.get(role_key)
        if not blueprint:
            return f"Unknown or inactive role key '{role_key}'."
        if str(record.get("company", "")).strip() != str(blueprint.get("company", "")).strip():
            return "The patch company does not match the active experience role."
        original = (
            ((current_resume.get("experience") or {}).get(role_key) or {}).get("bullets")
            or []
        )
        removals = [
            int(item.get("bullet_number", 0))
            for item in record.get("removals") or []
        ]
        additions = list(record.get("additions") or [])
        if not removals and not additions:
            return "An experience change must remove or add at least one bullet."
        if len(removals) != len(set(removals)):
            return "A bullet cannot be removed twice in one atomic change."
        if any(number < 1 or number > len(original) for number in removals):
            return "A bullet removal references an out-of-range original bullet."
        declared_current = int(record.get("current_bullet_count") or 0)
        declared_proposed = int(record.get("proposed_bullet_count") or 0)
        if declared_current != len(original):
            return "The declared current bullet count does not match the resume."
        all_removals = [
            int(number)
            for number in record.get("role_all_removals") or []
        ]
        if len(all_removals) != len(set(all_removals)):
            return "A bullet cannot be removed by more than one atomic change."
        if any(number < 1 or number > len(original) for number in all_removals):
            return "A bullet removal references an out-of-range original bullet."
        expected_proposed = (
            len(original)
            - len(all_removals)
            + int(record.get("role_addition_count") or 0)
        )
        if declared_proposed != expected_proposed:
            return "The declared proposed bullet count does not match the atomic changes."
        replaced_numbers: set[int] = set()
        for addition in additions:
            if not str(addition.get("new_bullet", "")).strip():
                return "An added bullet is empty."
            if not addition.get("evidence_refs"):
                return "An added bullet is missing candidate evidence references."
            position = int(addition.get("new_position") or 0)
            if position < 1 or position > max(1, declared_proposed):
                return "An added bullet has an invalid final position."
            replacements = {
                int(number)
                for number in addition.get("replaces_bullet_numbers") or []
            }
            if not replacements.issubset(set(removals)):
                return "A replacement references a bullet not removed by its atomic change."
            replaced_numbers.update(replacements)
        if additions and removals and replaced_numbers != set(removals):
            return "Every removed rewrite bullet must be linked to its replacement."
    return ""


def validate_resume_quality_audit_result(
    audit_result: dict,
    *,
    current_resume: dict,
    analysis_payload: dict,
    active_blueprints: list[dict],
    candidate_profile: dict | None = None,
    max_change_fraction: float = RESUME_QUALITY_AUDIT_MAX_CHANGE_FRACTION,
) -> dict:
    del max_change_fraction
    if not isinstance(audit_result, dict):
        raise ResumeQualityAuditValidationError(["Audit result must be an object."])
    if str(audit_result.get("schema_version", "")) != RESUME_QUALITY_AUDIT_SCHEMA_VERSION:
        raise ResumeQualityAuditValidationError(["Unsupported quality audit schema version."])
    decision = str(audit_result.get("decision", "")).strip()
    if decision not in {"approved", "changes_suggested", "manual_attention"}:
        raise ResumeQualityAuditValidationError(["Invalid quality audit decision."])
    changes = audit_result.get("changes")
    if not isinstance(changes, dict):
        raise ResumeQualityAuditValidationError(["Quality audit changes must be an object."])
    records = _quality_audit_change_records(changes)
    change_ids = [str(record.get("change_id", "")).strip() for record in records]
    structural_issues: list[str] = []
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", change_id) for change_id in change_ids):
        structural_issues.append("Every patch must have a valid change_id.")
    if len(change_ids) != len(set(change_ids)):
        structural_issues.append("Every patch change_id must be unique.")
    if decision == "approved" and records:
        structural_issues.append("approved requires empty changes.")
    if decision == "changes_suggested" and not records:
        structural_issues.append("changes_suggested requires at least one change.")
    if decision == "manual_attention" and records:
        structural_issues.append("manual_attention requires empty changes.")
    if not str(audit_result.get("review_summary", "")).strip():
        structural_issues.append("A concise review summary is required.")
    for name in RESUME_QUALITY_AUDIT_SCORE_COMPONENTS:
        value = (audit_result.get("component_scores") or {}).get(name)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
            structural_issues.append(f"Component score '{name}' must be an integer from 0 to 100.")
    overall_score = audit_result.get("overall_score")
    if not isinstance(overall_score, int) or isinstance(overall_score, bool) or not 0 <= overall_score <= 100:
        structural_issues.append("Overall score must be an integer from 0 to 100.")
    if decision == "manual_attention" and not (audit_result.get("manual_findings") or []):
        structural_issues.append("manual_attention requires at least one blocking finding.")
    review_basis_input = audit_result.get("review_basis") or {}
    top_title_change = isinstance(changes.get("top_title"), dict)
    experience_title_changes = bool(changes.get("experience_titles") or [])
    if (
        decision != "manual_attention"
        and review_basis_input.get("top_title_assessment") == "change_recommended"
        and not top_title_change
    ):
        structural_issues.append(
            "A recommended top-title change requires a complete top-title patch."
        )
    if (
        decision != "manual_attention"
        and review_basis_input.get("experience_title_assessment") == "change_recommended"
        and not experience_title_changes
    ):
        structural_issues.append(
            "A recommended career-title change requires at least one experience-title patch."
        )
    if structural_issues:
        raise ResumeQualityAuditValidationError(structural_issues)

    review_basis = copy.deepcopy(audit_result.get("review_basis") or {})
    if not str(review_basis.get("normalized_market_title", "")).strip():
        review_basis["normalized_market_title"] = (
            str(review_basis.get("advertised_job_title", "")).strip()
            or str(analysis_payload.get("target_role", "")).strip()
            or str(current_resume.get("updated_title", "")).strip()
            or "Target Role"
        )
    review_basis.setdefault("advertised_job_title", None)
    review_basis.setdefault("top_title_assessment", "aligned")
    review_basis.setdefault("experience_title_assessment", "coherent")
    review_basis.setdefault(
        "title_rationale",
        "The title set was evaluated against the target role and candidate evidence.",
    )
    for field in (
        "technical_recruiter_priorities",
        "hiring_manager_priorities",
        "principal_engineer_priorities",
    ):
        priorities = review_basis.get(field)
        if not isinstance(priorities, list) or not priorities:
            review_basis[field] = ["Evaluate the resume against the target role."]
    non_blocking_gaps = copy.deepcopy(audit_result.get("non_blocking_gaps") or [])
    for gap in non_blocking_gaps:
        if isinstance(gap, dict) and not str(gap.get("kind", "")).strip():
            gap["kind"] = "unsupported_engineering"

    current = _canonical_editable_resume(current_resume, active_blueprints)
    evidence_manifest = _quality_audit_evidence_manifest(
        current,
        active_blueprints,
        candidate_profile,
    )
    requirement_resolutions = copy.deepcopy(
        audit_result.get("requirement_resolutions") or []
    )
    requirement_ids = [
        str(item.get("requirement_id", "")).strip()
        for item in requirement_resolutions
        if isinstance(item, dict)
    ]
    if len(requirement_ids) != len(set(requirement_ids)):
        raise ResumeQualityAuditValidationError(
            ["Every requirement resolution must have a unique requirement_id."]
        )
    known_evidence_ids = set(evidence_manifest)
    known_change_ids = set(change_ids)
    resolution_issues: list[str] = []
    resolution_diagnostics: list[dict] = []
    gap_only_linked_change_ids: set[str] = set()
    patch_required_linked_change_ids: set[str] = set()
    for item in requirement_resolutions:
        if not isinstance(item, dict):
            resolution_issues.append("Every requirement resolution must be an object.")
            continue
        requirement_id = str(item.get("requirement_id", "")).strip()
        requirement = str(item.get("requirement", "")).strip()
        status = str(item.get("status", "")).strip()
        claim_type = str(item.get("claim_type", "")).strip()
        evidence_fit = str(item.get("evidence_fit", "")).strip()
        resume_action = str(item.get("resume_action", "")).strip()
        ignored_claim_type = _quality_audit_ignored_requirement_claim_type(requirement)
        if ignored_claim_type:
            claim_type = ignored_claim_type
            evidence_fit = "none"
            resume_action = "gap_only"
            status = "unresolved"
        elif not claim_type:
            # Preserve compatibility with persisted schema-v2 reviews created
            # before explicit requirement classification was introduced.
            claim_type = "engineering_capability"
        if not evidence_fit:
            evidence_fit = {
                "patched_direct": "direct",
                "patched_transferable": "transferable",
            }.get(status, "none")
        if not resume_action:
            resume_action = (
                "already_covered" if status == "already_covered"
                else "patch_required" if status in {"patched_direct", "patched_transferable"}
                else "gap_only"
            )
        priority = str(item.get("priority", "")).strip()
        if not ignored_claim_type:
            if status == "already_covered":
                resume_action = "already_covered"
            elif (
                claim_type in {"engineering_capability", "named_technology"}
                and evidence_fit in {"direct", "transferable"}
                and priority in {"critical", "important"}
            ):
                resume_action = "patch_required"
            elif evidence_fit == "none":
                resume_action = "gap_only"
        item["claim_type"] = claim_type
        item["evidence_fit"] = evidence_fit
        item["resume_action"] = resume_action
        item["status"] = status
        refs = [str(ref).strip() for ref in item.get("evidence_refs") or []]
        linked_changes = [
            str(change_id).strip()
            for change_id in item.get("change_ids") or []
        ]
        unknown_refs = sorted(set(refs) - known_evidence_ids)
        if unknown_refs:
            item["evidence_refs"] = [
                ref for ref in refs if ref in known_evidence_ids
            ]
            resolution_diagnostics.append({
                "requirement_id": requirement_id,
                "issue": "unknown_evidence_refs_removed",
                "details": unknown_refs,
            })
        else:
            item["evidence_refs"] = refs
        unknown_changes = sorted(set(linked_changes) - known_change_ids)
        if unknown_changes:
            linked_changes = [
                change_id for change_id in linked_changes
                if change_id in known_change_ids
            ]
            resolution_diagnostics.append({
                "requirement_id": requirement_id,
                "issue": "unknown_change_ids_removed",
                "details": unknown_changes,
            })
        if resume_action == "gap_only":
            gap_only_linked_change_ids.update(linked_changes)
        elif resume_action == "patch_required":
            patch_required_linked_change_ids.update(linked_changes)
        if status in {"already_covered", "unresolved"} and linked_changes:
            # The patch remains independently eligible. Only the contradictory
            # requirement-to-patch link is removed so one metadata mistake does
            # not discard the complete review.
            resolution_diagnostics.append({
                "requirement_id": requirement_id,
                "issue": "incompatible_change_ids_removed",
                "details": list(linked_changes),
            })
            linked_changes = []
        if status in {"patched_direct", "patched_transferable"} and not linked_changes:
            status = "unresolved"
            item["status"] = status
            item["reason"] = (
                str(item.get("reason", "")).strip()
                + " No valid linked patch remained after validation."
            ).strip()
            resolution_diagnostics.append({
                "requirement_id": requirement_id,
                "issue": "patched_requirement_downgraded",
                "details": [],
            })
        item["change_ids"] = linked_changes
    if resolution_issues:
        raise ResumeQualityAuditValidationError(resolution_issues)
    candidate_ids: set[str] = set()
    withheld: list[dict] = []
    for record in records:
        change_id = str(record["change_id"]).strip()
        if (
            change_id in gap_only_linked_change_ids
            and change_id not in patch_required_linked_change_ids
        ):
            withheld.append({
                "change_id": change_id,
                "section": record["section"],
                "reason": "Non-resume requirements cannot create resume patches.",
            })
            continue
        patch_issue = _quality_audit_patch_structure_issue(
            record,
            current,
            active_blueprints,
        )
        if patch_issue:
            withheld.append({
                "change_id": change_id,
                "section": record["section"],
                "reason": patch_issue,
            })
            continue
        grounding_issue = _quality_audit_grounding_issue(
            record,
            evidence_manifest,
            analysis_payload,
        )
        if grounding_issue:
            withheld.append({
                "change_id": change_id,
                "section": record["section"],
                "reason": grounding_issue,
            })
            continue
        candidate_ids.add(change_id)

    current_skill_rows = {
        row["category"]: {
            normalize_skill_dedupe_key(item)
            for item in row.get("items") or []
        }
        for row in normalize_updated_skills(current.get("updated_skills") or [])
    }
    explicit_category_removals = {
        str(record.get("category", "")).strip()
        for record in records
        if record.get("section") == "skills.category_removals"
        and record.get("change_id") in candidate_ids
    }
    for category, current_items in current_skill_rows.items():
        removal_records = [
            record
            for record in records
            if record.get("section") == "skills.skill_removals"
            and record.get("change_id") in candidate_ids
            and str(record.get("category", "")).strip() == category
        ]
        if not removal_records or category in explicit_category_removals:
            continue
        removed_items = {
            normalize_skill_dedupe_key(record.get("skill", ""))
            for record in removal_records
        }
        added_items = {
            normalize_skill_dedupe_key(record.get("skill", ""))
            for record in records
            if record.get("section") == "skills.skill_additions"
            and record.get("change_id") in candidate_ids
            and str(record.get("category", "")).strip() == category
        }
        if len((current_items - removed_items) | added_items) >= 2:
            continue
        for record in removal_records:
            change_id = str(record["change_id"]).strip()
            candidate_ids.discard(change_id)
            withheld.append({
                "change_id": change_id,
                "section": record["section"],
                "reason": (
                    f"Removing this item would leave '{category}' with fewer "
                    "than two supported skills. The category was preserved."
                ),
            })

    def candidate_validation_issues(selected_ids: set[str]) -> list[str]:
        trial_changes = _selected_quality_audit_changes(changes, selected_ids)
        try:
            trial_resume = _apply_quality_audit_changes(
                current,
                trial_changes,
                active_blueprints,
            )
            return _quality_audit_resume_validation_issues(
                trial_resume,
                analysis_payload,
                active_blueprints,
            )
        except Exception as exc:
            return [str(exc)]

    holistic_issues = candidate_validation_issues(candidate_ids)
    while candidate_ids and holistic_issues:
        best_change_id = None
        best_issues = holistic_issues
        for change_id in sorted(candidate_ids):
            remaining = candidate_ids - {change_id}
            remaining_issues = candidate_validation_issues(remaining)
            if (
                best_change_id is None
                or len(remaining_issues) < len(best_issues)
                or (
                    len(remaining_issues) == len(best_issues)
                    and change_id < best_change_id
                )
            ):
                best_change_id = change_id
                best_issues = remaining_issues
        if best_change_id is None:
            break
        record = next(
            item for item in records
            if str(item.get("change_id", "")).strip() == best_change_id
        )
        candidate_ids.remove(best_change_id)
        withheld.append({
            "change_id": best_change_id,
            "section": record["section"],
            "reason": holistic_issues[0],
        })
        holistic_issues = best_issues

    accepted_ids = candidate_ids
    if holistic_issues:
        for change_id in sorted(accepted_ids):
            record = next(
                item for item in records
                if str(item.get("change_id", "")).strip() == change_id
            )
            withheld.append({
                "change_id": change_id,
                "section": record["section"],
                "reason": holistic_issues[0],
            })
        accepted_ids = set()

    validated_changes = _selected_quality_audit_changes(changes, accepted_ids)
    validated_records = _quality_audit_change_records(validated_changes)
    final_decision = decision
    manual_findings = copy.deepcopy(audit_result.get("manual_findings") or [])
    if decision == "changes_suggested" and not validated_records:
        final_decision = "approved"
        non_blocking_gaps.extend({
            "id": f"withheld.{item['change_id']}",
            "path": str(item.get("section", "resume")),
            "kind": "withheld_patch",
            "gap": "An optional review suggestion was withheld by deterministic validation.",
            "impact": str(item.get("reason", "")).strip(),
            "evidence_refs": [],
        } for item in withheld)
    if final_decision == "manual_attention":
        validated_changes = _empty_resume_quality_audit_changes()
        validated_records = []

    normalized_requirement_resolutions: list[dict] = []
    required_patch_diagnostics: list[dict] = []
    existing_gap_ids = {
        str(item.get("id", "")).strip()
        for item in non_blocking_gaps
        if isinstance(item, dict)
    }
    for item in requirement_resolutions:
        resolution = copy.deepcopy(item)
        linked_ids = [
            str(change_id).strip()
            for change_id in resolution.get("change_ids") or []
        ]
        surviving_ids = [
            change_id for change_id in linked_ids
            if change_id in accepted_ids
        ]
        requires_patch = resolution.get("resume_action") == "patch_required"
        valid_patched_status = resolution.get("status") in {
            "patched_direct", "patched_transferable",
        }
        if requires_patch and (not valid_patched_status or not surviving_ids):
            linked_withheld = [
                item for item in withheld
                if str(item.get("change_id", "")).strip() in set(linked_ids)
            ]
            reason = (
                "Resume-addressable engineering requirement "
                f"'{resolution.get('requirement', '')}' requires a valid linked patch."
            )
            if linked_withheld:
                reason += " Proposed patches were withheld: " + "; ".join(
                    str(item.get("reason", "")).strip()
                    for item in linked_withheld
                    if str(item.get("reason", "")).strip()
                )
            required_patch_diagnostics.append({
                "requirement_id": str(resolution.get("requirement_id", "")).strip(),
                "requirement": str(resolution.get("requirement", "")).strip(),
                "claim_type": str(resolution.get("claim_type", "")).strip(),
                "evidence_fit": str(resolution.get("evidence_fit", "")).strip(),
                "evidence_refs": copy.deepcopy(resolution.get("evidence_refs") or []),
                "linked_change_ids": linked_ids,
                "reason": reason,
            })
        if (
            resolution.get("status") in {"patched_direct", "patched_transferable"}
            and not surviving_ids
        ):
            resolution["status"] = "unresolved"
            resolution["change_ids"] = []
            resolution["reason"] = (
                str(resolution.get("reason", "")).strip()
                + " The proposed patch was withheld by deterministic validation."
            ).strip()
        else:
            resolution["change_ids"] = surviving_ids
        normalized_requirement_resolutions.append(resolution)
        if resolution.get("status") != "unresolved":
            continue
        gap_id = f"requirement.{resolution.get('requirement_id')}"
        if gap_id in existing_gap_ids:
            continue
        non_blocking_gaps.append({
            "id": gap_id,
            "path": "job.requirements",
            "kind": _quality_audit_gap_kind(resolution.get("claim_type", "")),
            "gap": str(resolution.get("requirement", "")).strip(),
            "impact": str(resolution.get("reason", "")).strip(),
            "evidence_refs": copy.deepcopy(
                resolution.get("evidence_refs") or []
            ),
        })
        existing_gap_ids.add(gap_id)

    if required_patch_diagnostics:
        raise ResumeQualityAuditRepairRequiredError(required_patch_diagnostics)

    review_groups = []
    blueprint_by_key = {
        str(blueprint.get("key", "")).strip(): blueprint
        for blueprint in active_blueprints
    }
    current_skill_rows = {
        row["category"]: list(row.get("items") or [])
        for row in normalize_updated_skills(current.get("updated_skills") or [])
    }
    for record in validated_records:
        group = copy.deepcopy(record)
        group.pop("role_all_removals", None)
        group.pop("role_addition_count", None)
        change_id = str(group["change_id"])
        group["change_id"] = change_id
        group["current"] = None
        group["proposed"] = None
        if group["section"] == "top_title":
            group["current"] = current["updated_title"]
            group["proposed"] = group.get("suggested")
        elif group["section"] == "summary":
            group["current"] = current["updated_summary"]
            group["proposed"] = group.get("suggested")
        elif group["section"] == "experience_title":
            role_key = group.get("role_key")
            group["company"] = (
                blueprint_by_key.get(str(role_key), {}).get("company")
                or str(role_key)
            )
            group["current"] = ((current.get("experience") or {}).get(role_key) or {}).get("title")
            group["proposed"] = group.get("suggested")
        elif group["section"] == "experience":
            role_key = group.get("role_key")
            original = ((current.get("experience") or {}).get(role_key) or {}).get("bullets") or []
            removal_numbers = [
                int(item["bullet_number"])
                for item in group.get("removals") or []
            ]
            group["current"] = [
                original[number - 1]
                for number in removal_numbers
                if 1 <= number <= len(original)
            ]
            group["proposed"] = [
                item.get("new_bullet", "")
                for item in group.get("additions") or []
            ]
        elif group["section"] == "skills.category_removals":
            group["current"] = {
                "category": group.get("category"),
                "skills": current_skill_rows.get(group.get("category"), []),
            }
        elif group["section"] == "skills.category_additions":
            group["proposed"] = {
                "category": group.get("category"),
                "skills": group.get("skills") or [],
            }
        elif group["section"] == "skills.skill_removals":
            group["current"] = {
                "category": group.get("category"),
                "skill": group.get("skill"),
            }
        elif group["section"] == "skills.skill_additions":
            group["proposed"] = {
                "category": group.get("category"),
                "skill": group.get("skill"),
            }
        elif group["section"] == "skills.category_order":
            group["current"] = list(current_skill_rows)
            group["proposed"] = group.get("suggested") or []
        review_groups.append(group)

    return {
        "schema_version": RESUME_QUALITY_AUDIT_SCHEMA_VERSION,
        "decision": final_decision,
        "overall_score": int(audit_result.get("overall_score", 0)),
        "review_summary": str(audit_result.get("review_summary", "")).strip(),
        "review_basis": review_basis,
        "component_scores": {
            name: int((audit_result.get("component_scores") or {}).get(name, 0))
            for name in RESUME_QUALITY_AUDIT_SCORE_COMPONENTS
        },
        "manual_findings": manual_findings,
        "non_blocking_gaps": non_blocking_gaps,
        "requirement_resolutions": normalized_requirement_resolutions,
        "requirement_resolution_diagnostics": resolution_diagnostics,
        "changes": validated_changes,
        "review_groups": review_groups,
        "withheld_changes": withheld,
        "base_hash": canonical_json_hash(current),
    }


def _is_max_output_tokens_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "max_output_tokens" in message or (
        "status=incomplete" in message and "max" in message and "token" in message
    )


def _is_transient_audit_network_error(exc: Exception) -> bool:
    transient_types = (
        TimeoutError,
        socket.timeout,
        ConnectionError,
        urllib.error.URLError,
    )
    current: BaseException | None = exc
    messages = []
    while current is not None:
        if isinstance(current, transient_types):
            return True
        messages.append(str(current).lower())
        current = current.__cause__ or current.__context__

    message = " | ".join(messages)
    return any(
        term in message
        for term in (
            "connection closed",
            "connection reset",
            "connection aborted",
            "connection refused",
            "remote end closed",
            "network is unreachable",
            "name resolution",
            "temporary failure in name resolution",
            "timed out",
            "timeout",
            "ssl eof",
            "unexpected eof",
            "did not finish within",
            "winerror 10053",
            "winerror 10054",
            "winerror 10060",
        )
    )


def _quality_audit_failure_metadata(exc: Exception) -> dict:
    message = str(exc)
    normalized = message.lower()
    recorded_attempts = max(1, int(getattr(exc, "audit_attempt_count", 1)))
    if _is_max_output_tokens_error(exc):
        category = "max_output_tokens"
        attempt_count = max(2, recorded_attempts)
    elif isinstance(exc, ResumeQualityAuditValidationError):
        category = "validation"
        attempt_count = recorded_attempts
    elif any(term in normalized for term in ("401", "403", "authentication", "api key", "unauthorized")):
        category = "authentication"
        attempt_count = recorded_attempts
    elif _is_transient_audit_network_error(exc) or any(
        term in normalized for term in ("network", "connection", "dns")
    ):
        category = "network"
        attempt_count = recorded_attempts
    elif any(term in normalized for term in ("json", "schema", "parse")):
        category = "parsing"
        attempt_count = recorded_attempts
    else:
        category = "api"
        attempt_count = recorded_attempts
    return {
        "schema_version": RESUME_QUALITY_AUDIT_SCHEMA_VERSION,
        "decision": "technical_failed",
        "error": message,
        "error_kind": category,
        "model": AUDIT_MODEL,
        "reasoning_effort": AUDIT_REASONING_EFFORT,
        "attempt_count": attempt_count,
        "token_usage": None,
        "execution_mode": "background",
        "response_id": getattr(exc, "openai_response_id", None),
    }


def generate_resume_quality_audit(
    *,
    api_key: str,
    job_description: str,
    analysis_payload: dict,
    current_resume: dict,
    active_blueprints: list[dict],
    candidate_profile: dict | None = None,
    advertised_job_title: str = "",
    user_edit_context: dict | None = None,
    model: str = AUDIT_MODEL,
    timeout_seconds: int = OPENAI_RESUME_TIMEOUT_SECONDS,
    reasoning_effort: str = AUDIT_REASONING_EFFORT,
    max_change_fraction: float = RESUME_QUALITY_AUDIT_MAX_CHANGE_FRACTION,
) -> dict:
    del max_change_fraction
    order_key = skill_category_order_key_for_analysis(analysis_payload)
    ordered_categories = skill_category_order_for_key(order_key)
    canonical_resume = _canonical_editable_resume(current_resume, active_blueprints)
    evidence_manifest = _quality_audit_evidence_manifest(
        canonical_resume,
        active_blueprints,
        candidate_profile,
    )
    authoritative_title = str(advertised_job_title or "").strip()
    review_input = {
        "job": {
            "advertised_title": authoritative_title or None,
            "advertised_title_is_authoritative": bool(authoritative_title),
            "description": job_description.strip(),
        },
        "advisory_analysis": compact_analysis_for_generation(analysis_payload),
        "resume_under_review": canonical_resume,
        "deterministic_preflight": _quality_audit_preflight(
            canonical_resume,
            active_blueprints,
        ),
        "candidate_evidence_manifest": evidence_manifest,
        "active_roles": [
            {
                "key": blueprint["key"],
                "company": blueprint.get("company", ""),
                "bullet_min": blueprint["bullet_min"],
                "bullet_max": blueprint["bullet_max"],
            }
            for blueprint in active_blueprints
        ],
        "allowed_skill_category_order": ordered_categories,
        "generation_constraints": {
            "top_and_experience_title_words": {
                "minimum": TITLE_WORD_MIN,
                "maximum": TITLE_WORD_MAX,
            },
            "summary_words_for_replacement_only": {
                "minimum": SUMMARY_WORD_MIN,
                "maximum": SUMMARY_WORD_MAX,
            },
            "experience_bullet_words_for_new_or_replacement_only": {
                "minimum": EXPERIENCE_BULLET_WORD_MIN,
                "maximum": EXPERIENCE_BULLET_WORD_MAX,
            },
            "existing_content_word_counts_are_not_review_findings": True,
        },
        "user_edit_context": (
            copy.deepcopy(user_edit_context)
            if isinstance(user_edit_context, dict)
            else {"has_manual_edits": False, "edited_paths": []}
        ),
        "input_authority": [
            "job.advertised_title",
            "job.description",
            "candidate_evidence_manifest",
            "advisory_analysis",
            "resume_under_review",
        ],
    }
    user_prompt = (
        "Review this structured input. Follow input_authority in order and return "
        "only the schema-valid patch review JSON.\n"
        + json.dumps(review_input, ensure_ascii=False, separators=(",", ":"))
    )
    started = time.perf_counter()
    attempts = 0
    last_limit = RESUME_QUALITY_AUDIT_MAX_OUTPUT_TOKENS
    retried_output_limit = False
    retried_network = False
    while True:
        attempts += 1
        try:
            raw_result = call_openai_structured_output(
                api_key=api_key,
                model=model,
                temperature=RESUME_TEMPERATURE,
                developer_prompt=build_ai_resume_quality_audit_prompt(),
                user_prompt=user_prompt,
                schema_name="resume_quality_audit_v2",
                schema=ai_resume_quality_audit_schema(
                    active_blueprints,
                    ordered_categories,
                ),
                max_output_tokens=last_limit,
                request_timeout_seconds=timeout_seconds,
                reasoning_effort=reasoning_effort,
                background=True,
                background_timeout_seconds=OPENAI_AUDIT_BACKGROUND_TIMEOUT_SECONDS,
                background_poll_interval_seconds=OPENAI_BACKGROUND_POLL_INTERVAL_SECONDS,
            )
            break
        except Exception as exc:
            if not retried_output_limit and _is_max_output_tokens_error(exc):
                retried_output_limit = True
                last_limit = RESUME_QUALITY_AUDIT_RETRY_MAX_OUTPUT_TOKENS
                continue
            if (
                not retried_network
                and not bool(getattr(exc, "openai_response_started", False))
                and _is_transient_audit_network_error(exc)
            ):
                retried_network = True
                time.sleep(1.0)
                continue
            try:
                exc.audit_attempt_count = attempts
            except (AttributeError, TypeError):
                pass
            raise
    repair_attempted = False
    try:
        validated = validate_resume_quality_audit_result(
            raw_result,
            current_resume=canonical_resume,
            analysis_payload=analysis_payload,
            active_blueprints=active_blueprints,
            candidate_profile=candidate_profile,
        )
    except ResumeQualityAuditRepairRequiredError as exc:
        repair_attempted = True
        attempts += 1
        raw_result = call_openai_structured_output(
            api_key=api_key,
            model=model,
            temperature=RESUME_TEMPERATURE,
            developer_prompt=build_ai_resume_quality_audit_prompt(),
            user_prompt=build_ai_resume_quality_audit_repair_prompt(
                review_input,
                raw_result,
                exc.diagnostics,
            ),
            schema_name="resume_quality_audit_v2_repair",
            schema=ai_resume_quality_audit_schema(
                active_blueprints,
                ordered_categories,
            ),
            max_output_tokens=RESUME_QUALITY_AUDIT_RETRY_MAX_OUTPUT_TOKENS,
            request_timeout_seconds=timeout_seconds,
            reasoning_effort=reasoning_effort,
            background=True,
            background_timeout_seconds=OPENAI_AUDIT_BACKGROUND_TIMEOUT_SECONDS,
            background_poll_interval_seconds=OPENAI_BACKGROUND_POLL_INTERVAL_SECONDS,
        )
        last_limit = RESUME_QUALITY_AUDIT_RETRY_MAX_OUTPUT_TOKENS
        validated = validate_resume_quality_audit_result(
            raw_result,
            current_resume=canonical_resume,
            analysis_payload=analysis_payload,
            active_blueprints=active_blueprints,
            candidate_profile=candidate_profile,
        )
    if isinstance(validated.get("review_basis"), dict):
        validated["review_basis"]["advertised_job_title"] = (
            authoritative_title or None
        )
    validated["model"] = model
    validated["reasoning_effort"] = reasoning_effort
    validated["attempt_count"] = attempts
    validated["max_output_tokens"] = last_limit
    validated["repair_attempted"] = repair_attempted
    validated["duration_ms"] = round((time.perf_counter() - started) * 1000)
    validated["token_usage"] = None
    validated["execution_mode"] = "background"
    return validated


def apply_resume_quality_audit_proposal(
    *,
    expected_base_hash: str,
    current_resume: dict,
    audit_result: dict,
    analysis_payload: dict,
    active_blueprints: list[dict],
    candidate_profile: dict | None = None,
    max_change_fraction: float = RESUME_QUALITY_AUDIT_MAX_CHANGE_FRACTION,
) -> dict:
    del max_change_fraction
    current = _canonical_editable_resume(current_resume, active_blueprints)
    actual_hash = canonical_json_hash(current)
    if not expected_base_hash or expected_base_hash != actual_hash:
        raise ResumeQualityAuditStaleConflictError(expected_base_hash, actual_hash)
    validated = validate_resume_quality_audit_result(
        audit_result,
        current_resume=current,
        analysis_payload=analysis_payload,
        active_blueprints=active_blueprints,
        candidate_profile=candidate_profile,
    )
    if validated["decision"] != "changes_suggested":
        raise ResumeQualityAuditValidationError(["Audit result has no applicable changes."])
    change_ids = {
        record["change_id"]
        for record in _quality_audit_change_records(validated["changes"])
    }
    proposal = _apply_quality_audit_changes(
        current,
        validated["changes"],
        active_blueprints,
    )
    issues = _quality_audit_resume_validation_issues(
        proposal,
        analysis_payload,
        active_blueprints,
    )
    if issues:
        raise ResumeQualityAuditValidationError(issues)
    if not change_ids:
        raise ResumeQualityAuditValidationError(["Audit result has no applicable changes."])
    return proposal


apply_resume_quality_proposal = apply_resume_quality_audit_proposal


def normalize_resume_quality_audit_decisions(
    decisions,
    change_ids: list[str],
) -> dict[str, str]:
    if not isinstance(decisions, dict):
        raise ValueError("decisions must map every change_id to accept or reject.")
    expected = set(change_ids)
    supplied = set(decisions)
    issues: list[str] = []
    if expected - supplied:
        issues.append("Missing review decisions: " + ", ".join(sorted(expected - supplied)) + ".")
    if supplied - expected:
        issues.append("Unknown review decisions: " + ", ".join(sorted(supplied - expected)) + ".")
    normalized = {
        change_id: str(decisions.get(change_id, "")).strip().lower()
        for change_id in change_ids
    }
    invalid = [
        change_id for change_id, decision in normalized.items()
        if decision not in {"accept", "reject"}
    ]
    if invalid:
        issues.append("Decisions must be accept or reject for: " + ", ".join(invalid) + ".")
    if issues:
        raise ValueError(" ".join(issues))
    return normalized


def resolve_resume_quality_audit_decisions(
    *,
    expected_base_hash: str,
    current_resume: dict,
    audit_result: dict,
    decisions,
    analysis_payload: dict,
    active_blueprints: list[dict],
    candidate_profile: dict | None = None,
    max_change_fraction: float = RESUME_QUALITY_AUDIT_MAX_CHANGE_FRACTION,
) -> tuple[dict, list[str], bool]:
    del max_change_fraction
    current = _canonical_editable_resume(current_resume, active_blueprints)
    actual_hash = canonical_json_hash(current)
    if not expected_base_hash or expected_base_hash != actual_hash:
        raise ResumeQualityAuditStaleConflictError(expected_base_hash, actual_hash)
    validated = validate_resume_quality_audit_result(
        audit_result,
        current_resume=current,
        analysis_payload=analysis_payload,
        active_blueprints=active_blueprints,
        candidate_profile=candidate_profile,
    )
    if validated["decision"] != "changes_suggested":
        raise ResumeQualityAuditValidationError(["Audit result has no unresolved changes."])
    change_ids = [
        record["change_id"]
        for record in _quality_audit_change_records(validated["changes"])
    ]
    normalized = normalize_resume_quality_audit_decisions(decisions, change_ids)
    accepted = {
        change_id for change_id, decision in normalized.items()
        if decision == "accept"
    }
    all_rejected = not accepted
    if all_rejected:
        return copy.deepcopy(current), change_ids, True
    selected = _selected_quality_audit_changes(validated["changes"], accepted)
    resolved = _apply_quality_audit_changes(current, selected, active_blueprints)
    issues = _quality_audit_resume_validation_issues(
        resolved,
        analysis_payload,
        active_blueprints,
    )
    if issues:
        raise ResumeQualityAuditValidationError(issues)
    return resolved, change_ids, False


def generate_resume_experience_from_analysis(
    *,
    api_key: str,
    job_description: str,
    analysis_payload: dict,
    core_payload: dict,
    revision_request: str = "",
    current_resume_content: str = "",
    memory_block: str = "",
    enabled_experience_keys: list[str] | None = None,
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    prompt_family_key = prompt_family_key_for_analysis(analysis_payload)
    compact_core = {
        "updated_title": str(core_payload.get("updated_title", "")).strip(),
        "updated_summary": str(core_payload.get("updated_summary", "")).strip(),
        "updated_skills": core_payload.get("updated_skills", []),
    }
    user_parts = [
        f"Job description:\n{job_description.strip()}",
        "Use the JD analysis and core resume sections below as the source of truth. Generate only the Professional Experience object matching the schema.",
        "JD analysis:",
        json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
        "Core resume sections:",
        json.dumps(compact_core, ensure_ascii=False, separators=(",", ":")),
    ]
    if revision_request.strip():
        user_parts.append(f"Current refinement request:\n{revision_request.strip()}")
    if current_resume_content.strip():
        user_parts.append(f"Current edited draft from the user:\n{current_resume_content.strip()}")
    if memory_block:
        user_parts.append(f"Previous session memory (maximum two turns):\n{memory_block}")

    blueprints = filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_experience_keys)

    def run_generation(extra_instruction: str = "") -> dict:
        prompt_parts = list(user_parts)
        if extra_instruction:
            prompt_parts.append(extra_instruction)
        return call_openai_structured_output(
            api_key=api_key,
            model=RESUME_MODEL,
            temperature=RESUME_TEMPERATURE,
            developer_prompt=build_ai_resume_experience_prompt(prompt_family_key),
            user_prompt="\n\n".join(prompt_parts),
            schema_name="resume_experience_generation",
            schema=ai_experience_schema(blueprints),
            max_output_tokens=with_output_headroom(5600, LARGE_OUTPUT_HEADROOM),
            request_timeout_seconds=OPENAI_RESUME_TIMEOUT_SECONDS,
            reasoning_effort="low",
        )

    experience_payload = run_generation()
    invalid_titles = collect_invalid_experience_titles(experience_payload, blueprints)
    if invalid_titles:
        retry_lines = [
            "Previous attempt failed because one or more experience title fields were invalid.",
            "Return only the role title text for each company.",
            "Do not repeat company name, location, dates, or metadata separators in the title field.",
            "Fix these exact title failures:",
        ]
        for failure in invalid_titles:
            raw_title = failure["raw_title"] or "<empty>"
            retry_lines.append(
                f"- {failure['company']}: returned '{raw_title}' ({failure['reason']}); replace it with only the job title."
            )
        experience_payload = run_generation("\n".join(retry_lines))

    validation_issues = validate_experience_subset_payload_with_analysis(
        experience_payload,
        blueprints,
        analysis_payload,
    )
    unsupported_tool_issues = [
        issue for issue in validation_issues
        if "introduces analyst tools not named in the JD" in issue
        or "introduces GTM tools not named in the JD" in issue
    ]
    evidence_issues = validate_generated_experience_evidence(experience_payload, blueprints)
    repair_issues = unsupported_tool_issues + evidence_issues
    if repair_issues:
        retry_lines = [
            "Previous attempt included unsupported claims in experience bullets.",
            "Use named tools only when they are grounded by the JD and supplied candidate evidence.",
            "Use a numeric metric only when that exact number appears in the immutable experience blueprint evidence.",
            "When no grounded number exists, remove the number and state a concrete qualitative outcome.",
            "Never invent, estimate, infer, or borrow a metric from the JD.",
            "Fix these exact issues:",
            *[f"- {issue}" for issue in repair_issues],
        ]
        experience_payload = run_generation("\n".join(retry_lines))

    experience_payload = sanitize_experience_payload_for_prompt_family(experience_payload, analysis_payload)
    final_evidence_issues = validate_generated_experience_evidence(experience_payload, blueprints)
    if final_evidence_issues:
        raise ValueError("Experience evidence validation failed: " + " | ".join(final_evidence_issues[:3]))
    experience_payload["_enabled_experience_keys"] = [blueprint["key"] for blueprint in blueprints]
    return experience_payload


def generate_experience_subset_from_analysis(
    *,
    api_key: str,
    analysis_payload: dict,
    blueprints: list[dict],
    model: str,
    timeout_seconds: int,
    preliminary_skills_payload: dict | None = None,
    core_payload: dict | None = None,
    revision_context: dict | None = None,
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    prompt_family_key = prompt_family_key_for_analysis(analysis_payload)
    skills_source = preliminary_skills_payload if preliminary_skills_payload is not None else (core_payload or {})
    preliminary_skills = {"updated_skills": normalize_updated_skills(skills_source.get("updated_skills", []))}
    user_parts = [
        "Analysis:",
        json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
        "Preliminary skills:",
        json.dumps(preliminary_skills, ensure_ascii=False, separators=(",", ":")),
        "Immutable experience blueprints:",
        json.dumps(blueprints, ensure_ascii=False, separators=(",", ":")),
    ]
    append_revision_context_to_prompt(user_parts, revision_context)
    def run_generation(extra_instruction: str = "") -> dict:
        if not blueprints:
            return {"experience": {}, "_enabled_experience_keys": []}
        prompt_parts = list(user_parts)
        if extra_instruction:
            prompt_parts.append(extra_instruction)
        return call_openai_structured_output(
            api_key=api_key,
            model=model,
            temperature=RESUME_TEMPERATURE,
            developer_prompt=build_ai_resume_experience_subset_prompt(blueprints, prompt_family_key),
            user_prompt="\n\n".join(prompt_parts),
            schema_name="resume_experience_subset_generation",
            schema=ai_experience_subset_schema(blueprints),
            max_output_tokens=with_output_headroom(5200 if len(blueprints) > 1 else 2800, LARGE_OUTPUT_HEADROOM if len(blueprints) > 1 else MEDIUM_OUTPUT_HEADROOM),
            request_timeout_seconds=timeout_seconds,
            reasoning_effort="low",
        )

    experience_payload = run_generation()
    invalid_titles = collect_invalid_experience_titles(experience_payload, blueprints)
    if invalid_titles:
        retry_lines = [
            "Previous attempt failed because one or more experience title fields were invalid.",
            "Return only the role title text for each company.",
            "Do not repeat company name, location, dates, or metadata separators in the title field.",
            "Fix these exact title failures:",
        ]
        for failure in invalid_titles:
            raw_title = failure["raw_title"] or "<empty>"
            retry_lines.append(
                f"- {failure['company']}: returned '{raw_title}' ({failure['reason']}); replace it with only the job title."
            )
        experience_payload = run_generation("\n".join(retry_lines))

    validation_issues = validate_experience_subset_payload_with_analysis(
        experience_payload,
        blueprints,
        analysis_payload,
    )
    unsupported_tool_issues = [
        issue for issue in validation_issues
        if "introduces analyst tools not named in the JD" in issue
        or "introduces GTM tools not named in the JD" in issue
    ]
    evidence_issues = validate_generated_experience_evidence(experience_payload, blueprints)
    repair_issues = unsupported_tool_issues + evidence_issues
    if repair_issues:
        retry_lines = [
            "Previous attempt included unsupported claims in experience bullets.",
            "Use named tools only when they are grounded by the JD and supplied candidate evidence.",
            "Use a numeric metric only when that exact number appears in the immutable experience blueprint evidence.",
            "When no grounded number exists, remove the number and state a concrete qualitative outcome.",
            "Never invent, estimate, infer, or borrow a metric from the JD.",
            "Fix these exact issues:",
            *[f"- {issue}" for issue in repair_issues],
        ]
        experience_payload = run_generation("\n".join(retry_lines))
    final_evidence_issues = validate_generated_experience_evidence(experience_payload, blueprints)
    if final_evidence_issues:
        raise ValueError("Experience evidence validation failed: " + " | ".join(final_evidence_issues[:3]))
    experience_payload["_enabled_experience_keys"] = [blueprint["key"] for blueprint in blueprints]
    return experience_payload


def generate_reachout_message(
    *,
    api_key: str,
    job_description: str,
    analysis_payload: dict,
    current_resume_content: str = "",
    recipient_name: str = "",
    target_company: str = "",
    target_role: str = "",
) -> dict:
    compact_analysis = compact_analysis_for_reachout(analysis_payload)
    resume_snapshot = extract_reachout_resume_snapshot(current_resume_content)
    resolved_company = str(target_company or "").strip()
    if not resolved_company:
        company_match = re.search(r"^\s*([A-Z][A-Za-z0-9&.,' -]{1,80})\s+is\s+", job_description.strip())
        if company_match:
            resolved_company = company_match.group(1).strip()
    resolved_role = str(target_role or compact_analysis.get("target_role", "")).strip()
    greeting_name = str(recipient_name or "").strip() or "there"

    user_parts = [
        "Write one LinkedIn reachout message for a recruiter or hiring manager.",
        "Keep it under 300 characters total.",
        "Match this shape exactly:",
        f"Hey {greeting_name}, keeping this short:",
        "I'm a <grounded candidate role> with experience in <2-3 grounded skills>.",
        "I'm interested in this role because <one specific, grounded fit reason>.",
        "Would you be open to a quick conversation? Thanks for your time!",
        f"Recipient name: {greeting_name}",
        f"Target company: {resolved_company or 'unknown'}",
        f"Target role: {resolved_role}",
        f"Core problem: {compact_analysis.get('core_problem', '')}",
        "Skills mentioned: " + ", ".join(compact_analysis.get("skills_mentioned", [])[:3]),
    ]
    if compact_analysis.get("behavioral_signals"):
        user_parts.append("Behavioral signals: " + ", ".join(compact_analysis["behavioral_signals"][:2]))
    if resume_snapshot["title"]:
        user_parts.append(f"Resume title: {resume_snapshot['title']}")
    if resume_snapshot["summary"]:
        user_parts.append(
            f"Resume summary: {resume_snapshot['summary']}"
        )

    message = call_openai_text_output(
        api_key=api_key,
        model=ANALYSIS_MODEL,
        temperature=RESUME_TEMPERATURE,
        developer_prompt=build_ai_reachout_prompt(),
        user_prompt="\n\n".join(user_parts),
        max_output_tokens=with_output_headroom(500, SMALL_OUTPUT_HEADROOM),
        request_timeout_seconds=OPENAI_RESUME_TIMEOUT_SECONDS,
        reasoning_effort="low",
    )
    message = str(message).strip().replace("\r\n", "\n").replace("\r", "\n")
    message = "\n".join(line.strip() for line in message.split("\n") if line.strip())
    return {"message": message, "char_count": len(message)}


def generate_followup_answer(
    *,
    api_key: str,
    job_description: str,
    analysis_payload: dict,
    question: str,
    resume_pdf_text: str,
    max_characters: int = 0,
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    user_parts = [
        f"Job description:\n{job_description.strip()}",
        "JD analysis:",
        json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
        f"Candidate resume from final PDF:\n{resume_pdf_text.strip()}",
        f"Follow-up question:\n{question.strip()}",
        "Answer as the candidate in first person.",
    ]
    if max_characters > 0:
        user_parts.append(
            f"The application field allows at most {max_characters} characters. "
            "Keep the complete answer naturally within that limit."
        )

    answer = call_openai_text_output(
        api_key=api_key,
        model=RESUME_MODEL,
        temperature=RESUME_TEMPERATURE,
        developer_prompt=build_ai_followup_prompt(),
        user_prompt="\n\n".join(user_parts),
        max_output_tokens=with_output_headroom(1800, MEDIUM_OUTPUT_HEADROOM),
        request_timeout_seconds=OPENAI_RESUME_TIMEOUT_SECONDS,
        reasoning_effort="low",
    ).strip()

    if not answer:
        raise RuntimeError("Follow-up answer generation returned an empty answer.")

    return {"answer": answer, "char_count": len(answer), "max_characters": max_characters or None}


def call_openai_resume_engine(
    job_description: str,
    revision_request: str,
    memory_turns: list[dict],
    current_resume_content: str = "",
    cached_analysis: dict | None = None,
    enabled_experience_keys: list[str] | None = None,
) -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    memory_block = "\n\n".join(compact_turn_for_prompt(turn) for turn in memory_turns if turn)
    timing: dict[str, int] = {}

    if cached_analysis:
        analysis_payload = cached_analysis
        timing["analysis_ms"] = 0
    else:
        started = time.perf_counter()
        try:
            analysis_payload = analyze_job_description(
                api_key=api_key,
                job_description=job_description,
            )
        except Exception as exc:
            raise AIStageError("analysis", f"JD analysis failed: {exc}", timing=timing) from exc
        timing["analysis_ms"] = int((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    try:
        parsed_resume = generate_resume_from_analysis(
            api_key=api_key,
            job_description=job_description,
            analysis_payload=analysis_payload,
            revision_request=revision_request,
            current_resume_content=current_resume_content,
            memory_block=memory_block,
            enabled_experience_keys=enabled_experience_keys,
        )
    except Exception as exc:
        timing["resume_ms"] = int((time.perf_counter() - started) * 1000)
        timing["total_ms"] = timing.get("analysis_ms", 0) + timing["resume_ms"]
        raise AIStageError(
            "resume_generation",
            f"Resume generation failed: {exc}",
            analysis=analysis_payload,
            timing=timing,
        ) from exc
    timing["resume_ms"] = int((time.perf_counter() - started) * 1000)
    timing["total_ms"] = timing.get("analysis_ms", 0) + timing["resume_ms"]

    issues = validate_model_payload(
        {"analysis": analysis_payload, "resume": parsed_resume},
        enabled_experience_keys,
    )
    if issues:
        raise AIStageError(
            "resume_generation",
            "Resume generation failed validation: " + " | ".join(issues[:3]),
            analysis=analysis_payload,
            timing=timing,
        )

    return {"analysis": analysis_payload, "resume": parsed_resume, "timing": timing}


def load_base_resume():
    """Load base resume template."""
    with open(BASE_RESUME_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_profile_template() -> dict:
    fallback = {
        "name": "",
        "contact": {"location": "", "phone": "", "email": ""},
        "application": {},
        "projects": [],
        "certifications": [],
        "experience_history": [
            {
                "key": blueprint["key"],
                "company": "",
                "location": "",
                "title": "",
                "dates": "",
                "enabled": False,
            }
            for blueprint in EXPERIENCE_BLUEPRINTS
        ],
    }
    return load_json_file(Path(PROFILE_TEMPLATE_FILE), fallback)


def default_profile_doc() -> dict:
    return normalize_profile(load_profile_template())


def load_permanent_profile_doc() -> dict | None:
    if not Path(PERMANENT_PROFILE_FILE).exists():
        return None
    return load_json_file(Path(PERMANENT_PROFILE_FILE), default_profile_doc())


def load_session_profile_doc() -> dict | None:
    if not Path(SESSION_PROFILE_FILE).exists():
        return None
    return load_json_file(Path(SESSION_PROFILE_FILE), {})


def save_permanent_profile_doc(profile: dict) -> None:
    write_json_file(Path(PERMANENT_PROFILE_FILE), profile)


def save_session_profile_doc(profile: dict) -> None:
    write_json_file(Path(SESSION_PROFILE_FILE), profile)


def clear_session_profile_doc() -> None:
    try:
        Path(SESSION_PROFILE_FILE).unlink(missing_ok=True)
    except Exception:
        pass


def has_permanent_profile_doc() -> bool:
    return Path(PERMANENT_PROFILE_FILE).exists()


def merge_experience_history_lists(base_history: list[dict] | None, override_history: list[dict] | None) -> list[dict]:
    base_entries = base_history if isinstance(base_history, list) else []
    raw_entries = override_history if isinstance(override_history, list) else []

    overrides_by_key: dict[str, dict] = {}
    positional_overrides: list[dict] = []
    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key and index < len(EXPERIENCE_BLUEPRINTS):
            key = EXPERIENCE_BLUEPRINTS[index]["key"]
        if key and key not in overrides_by_key:
            overrides_by_key[key] = item
        positional_overrides.append(item)

    merged_history: list[dict] = []
    for index, blueprint in enumerate(EXPERIENCE_BLUEPRINTS):
        base_entry = base_entries[index] if index < len(base_entries) and isinstance(base_entries[index], dict) else {}
        raw_entry = overrides_by_key.get(blueprint["key"])
        if not isinstance(raw_entry, dict) and index < len(positional_overrides):
            candidate = positional_overrides[index]
            if isinstance(candidate, dict):
                raw_entry = candidate

        merged_entry = {
            "key": blueprint["key"],
            "company": str(base_entry.get("company", "")).strip(),
            "location": str(base_entry.get("location", "")).strip(),
            "title": str(base_entry.get("title", "")).strip(),
            "dates": str(base_entry.get("dates", "")).strip(),
            "enabled": bool(base_entry.get("enabled", True)),
        }
        if isinstance(raw_entry, dict):
            for field in ("company", "location", "title", "dates"):
                if field in raw_entry:
                    merged_entry[field] = str(raw_entry.get(field, "")).strip()
            if "enabled" in raw_entry:
                merged_entry["enabled"] = bool(raw_entry.get("enabled", True))

        merged_history.append(merged_entry)

    return merged_history


def merge_profile_docs(base: dict, override: dict | None) -> dict:
    merged = json.loads(json.dumps(base))
    if not isinstance(override, dict):
        return merged

    for field in ("name",):
        if field in override:
            merged[field] = override.get(field, "")

    override_contact = override.get("contact")
    if isinstance(override_contact, dict):
        merged["contact"] = {
            **(merged.get("contact") or {}),
            **override_contact,
        }

    override_application = override.get("application")
    if isinstance(override_application, dict):
        merged["application"] = {
            **(merged.get("application") or {}),
            **override_application,
        }

    for field in ("projects", "certifications"):
        if field in override and isinstance(override.get(field), list):
            merged[field] = override.get(field)

    if "experience_history" in override and isinstance(override.get("experience_history"), list):
        merged["experience_history"] = merge_experience_history_lists(
            merged.get("experience_history"),
            override.get("experience_history"),
        )

    return merged


def profile_experience_history_from_resume(resume: dict) -> list[dict]:
    experience_entries = resume.get("experience") if isinstance(resume.get("experience"), list) else []
    history: list[dict] = []
    for index, blueprint in enumerate(EXPERIENCE_BLUEPRINTS):
        resume_entry = experience_entries[index] if index < len(experience_entries) and isinstance(experience_entries[index], dict) else {}
        history.append(
            {
                "key": blueprint["key"],
                "company": str(resume_entry.get("company", blueprint["company"])).strip() or blueprint["company"],
                "location": str(resume_entry.get("location", blueprint["location"])).strip() or blueprint["location"],
                "title": str(resume_entry.get("title", "")).strip(),
                "dates": str(resume_entry.get("dates", blueprint["dates"])).strip() or blueprint["dates"],
                "enabled": True,
            }
        )
    return history


def is_experience_history_entry_complete(entry: dict) -> bool:
    return all(str(entry.get(field, "")).strip() for field in ("company", "location", "title", "dates"))


def is_experience_history_entry_enabled(entry: dict) -> bool:
    return entry.get("enabled", True) is not False and is_experience_history_entry_complete(entry)


def current_experience_blueprints() -> list[dict]:
    active_profile = current_profile()
    saved_history = active_profile.get("experience_history") if isinstance(active_profile.get("experience_history"), list) else []
    saved_history_by_key = {
        str(entry.get("key", "")).strip(): entry
        for entry in saved_history
        if isinstance(entry, dict) and str(entry.get("key", "")).strip()
    }

    blueprints: list[dict] = []
    for blueprint in EXPERIENCE_BLUEPRINTS:
        override = saved_history_by_key.get(blueprint["key"], {})
        merged = dict(blueprint)
        merged["company"] = str(override.get("company", blueprint["company"])).strip() or blueprint["company"]
        merged["location"] = str(override.get("location", blueprint["location"])).strip() or blueprint["location"]
        merged["dates"] = str(override.get("dates", blueprint["dates"])).strip() or blueprint["dates"]
        merged["default_title"] = str(override.get("title", "")).strip()
        blueprints.append(merged)
    return blueprints


def normalize_enabled_experience_keys(payload: list[str] | None) -> list[str]:
    if payload is None:
        return list(EXPERIENCE_BLUEPRINT_KEYS)
    requested = [str(item).strip() for item in payload if str(item).strip()]
    requested_set = set(requested)
    return [key for key in EXPERIENCE_BLUEPRINT_KEYS if key in requested_set]


def filter_blueprints_by_enabled_keys(blueprints: list[dict], enabled_experience_keys: list[str] | None = None) -> list[dict]:
    enabled_keys = set(normalize_enabled_experience_keys(enabled_experience_keys))
    return [blueprint for blueprint in blueprints if blueprint["key"] in enabled_keys]


def normalize_experience_history_override(payload: list[dict] | None) -> list[dict]:
    raw_items = payload if isinstance(payload, list) else []
    raw_by_key = {
        str(item.get("key", "")).strip(): item
        for item in raw_items
        if isinstance(item, dict) and str(item.get("key", "")).strip()
    }

    normalized: list[dict] = []
    for blueprint in current_experience_blueprints():
        raw_item = raw_by_key.get(blueprint["key"], {})
        normalized.append(
            {
                "key": blueprint["key"],
                "company": str(raw_item.get("company", blueprint["company"])).strip() or blueprint["company"],
                "location": str(raw_item.get("location", blueprint["location"])).strip() or blueprint["location"],
                "title": str(raw_item.get("title", blueprint.get("default_title", ""))).strip(),
                "dates": str(raw_item.get("dates", blueprint["dates"])).strip() or blueprint["dates"],
                "enabled": bool(raw_item.get("enabled", True)),
            }
        )
    return normalized


def apply_experience_history_override(resume: dict, experience_history_override: list[dict] | None = None) -> dict:
    overrides = normalize_experience_history_override(experience_history_override)
    if not overrides or not isinstance(resume.get("experience"), list):
        return resume

    override_by_key = {entry["key"]: entry for entry in overrides}
    for index, entry in enumerate(resume["experience"]):
        if not isinstance(entry, dict) or index >= len(EXPERIENCE_BLUEPRINT_KEYS):
            continue
        override = override_by_key.get(EXPERIENCE_BLUEPRINT_KEYS[index], {})
        if not is_experience_history_entry_enabled(override):
            continue
        for field in ("company", "location", "dates"):
            value = str(override.get(field, "")).strip()
            if value:
                entry[field] = value
        override_title = str(override.get("title", "")).strip()
        current_title = str(entry.get("title", "")).strip()
        if override_title and not current_title:
            entry["title"] = override_title
    return resume


def apply_enabled_experience_filter(resume: dict, enabled_experience_keys: list[str] | None = None) -> dict:
    normalized_enabled_keys = normalize_enabled_experience_keys(enabled_experience_keys)
    enabled_keys = set(normalized_enabled_keys)
    if not isinstance(resume.get("experience"), list):
        return resume

    experience_entries = list(resume["experience"])
    raw_resume_keys = [
        str(item).strip()
        for item in (resume.get("_enabled_experience_keys") or [])
        if str(item).strip()
    ]

    filtered: list[dict] = []
    if len(experience_entries) == len(EXPERIENCE_BLUEPRINT_KEYS):
        for index, entry in enumerate(experience_entries):
            if EXPERIENCE_BLUEPRINT_KEYS[index] in enabled_keys:
                filtered.append(entry)
    elif raw_resume_keys and len(raw_resume_keys) == len(experience_entries):
        by_key = {key: entry for key, entry in zip(raw_resume_keys, experience_entries)}
        filtered = [by_key[key] for key in normalized_enabled_keys if key in by_key]
    elif all(isinstance(entry, dict) and str(entry.get("key", "")).strip() for entry in experience_entries):
        by_key = {str(entry.get("key", "")).strip(): entry for entry in experience_entries}
        filtered = [by_key[key] for key in normalized_enabled_keys if key in by_key]
    else:
        filtered = experience_entries

    resume["experience"] = filtered
    resume["_enabled_experience_keys"] = normalized_enabled_keys
    return resume


def safe_folder_name(title: str, output_root: str = None) -> str:
    """Create safe folder name from title, avoiding duplicates."""
    if output_root is None:
        output_root = OUTPUT_ROOT

    name = (title or "").strip() or "Resume"
    name = re.sub(r'[\\/*?:"<>|→]', " ", name)  # Also remove arrow character
    name = re.sub(r"\s+", " ", name).strip()
    # Truncate to 100 chars max (macOS limit is 255 but be safe)
    if len(name) > 100:
        name = name[:97] + "..."

    # Check if folder already exists, append counter if it does
    base_name = name
    counter = 1
    while os.path.exists(os.path.join(output_root, name)):
        # Folder exists, try with a counter
        if len(base_name) + len(str(counter)) + 4 > 100:  # + 4 for " (N)"
            truncated = base_name[:100 - len(str(counter)) - 4]
            name = f"{truncated} ({counter})"
        else:
            name = f"{base_name} ({counter})"
        counter += 1

    return name


def display_folder_name(company_name: str, title: str, custom_folder: str) -> str:
    if custom_folder:
        return custom_folder
    if company_name and title:
        return f"{company_name} - {title}"
    if company_name:
        return company_name
    return title or "Resume"


def require_within_output(path_value: str, must_exist: bool = True) -> Path:
    requested = Path(path_value).expanduser().resolve()
    output_root = Path(settings["output_directory"]).expanduser().resolve()

    if must_exist and not requested.exists():
        raise FileNotFoundError(str(requested))

    try:
        requested.relative_to(output_root)
    except ValueError as exc:
        raise PermissionError("Requested path is outside the configured output directory") from exc

    return requested


def start_pdf_conversion(
    docx_path: Path,
    pdf_path: Path,
    status_path: Path,
    *,
    delete_docx: bool = True,
) -> None:
    script_dir = Path(__file__).resolve().parent
    command = [
        sys.executable,
        str(script_dir / "convert_pdf_job.py"),
        "--docx", str(docx_path),
        "--pdf", str(pdf_path),
        "--status", str(status_path),
        "--timeout", "180",
    ]
    if delete_docx:
        command.append("--delete-docx")
    proc = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=(os.name != "nt"),
    )
    threading.Thread(target=proc.wait, daemon=True).start()


def profile_from_resume(resume: dict) -> dict:
    contact = resume.get("contact", {})
    return {
        "name": resume.get("name", ""),
        "contact": {
            "location": contact.get("location", ""),
            "phone": contact.get("phone", ""),
            "email": contact.get("email", ""),
        },
        "application": {},
        "projects": resume.get("projects", []),
        "certifications": resume.get("certifications", []),
        "experience_history": profile_experience_history_from_resume(resume),
    }


def current_profile() -> dict:
    default_profile = default_profile_doc()
    permanent_doc = load_permanent_profile_doc()
    permanent = normalize_profile(merge_profile_docs(default_profile, permanent_doc)) if permanent_doc else default_profile
    session_doc = load_session_profile_doc()
    session = normalize_profile(session_doc) if session_doc else None
    return normalize_profile(merge_profile_docs(permanent, session))


def _identity_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return normalized or uuid.uuid4().hex[:8]


def default_identity_profiles() -> list[dict]:
    profile_contact = (current_profile().get("contact") or {})
    return [
        {
            "id": "outlook",
            "label": "Outlook",
            "location": str(profile_contact.get("location", "")).strip(),
            "phone": str(profile_contact.get("phone", "")).strip(),
            "email": str(profile_contact.get("email", "")).strip(),
            "format_profile": "outlook",
        },
        dict(GMAIL_IDENTITY_DEFAULT),
    ]


def normalize_identity_profiles(payload: list[dict] | None) -> list[dict]:
    defaults = default_identity_profiles()
    default_by_id = {item["id"]: item for item in defaults}
    raw_items = payload if isinstance(payload, list) else []
    normalized: list[dict] = []
    seen_ids: set[str] = set()

    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            continue
        fallback = defaults[index] if index < len(defaults) else {}
        label = str(raw_item.get("label", fallback.get("label", ""))).strip() or str(fallback.get("label", "")).strip() or f"Identity {len(normalized) + 1}"
        identity_id = _identity_id(raw_item.get("id") or label)
        if identity_id in seen_ids:
            identity_id = f"{identity_id}-{len(normalized) + 1}"
        seen_ids.add(identity_id)
        format_profile = str(raw_item.get("format_profile", fallback.get("format_profile", "outlook"))).strip().lower()
        if format_profile not in {"outlook", "gmail"}:
            format_profile = "outlook"
        normalized.append(
            {
                "id": identity_id,
                "label": label,
                "location": str(raw_item.get("location", fallback.get("location", ""))).strip(),
                "phone": str(raw_item.get("phone", fallback.get("phone", ""))).strip(),
                "email": str(raw_item.get("email", fallback.get("email", ""))).strip(),
                "format_profile": format_profile,
            }
        )

    if not normalized:
        return defaults

    for default in defaults:
        if default["id"] in seen_ids:
            continue
        normalized.append(default)
    return normalized


def current_identity_profiles() -> list[dict]:
    return normalize_identity_profiles(settings.get("identities"))


def identity_profile_by_id(identity_id: str) -> dict:
    normalized_id = str(identity_id or "").strip().lower()
    identities = current_identity_profiles()
    if normalized_id:
        for item in identities:
            if item["id"] == normalized_id:
                return item
    return identities[0] if identities else default_identity_profiles()[0]


def apply_profile_overrides(resume: dict) -> dict:
    profile = current_profile()
    resume["name"] = profile.get("name") or resume.get("name", "")
    resume["contact"] = {
        **resume.get("contact", {}),
        **(profile.get("contact") or {}),
    }
    resume["projects"] = profile.get("projects", resume.get("projects", []))
    resume["certifications"] = profile.get("certifications", resume.get("certifications", []))
    profile_history = profile.get("experience_history") if isinstance(profile.get("experience_history"), list) else []
    if isinstance(resume.get("experience"), list) and profile_history:
        history_by_key = {
            str(entry.get("key", "")).strip(): entry
            for entry in profile_history
            if isinstance(entry, dict) and str(entry.get("key", "")).strip()
        }
        for index, entry in enumerate(resume["experience"]):
            if not isinstance(entry, dict) or index >= len(EXPERIENCE_BLUEPRINT_KEYS):
                continue
            override = history_by_key.get(EXPERIENCE_BLUEPRINT_KEYS[index], {})
            if is_experience_history_entry_enabled(override):
                for field in ("company", "location", "dates"):
                    value = str(override.get(field, "")).strip()
                    if value:
                        entry[field] = value
            override_title = str(override.get("title", "")).strip()
            current_title = str(entry.get("title", "")).strip()
            if override_title and not current_title:
                entry["title"] = override_title
    return resume


def normalize_profile(payload: dict) -> dict:
    contact = payload.get("contact") or {}
    application = normalize_application_profile(payload.get("application"))
    projects = payload.get("projects") if isinstance(payload.get("projects"), list) else []
    certifications = payload.get("certifications") if isinstance(payload.get("certifications"), list) else []
    experience_history = payload.get("experience_history") if isinstance(payload.get("experience_history"), list) else []

    normalized_projects = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        name = str(project.get("name", "")).strip()
        bullets = [str(item).strip() for item in project.get("bullets", []) if str(item).strip()]
        if name:
            normalized_projects.append({"name": name, "bullets": bullets})

    normalized_history = merge_experience_history_lists([], experience_history)

    return {
        "name": str(payload.get("name", "")).strip(),
        "contact": {
            "location": str(contact.get("location", "")).strip(),
            "phone": str(contact.get("phone", "")).strip(),
            "email": str(contact.get("email", "")).strip(),
        },
        "application": application,
        "projects": normalized_projects,
        "certifications": [str(item).strip() for item in certifications if str(item).strip()],
        "experience_history": normalized_history,
    }


APPLICATION_PROFILE_FIELDS = (
    "firstName", "middleName", "lastName", "addressLine1", "addressLine2", "city", "state",
    "postalCode", "country", "linkedinUrl", "githubUrl", "portfolioUrl", "websiteUrl",
    "yearsOfExperience", "currentTitle", "currentCompany", "highestDegree", "graduationYear",
    "salaryExpectation", "noticePeriod", "relocationWilling", "workAuthorization",
    "sponsorshipRequired", "workAuthExpiration", "j1Visa",
)


def normalize_application_profile(payload: dict | None) -> dict:
    raw = payload if isinstance(payload, dict) else {}
    normalized = {field: str(raw.get(field, "")).strip() for field in APPLICATION_PROFILE_FIELDS}
    normalized["autoFillEnabled"] = raw.get("autoFillEnabled", True) is not False
    custom_answers = raw.get("customAnswers") if isinstance(raw.get("customAnswers"), dict) else {}
    normalized["customAnswers"] = {
        str(question).strip(): str(answer).strip()
        for question, answer in custom_answers.items()
        if str(question).strip() and str(answer).strip()
    }
    return normalized


def autofill_profile_data(identity_id: str = "") -> dict:
    profile = current_profile()
    application = normalize_application_profile(profile.get("application"))
    identity = identity_profile_by_id(identity_id)
    name_parts = str(profile.get("name", "")).strip().split()
    first_name = application.get("firstName") or (name_parts[0] if name_parts else "")
    last_name = application.get("lastName") or (name_parts[-1] if len(name_parts) > 1 else "")
    middle_name = application.get("middleName") or (" ".join(name_parts[1:-1]) if len(name_parts) > 2 else "")

    history = [
        item for item in profile.get("experience_history", [])
        if isinstance(item, dict) and is_experience_history_entry_enabled(item)
    ]
    latest = history[0] if history else {}
    return {
        **application,
        "fullName": str(profile.get("name", "")).strip(),
        "firstName": first_name,
        "middleName": middle_name,
        "lastName": last_name,
        "email": str(identity.get("email", "")).strip(),
        "phone": str(identity.get("phone", "")).strip(),
        "currentLocation": str(identity.get("location", "")).strip() or str((profile.get("contact") or {}).get("location", "")).strip(),
        "currentTitle": application.get("currentTitle") or str(latest.get("title", "")).strip(),
        "currentCompany": application.get("currentCompany") or str(latest.get("company", "")).strip(),
        "identityId": identity.get("id", ""),
        "identityLabel": identity.get("label", ""),
    }


def validate_profile_payload(profile: dict) -> list[str]:
    issues: list[str] = []
    if not str(profile.get("name", "")).strip():
        issues.append("Name is required.")

    contact = profile.get("contact") or {}
    for field, label in (("location", "Location"), ("phone", "Phone"), ("email", "Email")):
        if not str(contact.get(field, "")).strip():
            issues.append(f"{label} is required.")

    projects = profile.get("projects") if isinstance(profile.get("projects"), list) else []
    certifications = profile.get("certifications") if isinstance(profile.get("certifications"), list) else []
    experience_history = profile.get("experience_history") if isinstance(profile.get("experience_history"), list) else []

    if len(projects) < 1:
        issues.append("At least one project is required.")
    if len(certifications) < 1:
        issues.append("At least one certification is required.")
    if not any(is_experience_history_entry_enabled(entry) for entry in experience_history if isinstance(entry, dict)):
        issues.append("At least one enabled work experience role with all fields filled is required.")

    return issues


def profile_response_payload() -> dict:
    profile = current_profile()
    return {
        "profile": profile,
        "onboarding_required": not has_permanent_profile_doc(),
        "has_permanent_profile": has_permanent_profile_doc(),
        "session_active": Path(SESSION_PROFILE_FILE).exists(),
        "permanent_profile_file": str(PERMANENT_PROFILE_FILE),
        "session_profile_file": str(SESSION_PROFILE_FILE),
    }


def profile_doc_needs_normalization(profile_doc: dict | None) -> bool:
    if not isinstance(profile_doc, dict):
        return False
    experience_history = profile_doc.get("experience_history")
    if not isinstance(experience_history, list):
        return False
    if len(experience_history) != len(EXPERIENCE_BLUEPRINTS):
        return True
    return any(
        not isinstance(item, dict) or not str(item.get("key", "")).strip()
        for item in experience_history
    )


def migrate_legacy_profile_if_needed() -> None:
    legacy_profile = settings.get("profile")
    if has_permanent_profile_doc() or not isinstance(legacy_profile, dict) or not legacy_profile:
        settings.pop("profile", None)
        save_settings(settings)
        return

    normalized_legacy = normalize_profile(legacy_profile)
    save_permanent_profile_doc(normalized_legacy)
    settings.pop("profile", None)
    save_settings(settings)


def normalize_profile_documents_if_needed() -> None:
    permanent_doc = load_permanent_profile_doc()
    if profile_doc_needs_normalization(permanent_doc):
        save_permanent_profile_doc(normalize_profile(permanent_doc))

    session_doc = load_session_profile_doc()
    if profile_doc_needs_normalization(session_doc):
        save_session_profile_doc(normalize_profile(session_doc))


if os.getenv("RESUME_PRESERVE_SESSION_PROFILE", "").strip().lower() not in {"1", "true", "yes"}:
    clear_session_profile_doc()
migrate_legacy_profile_if_needed()
normalize_profile_documents_if_needed()


EXTENSION_GENERATING_STATUSES = {"queued", "analyzing", "generating_core", "generating_experience", "reviewing"}
extension_worker_event = threading.Event()
extension_worker_started = False
extension_worker_lock = threading.Lock()
extension_worker_threads: list[threading.Thread] = []


def extension_generation_worker_count(value: str | None = None) -> int:
    raw_value = value if value is not None else os.getenv("EXTENSION_GENERATION_WORKERS", "2")
    try:
        worker_count = int(str(raw_value).strip())
    except (TypeError, ValueError):
        worker_count = 2
    return max(1, min(worker_count, 4))


def experience_blueprints_from_snapshot(draft: dict) -> list[dict]:
    history = draft.get("experience_history_snapshot") if isinstance(draft.get("experience_history_snapshot"), list) else []
    by_key = {
        str(item.get("key", "")).strip(): item
        for item in history
        if isinstance(item, dict) and str(item.get("key", "")).strip()
    }
    blueprints: list[dict] = []
    for blueprint in EXPERIENCE_BLUEPRINTS:
        saved = by_key.get(blueprint["key"], {})
        merged = dict(blueprint)
        merged["company"] = str(saved.get("company", blueprint["company"])).strip() or blueprint["company"]
        merged["location"] = str(saved.get("location", blueprint["location"])).strip() or blueprint["location"]
        merged["dates"] = str(saved.get("dates", blueprint["dates"])).strip() or blueprint["dates"]
        merged["default_title"] = str(saved.get("title", "")).strip()
        blueprints.append(merged)
    return blueprints


def draft_resume_snapshot(draft: dict) -> dict:
    content = str(draft.get("resume_content", "")).strip()
    resume = parse_updated_content_to_resume(content, load_base_resume())
    enabled_keys = normalize_enabled_experience_keys(draft.get("enabled_experience_keys"))
    if len(enabled_keys) != len(EXPERIENCE_BLUEPRINT_KEYS) and isinstance(resume.get("experience"), list):
        parsed_active_entries = list(resume["experience"][:len(enabled_keys)])
        active_by_key = {key: parsed_active_entries[index] for index, key in enumerate(enabled_keys) if index < len(parsed_active_entries)}
        resume["experience"] = [
            active_by_key.get(blueprint["key"], {
                "company": blueprint["company"],
                "location": blueprint["location"],
                "dates": blueprint["dates"],
                "title": "",
                "bullets": [],
            })
            for blueprint in EXPERIENCE_BLUEPRINTS
        ]
    profile = draft.get("profile_snapshot") if isinstance(draft.get("profile_snapshot"), dict) else {}
    resume["name"] = str(profile.get("name", resume.get("name", ""))).strip()
    resume["projects"] = profile.get("projects") if isinstance(profile.get("projects"), list) else resume.get("projects", [])
    resume["certifications"] = profile.get("certifications") if isinstance(profile.get("certifications"), list) else resume.get("certifications", [])

    contact = draft.get("contact_snapshot") if isinstance(draft.get("contact_snapshot"), dict) else {}
    profile_contact = profile.get("contact") if isinstance(profile.get("contact"), dict) else {}
    resume["contact"] = {
        **(resume.get("contact") or {}),
        **{
            key: str(contact.get(key, profile_contact.get(key, ""))).strip()
            for key in ("location", "phone", "email")
            if str(contact.get(key, profile_contact.get(key, ""))).strip()
        },
    }

    history = draft.get("experience_history_snapshot") if isinstance(draft.get("experience_history_snapshot"), list) else []
    history_by_key = {
        str(item.get("key", "")).strip(): item
        for item in history
        if isinstance(item, dict) and str(item.get("key", "")).strip()
    }
    for index, entry in enumerate(resume.get("experience", [])):
        if index >= len(EXPERIENCE_BLUEPRINT_KEYS) or not isinstance(entry, dict):
            continue
        saved = history_by_key.get(EXPERIENCE_BLUEPRINT_KEYS[index], {})
        for field in ("company", "location", "dates"):
            value = str(saved.get(field, "")).strip()
            if value:
                entry[field] = value
        if not str(entry.get("title", "")).strip() and str(saved.get("title", "")).strip():
            entry["title"] = str(saved["title"]).strip()

    return apply_enabled_experience_filter(resume, enabled_keys)


def extension_draft_payload(draft: dict | None) -> dict | None:
    if not draft:
        return None
    refreshed = dict(draft)
    status_path = str(refreshed.get("pdf_status_path", "")).strip()
    if refreshed.get("status") == "pdf_generating" and status_path:
        try:
            pdf_status = get_conversion_status(status_path)
            state = str(pdf_status.get("state", "")).lower()
            if state in {"completed", "success"}:
                revision_matches = int(refreshed.get("pdf_revision") or 0) == int(refreshed.get("resume_revision") or 1)
                finished_at = pdf_status.get("finished_at")
                generated_at = datetime.fromtimestamp(float(finished_at), timezone.utc) if finished_at else datetime.now(timezone.utc)
                refreshed = extension_drafts.update(
                    refreshed["id"],
                    {
                        "status": "pdf_ready" if revision_matches else "ready",
                        "stage": "complete",
                        "pdf_path": str(pdf_status.get("pdf", "")).strip() or refreshed.get("pdf_path", ""),
                        "pdf_stale": not revision_matches,
                        "pdf_generated_at": generated_at,
                    },
                )
            elif state in {"failed", "error"}:
                refreshed = extension_drafts.update(
                    refreshed["id"],
                    {
                        "status": "failed",
                        "error_stage": "pdf_generation",
                        "error_message": str(pdf_status.get("error", "PDF conversion failed.")),
                    },
                )
        except Exception:
            pass
    if str(refreshed.get("resume_content", "")).strip():
        try:
            refreshed["preview"] = draft_resume_snapshot(refreshed)
        except Exception as exc:
            refreshed["preview_error"] = str(exc)
    refreshed["review_groups"] = []
    if refreshed.get("audit_status") == "changes_suggested":
        audit_result = refreshed.get("audit_result")
        if isinstance(audit_result, dict):
            refreshed["review_groups"] = copy.deepcopy(
                audit_result.get("review_groups") or []
            )
    return refreshed


def run_extension_ai_stage(call):
    while True:
        with extension_ai_stage_gate_lock:
            if not extension_drafts.has_duplicate_review():
                break
        extension_worker_event.wait(timeout=1.0)
        extension_worker_event.clear()
    return call()


def create_extension_draft_with_gate(
    context: dict,
    snapshot: dict,
    duplicate_count: int,
) -> dict:
    with extension_ai_stage_gate_lock:
        return extension_drafts.create(context, snapshot, duplicate_count)


def extension_canonical_resume(draft: dict, blueprints: list[dict]) -> dict:
    experience = {}
    experience.update((draft.get("experience_recent") or {}).get("experience", {}))
    experience.update((draft.get("experience_older") or {}).get("experience", {}))
    return _canonical_editable_resume(
        {
            **merge_core_sections(draft.get("title_summary") or {}, draft.get("skills") or {}),
            "experience": experience,
        },
        blueprints,
    )


def extension_resume_version_payload(
    draft: dict,
    canonical_resume: dict,
    *,
    revision: int,
) -> dict:
    return {
        "resume": copy.deepcopy(canonical_resume),
        "title_summary": copy.deepcopy(draft.get("title_summary") or {}),
        "skills": copy.deepcopy(draft.get("skills") or {}),
        "experience_recent": copy.deepcopy(
            draft.get("experience_recent") or {}
        ),
        "experience_older": copy.deepcopy(
            draft.get("experience_older") or {}
        ),
        "resume_content": str(draft.get("resume_content", "")),
        "resume_snapshot": copy.deepcopy(draft.get("resume_snapshot") or {}),
        "revision": int(revision or 1),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def run_extension_generation_task(task: dict) -> None:
    task_id = task["task_id"]
    draft = task["draft"]
    draft_id = draft["id"]
    stage = "analysis"
    try:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise AIStageError("analysis", "OPENAI_API_KEY is not configured")

        enabled_keys = normalize_enabled_experience_keys(draft.get("enabled_experience_keys"))
        blueprints = filter_blueprints_by_enabled_keys(experience_blueprints_from_snapshot(draft), enabled_keys)

        analysis_payload = draft.get("analysis") or {}
        if not analysis_payload:
            extension_drafts.checkpoint(task_id, draft_id, "analysis", {"status": "analyzing"})
            analysis_payload = run_extension_ai_stage(
                lambda: analyze_job_description(
                    api_key=api_key,
                    job_description=draft["job_description"],
                )
            )
            analysis_payload = normalize_analysis_payload(analysis_payload)
            draft = extension_drafts.checkpoint(task_id, draft_id, "core", {
                "analysis": analysis_payload,
                "status": "generating_core",
            })

        original_skill_route = str(analysis_payload.get("skill_category_order_key", "")).strip()
        original_prompt_route = str(analysis_payload.get("prompt_family_key", "")).strip()
        normalized_analysis = normalize_analysis_payload(analysis_payload)
        route_changed = (
            bool(original_skill_route or original_prompt_route)
            and (
                original_skill_route != normalized_analysis["skill_category_order_key"]
                or original_prompt_route != normalized_analysis["prompt_family_key"]
            )
        )
        analysis_payload = normalized_analysis
        if route_changed:
            draft = extension_drafts.update(draft_id, {
                "analysis": analysis_payload,
                "title_summary": {},
                "skills": {},
                "experience_recent": {},
                "experience_older": {},
                "resume_content": "",
                "resume_snapshot": {},
                "audit_status": "not_started",
                "audit_result": None,
                "audit_proposal": None,
            })
        elif draft.get("analysis") != analysis_payload:
            draft = extension_drafts.update(draft_id, {"analysis": analysis_payload})

        if draft.get("source") == "mcp":
            source_metadata = dict(draft.get("source_metadata") or {})
            company_name = str(
                draft.get("company_name") or analysis_payload.get("company_name") or ""
            ).strip()
            role_title = str(
                draft.get("role_title") or analysis_payload.get("target_role") or ""
            ).strip()
            context_values = {
                "company_name": company_name,
                "role_title": role_title,
                "source_metadata": {
                    **source_metadata,
                    "context_resolved": bool(company_name and role_title),
                },
            }
            draft = extension_drafts.update(draft_id, context_values)
            if not company_name or not role_title:
                missing = []
                if not company_name:
                    missing.append("company")
                if not role_title:
                    missing.append("role title")
                raise AIStageError(
                    "context_resolution",
                    "The job analysis could not determine the " + " and ".join(missing) + ".",
                )

            if not source_metadata.get("duplicate_checked"):
                history = tracker_company_history(company_name)
                source_metadata = {
                    **source_metadata,
                    "context_resolved": True,
                    "duplicate_checked": True,
                }
                if int(history.get("count", 0)) and draft.get("duplicate_decision") != "continue":
                    extension_drafts.pause_task_for_duplicate(
                        task_id,
                        draft_id,
                        {
                            "company_name": company_name,
                            "role_title": role_title,
                            "source_metadata": source_metadata,
                        },
                    )
                    extension_worker_event.set()
                    return
                draft = extension_drafts.update(
                    draft_id,
                    {"source_metadata": source_metadata},
                )

        stage = "preliminary_skills"
        skills_payload = draft.get("skills") or {}
        if not skills_payload:
            skills_payload = run_extension_ai_stage(
                lambda: generate_skills_from_analysis(
                    api_key=api_key,
                    analysis_payload=analysis_payload,
                )
            )
        skills_payload["updated_skills"] = normalize_updated_skills(skills_payload.get("updated_skills", []))
        skill_issues = validate_skills_only_payload(skills_payload, analysis_payload)
        if skill_issues:
            raise AIStageError("preliminary_skills", "Preliminary skills failed validation: " + " | ".join(skill_issues[:3]))
        draft = extension_drafts.checkpoint(task_id, draft_id, "experience", {
            "skills": skills_payload,
            "status": "generating_experience",
        })

        stage = "experience_generation"
        recent_keys = set(EXPERIENCE_BLUEPRINT_KEYS[:2])
        recent_blueprints = [item for item in blueprints if item["key"] in recent_keys]
        older_blueprints = [item for item in blueprints if item["key"] not in recent_keys]
        recent_payload = draft.get("experience_recent") or {}
        older_payload = draft.get("experience_older") or {}

        def generate_subset(subset_blueprints: list[dict]) -> dict:
            if not subset_blueprints:
                return {"experience": {}}
            return run_extension_ai_stage(
                lambda: generate_experience_subset_from_analysis(
                    api_key=api_key,
                    analysis_payload=analysis_payload,
                    preliminary_skills_payload=skills_payload,
                    blueprints=subset_blueprints,
                    model=RESUME_MODEL,
                    timeout_seconds=OPENAI_RESUME_TIMEOUT_SECONDS,
                )
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            recent_future = None if recent_payload else executor.submit(generate_subset, recent_blueprints)
            older_future = None if older_payload else executor.submit(generate_subset, older_blueprints)
            if recent_future:
                recent_payload = recent_future.result()
            if older_future:
                older_payload = older_future.result()

        experience_issues = (
            validate_experience_subset_payload_with_analysis(recent_payload, recent_blueprints, analysis_payload)
            + validate_experience_subset_payload_with_analysis(older_payload, older_blueprints, analysis_payload)
        )
        if experience_issues:
            raise AIStageError("experience_generation", "Experience generation failed validation: " + " | ".join(experience_issues[:3]))
        combined_experience = {"experience": {}}
        combined_experience["experience"].update(recent_payload.get("experience", {}))
        combined_experience["experience"].update(older_payload.get("experience", {}))
        combined_experience["_enabled_experience_keys"] = enabled_keys
        draft = extension_drafts.checkpoint(task_id, draft_id, "synthesis", {
            "experience_recent": recent_payload,
            "experience_older": older_payload,
            "status": "reviewing",
        })

        stage = "final_synthesis"
        title_summary = draft.get("title_summary") or {}
        if not title_summary:
            synthesized = run_extension_ai_stage(
                lambda: generate_final_synthesis_from_analysis(
                    api_key=api_key,
                    job_description=draft["job_description"],
                    analysis_payload=analysis_payload,
                    preliminary_skills_payload=skills_payload,
                    combined_experience_payload=combined_experience,
                    active_blueprints=blueprints,
                )
            )
            synthesis_issues = validate_final_synthesis_payload(synthesized, blueprints, analysis_payload)
            if synthesis_issues:
                raise AIStageError("final_synthesis", "Final synthesis failed validation: " + " | ".join(synthesis_issues[:3]))
            title_summary = {
                "updated_title": synthesized["updated_title"],
                "updated_summary": synthesized["updated_summary"],
            }
            skills_payload = {"updated_skills": synthesized["updated_skills"]}
            recent_payload = apply_reviewed_titles_to_experience_payload(recent_payload, synthesized)
            older_payload = apply_reviewed_titles_to_experience_payload(older_payload, synthesized)

        reviewed_core = merge_core_sections(title_summary, skills_payload)
        reviewed_core["_analysis"] = analysis_payload
        reviewed_core["_enabled_experience_keys"] = enabled_keys
        reviewed_experience = {"experience": {}}
        reviewed_experience["experience"].update(recent_payload.get("experience", {}))
        reviewed_experience["experience"].update(older_payload.get("experience", {}))
        reviewed_experience["_enabled_experience_keys"] = enabled_keys
        final_content = format_generated_resume_text(merge_resume_payloads(reviewed_core, reviewed_experience), blueprints)
        draft = extension_drafts.checkpoint(task_id, draft_id, "audit", {
            "title_summary": title_summary,
            "skills": skills_payload,
            "experience_recent": recent_payload,
            "experience_older": older_payload,
            "resume_content": final_content,
            "audit_status": "running",
            "status": "reviewing",
        })
        final_draft = {
            **draft,
            "resume_content": final_content,
            "title_summary": title_summary,
            "skills": skills_payload,
            "experience_recent": recent_payload,
            "experience_older": older_payload,
        }
        preview = draft_resume_snapshot(final_draft)
        canonical_resume = extension_canonical_resume(final_draft, blueprints)
        base_revision = int(draft.get("resume_revision") or 1)
        original_draft = {
            **final_draft,
            "resume_snapshot": preview,
        }
        resume_versions = copy.deepcopy(draft.get("resume_versions") or {})
        resume_versions["original"] = extension_resume_version_payload(
            original_draft,
            canonical_resume,
            revision=base_revision,
        )
        active_resume_version = "original"
        final_resume_values = {"resume_snapshot": preview}
        stage = "quality_audit"
        try:
            audit_result = run_extension_ai_stage(
                lambda: generate_resume_quality_audit(
                    api_key=api_key,
                    job_description=draft["job_description"],
                    analysis_payload=analysis_payload,
                    current_resume=canonical_resume,
                    active_blueprints=blueprints,
                    candidate_profile=draft.get("profile_snapshot") or {},
                    advertised_job_title=draft.get("role_title", ""),
                    user_edit_context={
                        "has_manual_edits": int(draft.get("resume_revision") or 1) > 1,
                        "edited_paths": [],
                    },
                )
            )
            if audit_result["decision"] == "changes_suggested":
                reviewed_resume = apply_resume_quality_audit_proposal(
                    expected_base_hash=audit_result["base_hash"],
                    current_resume=canonical_resume,
                    audit_result=audit_result,
                    analysis_payload=analysis_payload,
                    active_blueprints=blueprints,
                    candidate_profile=draft.get("profile_snapshot") or {},
                )
                reviewed_values = extension_audit_values_from_resume(
                    original_draft,
                    reviewed_resume,
                    enabled_keys,
                )
                reviewed_revision = base_revision + 1
                reviewed_draft = {
                    **original_draft,
                    **reviewed_values,
                    "resume_revision": reviewed_revision,
                }
                resume_versions["luna_reviewed"] = (
                    extension_resume_version_payload(
                        reviewed_draft,
                        reviewed_resume,
                        revision=reviewed_revision,
                    )
                )
                active_resume_version = "luna_reviewed"
                accepted_change_ids = [
                    record["change_id"]
                    for record in _quality_audit_change_records(
                        audit_result.get("changes") or {}
                    )
                ]
                audit_result = {
                    **audit_result,
                    "accepted_change_ids": accepted_change_ids,
                    "rejected_change_ids": [],
                    "auto_applied": True,
                }
                final_resume_values = {
                    **reviewed_values,
                    "resume_revision": reviewed_revision,
                }
                audit_status = "applied"
                audit_applied_at = datetime.now(timezone.utc)
            else:
                resume_versions["luna_reviewed"] = (
                    extension_resume_version_payload(
                        original_draft,
                        canonical_resume,
                        revision=base_revision,
                    )
                )
                active_resume_version = "luna_reviewed"
                audit_status = audit_result["decision"]
                audit_applied_at = None
            audit_values = {
                "audit_status": audit_status,
                "audit_result": audit_result,
                "audit_proposal": None,
                "audit_base_revision": base_revision,
                "audit_base_hash": audit_result["base_hash"],
                "audit_created_at": datetime.now(timezone.utc),
                "audit_applied_at": audit_applied_at,
            }
        except Exception as audit_exc:
            audit_values = {
                "audit_status": "technical_failed",
                "audit_result": _quality_audit_failure_metadata(audit_exc),
                "audit_proposal": None,
                "audit_base_revision": base_revision,
                "audit_base_hash": canonical_json_hash(canonical_resume),
                "audit_created_at": datetime.now(timezone.utc),
                "audit_applied_at": None,
            }
        extension_drafts.complete_task(task_id, draft_id, {
            **final_resume_values,
            "resume_versions": resume_versions,
            "active_resume_version": active_resume_version,
            "pdf_stale": False,
            **audit_values,
        })
    except Exception as exc:
        error_stage = exc.stage if isinstance(exc, AIStageError) else stage
        extension_drafts.fail_task(task_id, draft_id, error_stage, str(exc))


def extension_worker_loop(
    stop_event: threading.Event | None = None,
    draft_store: ExtensionDraftStore | None = None,
    task_runner=None,
    wake_event: threading.Event | None = None,
) -> None:
    store = draft_store or extension_drafts
    runner = task_runner or run_extension_generation_task
    signal = wake_event or extension_worker_event
    while stop_event is None or not stop_event.is_set():
        try:
            if store.has_duplicate_review():
                signal.wait(timeout=1.0)
                signal.clear()
                continue
            task = store.next_task()
            if task:
                runner(task)
                continue
        except Exception as exc:
            print(f"Extension draft worker error: {exc}")
        signal.wait(timeout=1.0)
        signal.clear()


def ensure_extension_worker_started() -> None:
    global extension_worker_started, extension_worker_threads
    with extension_worker_lock:
        if extension_worker_started:
            return
        extension_drafts.recover_interrupted()
        worker_count = extension_generation_worker_count()
        extension_worker_threads = [
            threading.Thread(
                target=extension_worker_loop,
                name=f"resume-draft-worker-{index + 1}",
                daemon=True,
            )
            for index in range(worker_count)
        ]
        extension_worker_started = True
        for worker in extension_worker_threads:
            worker.start()


def extension_profile_snapshot(identity_id: str, enabled_keys_payload) -> dict:
    profile = current_profile()
    identity = identity_profile_by_id(identity_id)
    complete_keys = [
        str(item.get("key", "")).strip()
        for item in profile.get("experience_history", [])
        if isinstance(item, dict) and is_experience_history_entry_enabled(item)
    ]
    requested = normalize_enabled_experience_keys(enabled_keys_payload) if enabled_keys_payload is not None else complete_keys
    enabled_keys = [key for key in requested if key in complete_keys]
    if not enabled_keys:
        raise ValueError("Enable at least one complete experience role in Profile.")
    return {
        "identity_id": identity.get("id", ""),
        "enabled_experience_keys": enabled_keys,
        "profile_snapshot": profile,
        "contact_snapshot": identity,
        "experience_history_snapshot": profile.get("experience_history", []),
    }


def generate_extension_pdf(draft: dict, *, preserve_docx: bool = False) -> dict:
    audit_status = str(draft.get("audit_status") or "not_started").strip().lower()
    if audit_status not in AI_PDF_ALLOWED_AUDIT_STATUSES:
        raise ExtensionPdfAuditConflict(audit_status)
    if draft.get("status") not in {"ready", "pdf_ready"}:
        raise ValueError("The resume must finish generating before creating a PDF.")
    if not str(draft.get("resume_content", "")).strip():
        raise ValueError("Resume content is required.")
    resume = draft_resume_snapshot(draft)
    errors, _warnings = validate_updated_content(draft["resume_content"])
    if errors:
        raise ValueError(f"Validation failed: {errors[0]}")
    identity = draft.get("contact_snapshot") if isinstance(draft.get("contact_snapshot"), dict) else {}
    format_profile = str(identity.get("format_profile", "outlook")).strip() or "outlook"
    title = str(resume.get("title", "Resume")).strip() or "Resume"
    folder_name = safe_folder_name(display_folder_name(draft.get("company_name", ""), title, ""), settings["output_directory"])
    out_dir = Path(settings["output_directory"]) / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / "tharun manikonda resume.docx"
    pdf_path = out_dir / "tharun manikonda resume.pdf"
    status_path = out_dir / "pdf_status.json"
    build_resume_docx(resume, str(docx_path), format_profile=format_profile)
    start_pdf_conversion(
        docx_path,
        pdf_path,
        status_path,
        delete_docx=not preserve_docx,
    )
    return extension_drafts.materialize_pdf(draft["id"], {
        "status": "pdf_generating",
        "stage": "pdf_generation",
        "resume_snapshot": resume,
        "docx_path": str(docx_path),
        "pdf_path": str(pdf_path),
        "output_dir": str(out_dir),
        "pdf_status_path": str(status_path),
        "pdf_stale": False,
        "pdf_revision": int(draft.get("resume_revision") or 1),
        "pdf_generated_at": None,
        "error_stage": "",
        "error_message": "",
    })


def get_conversion_status(status_path: str) -> dict:
    """Get PDF conversion status."""
    status_file = require_within_output(status_path, must_exist=False)
    if not status_file.exists():
        return {"state": "pending"}

    with open(status_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    """Main page."""
    ok, msg = get_pdf_conversion_status()
    return render_template(
        "index.html",
        pdf_conversion_ready=ok,
        pdf_conversion_status=msg
    )


@app.route("/api/validate", methods=["POST"])
def validate():
    """Validate resume content."""
    data = request.get_json()
    content = data.get("content", "").strip()

    if not content:
        return jsonify({
            "valid": False,
            "errors": ["Please paste resume content"],
            "warnings": []
        })

    errors, warnings = validate_updated_content(content)

    return jsonify({
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    })


@app.route("/api/preview", methods=["POST"])
def preview():
    """Parse resume content and return preview data."""
    try:
        data = request.get_json() or {}
        content = str(data.get("content", "")).strip()
        identity = identity_profile_by_id(data.get("identity", "")).get("id", "outlook")
        enabled_experience_keys = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))

        if not content:
            return jsonify({
                "success": False,
                "error": "Content is required",
            }), 400

        base_resume = load_base_resume()
        merged_resume = parse_updated_content_to_resume(content, base_resume)
        merged_resume = apply_profile_overrides(merged_resume)
        merged_resume = apply_experience_history_override(merged_resume, data.get("experience_history_override"))
        merged_resume = apply_enabled_experience_filter(merged_resume, enabled_experience_keys)
        merged_resume["_enabled_experience_keys"] = enabled_experience_keys

        contact_override = data.get("contact_override") or {}
        if isinstance(contact_override, dict):
            merged_resume["contact"] = {
                **merged_resume.get("contact", {}),
                **{
                    key: str(contact_override.get(key, "")).strip()
                    for key in ("location", "phone", "email")
                    if str(contact_override.get(key, "")).strip()
                },
            }

        errors, warnings = validate_updated_content(content)

        return jsonify({
            "success": True,
            "preview": merged_resume,
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        })
    except AIStageError as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "stage": e.stage,
            "analysis": e.analysis,
            "timing": e.timing,
        }), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Get current settings."""
    ok, msg = get_pdf_conversion_status()
    ai_ok, ai_msg = is_ai_generation_ready()
    return jsonify({
        **settings,
        "identities": current_identity_profiles(),
        "settings_file": str(SETTINGS_FILE),
        "pdf_conversion_ready": ok,
        "pdf_conversion_status": msg,
        "ai_generation_ready": ai_ok,
        "ai_generation_status": ai_msg,
        "ai_model": RESUME_MODEL,
        "ai_analysis_model": ANALYSIS_MODEL,
        "ai_resume_model": RESUME_MODEL,
        "ai_synthesis_model": SYNTHESIS_MODEL,
        "ai_audit_model": AUDIT_MODEL,
        "ai_synthesis_reasoning_effort": SYNTHESIS_REASONING_EFFORT,
        "ai_audit_reasoning_effort": AUDIT_REASONING_EFFORT,
        "ai_memory_limit": AI_MEMORY_LIMIT,
    })


@app.route("/api/settings", methods=["POST"])
def update_settings():
    """Update settings."""
    try:
        data = request.get_json()
        output_directory = data.get("output_directory", "").strip()
        identities = normalize_identity_profiles(data.get("identities"))

        if not output_directory:
            return jsonify({
                "success": False,
                "error": "Output directory cannot be empty"
            }), 400

        if not Path(output_directory).is_absolute():
            return jsonify({
                "success": False,
                "error": "Path must be absolute.\nExample:\n/Users/yourname/Documents/resumes"
            }), 400

        # Try to create the directory if it doesn't exist
        try:
            Path(output_directory).mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return jsonify({
                "success": False,
                "error": f"Permission denied: Cannot write to {output_directory}"
            }), 403
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Cannot create directory: {str(e)}"
            }), 400

        # Update in-memory settings and save to file
        settings["output_directory"] = output_directory
        settings["keep_docx"] = bool(data.get("keep_docx", settings.get("keep_docx", True)))
        settings["identities"] = identities
        save_settings(settings)

        return jsonify({
            "success": True,
            "message": "Settings saved successfully",
            "output_directory": output_directory,
            "identities": identities,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/profile", methods=["GET"])
def get_profile():
    """Get the effective profile plus onboarding/session metadata."""
    return jsonify(profile_response_payload())


@app.route("/api/profile", methods=["POST"])
def update_profile():
    """Save profile data to the permanent or session profile document."""
    try:
        data = request.get_json() or {}
        save_target = str(data.get("save_target", "session")).strip().lower()
        if save_target not in {"session", "permanent"}:
            return jsonify({"success": False, "error": "Invalid save target."}), 400

        if not isinstance(data.get("application"), dict):
            data["application"] = current_profile().get("application", {})
        profile = normalize_profile(data)
        issues = validate_profile_payload(profile)
        if issues:
            return jsonify({"success": False, "error": issues[0], "issues": issues}), 400

        if save_target == "permanent":
            save_permanent_profile_doc(profile)
            clear_session_profile_doc()
        else:
            save_session_profile_doc(profile)

        return jsonify({"success": True, **profile_response_payload()})
    except AIStageError as e:
        response = {
            "success": False,
            "error": str(e),
            "stage": e.stage,
            "analysis": e.analysis,
            "timing": e.timing,
            "session_id": session_id if 'session_id' in locals() else None,
            "memory_count": len(session.get("turns", [])) if 'session' in locals() else 0,
            "memory_limit": AI_MEMORY_LIMIT,
        }
        if e.analysis and 'session' in locals():
            session["analysis"] = e.analysis
        return jsonify(response), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def parse_extension_skills_text(value: str) -> list[dict]:
    skills: list[dict] = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        category, raw_items = line.split(":", 1)
        items = [item.strip().rstrip(".") for item in raw_items.split(",") if item.strip().rstrip(".")]
        if category.strip() and items:
            skills.append({"category": category.strip(), "items": items})
    return normalize_updated_skills(skills)


def validate_extension_manual_core(title_summary: dict, skills_payload: dict) -> list[str]:
    """Validate editable resume structure without reapplying AI generation policy."""
    issues: list[str] = []
    if not str(title_summary.get("updated_title", "")).strip():
        issues.append("Resume title is required.")
    if not str(title_summary.get("updated_summary", "")).strip():
        issues.append("Summary is required.")

    skills = normalize_updated_skills(skills_payload.get("updated_skills") or [])
    if not skills:
        issues.append("Add at least one technical skills category.")
        return issues
    seen_categories: set[str] = set()
    for entry in skills:
        category = str(entry.get("category", "")).strip()
        items = expand_skill_items(entry.get("items", []))
        normalized_category = category.casefold()
        if not category:
            issues.append("A technical skills category is empty.")
        elif normalized_category in seen_categories:
            issues.append(f"Duplicate skills category: {category}.")
        else:
            seen_categories.add(normalized_category)
        if not items:
            issues.append(f"Skills category '{category or 'Untitled'}' needs at least one skill.")
    return issues


def parse_extension_bullets(value) -> list[str]:
    raw_items = value if isinstance(value, list) else str(value or "").splitlines()
    return [
        re.sub(r"^[\s\u2022\-*]+", "", str(item)).strip()
        for item in raw_items
        if re.sub(r"^[\s\u2022\-*]+", "", str(item)).strip()
    ]


def apply_extension_experience_edits(draft: dict, edits: list, enabled_keys: list[str]) -> dict:
    if not isinstance(edits, list):
        raise ValueError("Work experience edits must be a list.")
    enabled_set = set(enabled_keys)
    recent = {
        **(draft.get("experience_recent") or {}),
        "experience": {
            key: dict(value) for key, value in ((draft.get("experience_recent") or {}).get("experience") or {}).items()
        },
    }
    older = {
        **(draft.get("experience_older") or {}),
        "experience": {
            key: dict(value) for key, value in ((draft.get("experience_older") or {}).get("experience") or {}).items()
        },
    }
    history = [dict(item) for item in (draft.get("experience_history_snapshot") or []) if isinstance(item, dict)]
    history_by_key = {str(item.get("key", "")).strip(): item for item in history}
    seen: set[str] = set()

    for raw_entry in edits:
        if not isinstance(raw_entry, dict):
            raise ValueError("Each work experience edit must be an object.")
        key = str(raw_entry.get("key", "")).strip()
        if not key or key not in enabled_set:
            raise ValueError("Work experience edits must reference an enabled role.")
        if key in seen:
            raise ValueError(f"Work experience role '{key}' was submitted more than once.")
        seen.add(key)
        target = recent["experience"].get(key) or older["experience"].get(key)
        if target is None:
            raise ValueError(f"Regenerate the resume before editing role '{key}'.")

        title = str(raw_entry.get("title", target.get("title", ""))).strip()
        bullets = parse_extension_bullets(raw_entry.get("bullets_text", raw_entry.get("bullets", target.get("bullets", []))))
        if not title:
            raise ValueError("Every enabled work experience requires a role title.")
        if not bullets:
            raise ValueError("Every enabled work experience requires at least one bullet.")
        target.update({"title": title, "bullets": bullets})

        history_entry = history_by_key.get(key)
        if history_entry is None:
            raise ValueError(f"Profile history is missing work experience role '{key}'.")
        for field in ("company", "location", "dates"):
            value = str(raw_entry.get(field, history_entry.get(field, ""))).strip()
            if not value:
                raise ValueError(f"Every enabled work experience requires {field}.")
            history_entry[field] = value

    return {
        "experience_recent": recent,
        "experience_older": older,
        "experience_history_snapshot": history,
    }


def rebuild_extension_draft_content(draft: dict, title_summary: dict, skills_payload: dict, enabled_keys: list[str]) -> str:
    core = merge_core_sections(title_summary, skills_payload)
    core["_analysis"] = draft.get("analysis") or {}
    core["_enabled_experience_keys"] = enabled_keys
    experience = {"experience": {}}
    experience["experience"].update((draft.get("experience_recent") or {}).get("experience", {}))
    experience["experience"].update((draft.get("experience_older") or {}).get("experience", {}))
    experience["_enabled_experience_keys"] = enabled_keys
    missing = [key for key in enabled_keys if key not in experience["experience"]]
    if missing:
        raise ValueError("Regenerate the resume to add experience roles that were not generated in this draft.")
    return format_generated_resume_text(merge_resume_payloads(core, experience), experience_blueprints_from_snapshot(draft))


def extension_payloads_from_content(content: str, draft: dict, enabled_keys: list[str]) -> dict:
    parsed = parse_updated_content_to_resume(content, load_base_resume())
    parsed_skills = []
    for item in parsed.get("technical_skills", []):
        if not isinstance(item, dict):
            continue
        raw_items = item.get("items", "")
        items = raw_items if isinstance(raw_items, list) else [part.strip() for part in str(raw_items).split(",") if part.strip()]
        parsed_skills.append({"category": str(item.get("category", "")).strip(), "items": items})
    skills_payload = {"updated_skills": normalize_updated_skills(parsed_skills)}
    title_summary = {
        "updated_title": str(parsed.get("title", "")).strip(),
        "updated_summary": str(parsed.get("summary", "")).strip(),
    }
    experience_by_key: dict[str, dict] = {}
    parsed_experience = parsed.get("experience") if isinstance(parsed.get("experience"), list) else []
    for index, key in enumerate(enabled_keys):
        entry = parsed_experience[index] if index < len(parsed_experience) and isinstance(parsed_experience[index], dict) else {}
        experience_by_key[key] = {
            "title": str(entry.get("title", "")).strip(),
            "bullets": [str(item).strip() for item in entry.get("bullets", []) if str(item).strip()],
        }
    recent_keys = set(EXPERIENCE_BLUEPRINT_KEYS[:2])
    return {
        "title_summary": title_summary,
        "skills": skills_payload,
        "experience_recent": {"experience": {key: value for key, value in experience_by_key.items() if key in recent_keys}},
        "experience_older": {"experience": {key: value for key, value in experience_by_key.items() if key not in recent_keys}},
    }


def run_extension_draft_audit(draft_id: str) -> dict:
    draft = extension_drafts.get(draft_id)
    if not draft:
        raise KeyError("Resume draft not found.")
    draft = extension_drafts.start_audit(draft_id)
    run_token = str((draft.get("audit_result") or {}).get("run_token", "")).strip()
    if not run_token:
        raise RuntimeError("Quality review run token was not created.")
    enabled_keys = normalize_enabled_experience_keys(draft.get("enabled_experience_keys"))
    blueprints = filter_blueprints_by_enabled_keys(experience_blueprints_from_snapshot(draft), enabled_keys)
    current_resume = extension_canonical_resume(draft, blueprints)
    base_revision = int(draft.get("resume_revision") or 1)
    try:
        result = run_extension_ai_stage(
            lambda: generate_resume_quality_audit(
                api_key=os.getenv("OPENAI_API_KEY", "").strip(),
                job_description=draft["job_description"],
                analysis_payload=draft.get("analysis") or {},
                current_resume=current_resume,
                active_blueprints=blueprints,
                candidate_profile=draft.get("profile_snapshot") or {},
                advertised_job_title=draft.get("role_title", ""),
                user_edit_context={
                    "has_manual_edits": int(draft.get("resume_revision") or 1) > 1,
                    "edited_paths": [],
                },
            )
        )
        saved = extension_drafts.save_audit_result(
            draft_id,
            result,
            result["base_hash"],
            base_revision,
            run_token,
        )
        if result.get("decision") == "changes_suggested":
            return apply_extension_draft_audit(draft_id)
        return saved
    except (ResumeQualityAuditStaleConflictError, AuditStaleError):
        raise
    except ResumeQualityAuditValidationError as exc:
        extension_drafts.mark_audit_failure(
            draft_id,
            str(exc),
            run_token,
            metadata=_quality_audit_failure_metadata(exc),
        )
        raise
    except Exception as exc:
        extension_drafts.mark_audit_failure(
            draft_id,
            str(exc),
            run_token,
            metadata=_quality_audit_failure_metadata(exc),
        )
        raise


def apply_extension_draft_audit(draft_id: str) -> dict:
    draft = extension_drafts.get(draft_id)
    if not draft:
        raise KeyError("Resume draft not found.")
    enabled_keys = normalize_enabled_experience_keys(draft.get("enabled_experience_keys"))
    blueprints = filter_blueprints_by_enabled_keys(experience_blueprints_from_snapshot(draft), enabled_keys)
    current_resume = extension_canonical_resume(draft, blueprints)
    applied = apply_resume_quality_audit_proposal(
        expected_base_hash=str(draft.get("audit_base_hash", "")),
        current_resume=current_resume,
        audit_result=draft.get("audit_result") or {},
        analysis_payload=draft.get("analysis") or {},
        active_blueprints=blueprints,
        candidate_profile=draft.get("profile_snapshot") or {},
    )
    values = extension_audit_values_from_resume(draft, applied, enabled_keys)
    change_ids = [
        record["change_id"]
        for record in _quality_audit_change_records(
            (draft.get("audit_result") or {}).get("changes") or {}
        )
    ]
    return extension_drafts.resolve_audit_decisions(
        draft_id,
        expected_revision=int(draft.get("audit_base_revision") or 0),
        expected_hash=str(draft.get("audit_base_hash", "")),
        current_hash=canonical_json_hash(current_resume),
        values=values,
        decisions={change_id: "accept" for change_id in change_ids},
    )


def extension_audit_values_from_resume(
    draft: dict,
    resolved_resume: dict,
    enabled_keys: list[str],
) -> dict:
    recent_keys = set(EXPERIENCE_BLUEPRINT_KEYS[:2])
    recent = {
        "experience": {
            key: value
            for key, value in resolved_resume["experience"].items()
            if key in recent_keys
        }
    }
    older = {
        "experience": {
            key: value
            for key, value in resolved_resume["experience"].items()
            if key not in recent_keys
        }
    }
    title_summary = {
        "updated_title": resolved_resume["updated_title"],
        "updated_summary": resolved_resume["updated_summary"],
    }
    skills = {"updated_skills": resolved_resume["updated_skills"]}
    candidate = {
        **draft,
        "title_summary": title_summary,
        "skills": skills,
        "experience_recent": recent,
        "experience_older": older,
    }
    content = rebuild_extension_draft_content(candidate, title_summary, skills, enabled_keys)
    candidate["resume_content"] = content
    values = {
        "title_summary": title_summary,
        "skills": skills,
        "experience_recent": recent,
        "experience_older": older,
        "resume_content": content,
        "resume_snapshot": draft_resume_snapshot(candidate),
    }
    return values


def resolve_extension_draft_audit(draft_id: str, decisions) -> dict:
    draft = extension_drafts.get(draft_id)
    if not draft:
        raise KeyError("Resume draft not found.")
    enabled_keys = normalize_enabled_experience_keys(draft.get("enabled_experience_keys"))
    blueprints = filter_blueprints_by_enabled_keys(
        experience_blueprints_from_snapshot(draft),
        enabled_keys,
    )
    current_resume = extension_canonical_resume(draft, blueprints)
    resolved, _review_groups, all_rejected = resolve_resume_quality_audit_decisions(
        expected_base_hash=str(draft.get("audit_base_hash", "")),
        current_resume=current_resume,
        audit_result=draft.get("audit_result") or {},
        decisions=decisions,
        analysis_payload=draft.get("analysis") or {},
        active_blueprints=blueprints,
        candidate_profile=draft.get("profile_snapshot") or {},
    )
    values = None if all_rejected else extension_audit_values_from_resume(
        draft,
        resolved,
        enabled_keys,
    )
    return extension_drafts.resolve_audit_decisions(
        draft_id,
        expected_revision=int(draft.get("audit_base_revision") or 0),
        expected_hash=str(draft.get("audit_base_hash", "")),
        current_hash=canonical_json_hash(current_resume),
        values=values,
        decisions=decisions,
    )


@app.route("/api/extension/status", methods=["GET"])
def extension_status():
    pdf_ok, pdf_message = get_pdf_conversion_status()
    ai_ok, ai_message = is_ai_generation_ready()
    profile = current_profile()
    return jsonify({
        "success": True,
        "server_ready": True,
        "ai_ready": ai_ok,
        "ai_message": ai_message,
        "model": RESUME_MODEL,
        "analysis_model": ANALYSIS_MODEL,
        "resume_model": RESUME_MODEL,
        "synthesis_model": SYNTHESIS_MODEL,
        "audit_model": AUDIT_MODEL,
        "synthesis_reasoning_effort": SYNTHESIS_REASONING_EFFORT,
        "audit_reasoning_effort": AUDIT_REASONING_EFFORT,
        "pdf_ready": pdf_ok,
        "pdf_message": pdf_message,
        "onboarding_required": not has_permanent_profile_doc(),
        "queue_paused": extension_drafts.has_duplicate_review(),
        "identities": current_identity_profiles(),
        "experience_history": profile.get("experience_history", []),
        "autofill_ready": bool(profile.get("name")) and bool(current_identity_profiles()),
    })


@app.route("/api/extension/autofill-profile", methods=["GET", "POST"])
def extension_autofill_profile():
    """Return or update the application profile used by ATS content scripts."""
    if request.method == "GET":
        identity_id = str(request.args.get("identity_id", "")).strip()
        return jsonify({
            "success": True,
            "profile": autofill_profile_data(identity_id),
            "application": current_profile().get("application", {}),
        })

    try:
        data = request.get_json() or {}
        save_target = str(data.get("save_target", "permanent")).strip().lower()
        if save_target not in {"session", "permanent"}:
            return jsonify({"success": False, "error": "Invalid save target."}), 400

        effective = current_profile()
        application_payload = data.get("application") if isinstance(data.get("application"), dict) else data
        effective["application"] = normalize_application_profile(application_payload)
        if "fullName" in data or "name" in data:
            effective["name"] = str(data.get("fullName", data.get("name", ""))).strip()
        normalized = normalize_profile(effective)

        if save_target == "permanent":
            save_permanent_profile_doc(normalized)
            clear_session_profile_doc()
        else:
            save_session_profile_doc(normalized)

        identity_id = str(data.get("identity_id", "")).strip()
        return jsonify({
            "success": True,
            "profile": autofill_profile_data(identity_id),
            "application": current_profile().get("application", {}),
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/extension/contexts/resolve", methods=["POST"])
def resolve_extension_context():
    try:
        context, draft = extension_drafts.resolve(request.get_json() or {})
        issues = validate_context(context)
        history = tracker_company_history(context.get("company_name", "")) if context.get("company_name") else {"count": 0, "applications": []}
        return jsonify({
            "success": True,
            "context": context,
            "complete": not issues,
            "issues": issues,
            "history": history,
            "draft": extension_draft_payload(draft),
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/extension/drafts", methods=["POST"])
def create_extension_draft():
    try:
        if not has_permanent_profile_doc():
            return jsonify({"success": False, "error": "Complete Profile setup before generating a resume.", "onboarding_required": True}), 409
        data = request.get_json() or {}
        context = normalize_context(data.get("context") or data)
        issues = validate_context(context)
        if issues:
            return jsonify({"success": False, "error": " ".join(issues), "issues": issues}), 400
        history = tracker_company_history(context["company_name"])
        snapshot = extension_profile_snapshot(str(data.get("identity_id", "")), data.get("enabled_experience_keys"))
        draft = create_extension_draft_with_gate(
            context,
            snapshot,
            int(history.get("count", 0)),
        )
        extension_worker_event.set()
        return jsonify({
            "success": True,
            "draft": extension_draft_payload(draft),
            "history": history,
            "queue_paused": extension_drafts.has_duplicate_review(),
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/extension/drafts", methods=["GET"])
def list_extension_drafts():
    try:
        limit = int(request.args.get("limit", "12"))
        drafts = [extension_draft_payload(draft) for draft in extension_drafts.list(limit)]
        return jsonify({
            "success": True,
            "drafts": drafts,
            "queue_paused": extension_drafts.has_duplicate_review(),
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/extension/drafts/<draft_id>", methods=["GET"])
def get_extension_draft(draft_id: str):
    draft = extension_drafts.get(draft_id)
    if not draft:
        return jsonify({"success": False, "error": "Resume draft not found."}), 404
    return jsonify({"success": True, "draft": extension_draft_payload(draft)})


def update_extension_draft_service(
    draft_id: str,
    data: dict,
    *,
    expected_revision: int | None = None,
) -> dict:
    """Apply one canonical draft update for the app, extension, or MCP adapter."""
    draft = extension_drafts.get(draft_id)
    if not draft:
        raise KeyError("Resume draft not found.")
    if draft.get("locked"):
        raise ValueError("Applied resume drafts are locked.")
    current_revision = int(draft.get("resume_revision") or 1)
    if expected_revision is not None and int(expected_revision) != current_revision:
        raise AuditStaleError(
            f"The resume changed. Expected revision {expected_revision}, current revision is {current_revision}."
        )

    values: dict = {}
    invalidate_pdf = False
    if "company_name" in data:
        values["company_name"] = str(data.get("company_name", "")).strip()
        invalidate_pdf = True
    if "role_title" in data:
        values["role_title"] = str(data.get("role_title", "")).strip()
        invalidate_pdf = True
    if "identity_id" in data:
        identity = identity_profile_by_id(str(data.get("identity_id", "")))
        values.update({"identity_id": identity.get("id", ""), "contact_snapshot": identity})
        invalidate_pdf = True
    if "experience_history" in data and isinstance(data.get("experience_history"), list):
        history = merge_experience_history_lists([], data.get("experience_history"))
        values["experience_history_snapshot"] = history
        invalidate_pdf = True

    enabled_keys = draft.get("enabled_experience_keys") or []
    if "enabled_experience_keys" in data:
        requested = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))
        complete = {
            str(item.get("key", "")).strip()
            for item in draft.get("experience_history_snapshot", [])
            if isinstance(item, dict) and is_experience_history_entry_enabled(item)
        }
        enabled_keys = [key for key in requested if key in complete]
        if not enabled_keys:
            raise ValueError("Keep at least one complete experience role enabled.")
        values["enabled_experience_keys"] = enabled_keys
        invalidate_pdf = True

    title_summary = dict(draft.get("title_summary") or {})
    skills_payload = dict(draft.get("skills") or {})
    quick_edits = data.get("quick_edits") if isinstance(data.get("quick_edits"), dict) else None
    if quick_edits is not None:
        if "title" in quick_edits:
            title_summary["updated_title"] = str(quick_edits.get("title", "")).strip()
        if "summary" in quick_edits:
            title_summary["updated_summary"] = str(quick_edits.get("summary", "")).strip()
        if "skills_text" in quick_edits:
            skills_text_value = str(quick_edits.get("skills_text", ""))
            malformed_lines = [
                line.strip()
                for line in skills_text_value.splitlines()
                if line.strip() and (
                    ":" not in line
                    or not line.split(":", 1)[0].strip()
                    or not line.split(":", 1)[1].strip()
                )
            ]
            if malformed_lines:
                raise ValueError("Use one skills category per line in 'Category: item, item' format.")
            parsed_skills = parse_extension_skills_text(skills_text_value)
            if not parsed_skills:
                raise ValueError("Use one skills category per line in 'Category: item, item' format.")
            skills_payload["updated_skills"] = parsed_skills
        if "experience" in quick_edits:
            values.update(apply_extension_experience_edits(draft, quick_edits.get("experience"), enabled_keys))
        issues = validate_extension_manual_core(title_summary, skills_payload)
        if issues:
            raise ValueError(" | ".join(issues[:3]))
        values.update({"title_summary": title_summary, "skills": skills_payload})
        invalidate_pdf = True

    if quick_edits is not None or "enabled_experience_keys" in data:
        values["resume_content"] = rebuild_extension_draft_content({**draft, **values}, title_summary, skills_payload, enabled_keys)
    if "resume_content" in data:
        content = str(data.get("resume_content", "")).strip()
        errors, _warnings = validate_updated_content(content)
        if errors:
            raise ValueError(errors[0])
        values["resume_content"] = content
        values.update(extension_payloads_from_content(content, {**draft, **values}, enabled_keys))
        invalidate_pdf = True

    next_draft = {**draft, **values}
    if values.get("resume_content"):
        values["resume_snapshot"] = draft_resume_snapshot(next_draft)
    updated = extension_drafts.update(draft_id, values, invalidate_pdf=invalidate_pdf)
    return extension_draft_payload(updated)


@app.route("/api/extension/drafts/<draft_id>", methods=["PATCH"])
def update_extension_draft(draft_id: str):
    try:
        updated = update_extension_draft_service(draft_id, request.get_json() or {})
        return jsonify({"success": True, "draft": updated})
    except KeyError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except AuditStaleError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/extension/drafts/<draft_id>", methods=["DELETE"])
def delete_extension_draft(draft_id: str):
    try:
        extension_drafts.delete(draft_id)
        return jsonify({"success": True})
    except KeyError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409


@app.route("/api/extension/drafts/<draft_id>/generate", methods=["POST"])
def queue_extension_draft(draft_id: str):
    try:
        draft = extension_drafts.queue(draft_id)
        extension_worker_event.set()
        return jsonify({"success": True, "draft": extension_draft_payload(draft)})
    except (KeyError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route("/api/extension/drafts/<draft_id>/duplicate-decision", methods=["POST"])
def decide_extension_duplicate(draft_id: str):
    try:
        draft = extension_drafts.decide_duplicate(draft_id, str((request.get_json() or {}).get("decision", "")))
        extension_worker_event.set()
        return jsonify({"success": True, "draft": extension_draft_payload(draft), "queue_paused": extension_drafts.has_duplicate_review()})
    except (KeyError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route("/api/extension/drafts/<draft_id>/retry", methods=["POST"])
def retry_extension_draft(draft_id: str):
    try:
        draft = extension_drafts.retry(draft_id)
        extension_worker_event.set()
        return jsonify({"success": True, "draft": extension_draft_payload(draft)})
    except (KeyError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route("/api/extension/drafts/<draft_id>/regenerate", methods=["POST"])
def regenerate_extension_draft(draft_id: str):
    try:
        data = request.get_json() or {}
        current = extension_drafts.get(draft_id)
        if current and current.get("locked"):
            context = data.get("context") or {
                "source": current.get("source"),
                "external_job_id": current.get("external_job_id"),
                "url": current.get("canonical_url"),
                "company_name": current.get("company_name"),
                "role_title": current.get("role_title"),
                "location": current.get("location"),
                "job_description": data.get("job_description") or current.get("job_description"),
            }
            snapshot = extension_profile_snapshot(current.get("identity_id", ""), current.get("enabled_experience_keys"))
            draft = extension_drafts.create(context, snapshot, 0)
        else:
            draft = extension_drafts.regenerate(draft_id, data.get("context"))
        extension_worker_event.set()
        return jsonify({"success": True, "draft": extension_draft_payload(draft)})
    except ActiveDraftTaskError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except (KeyError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route("/api/extension/drafts/<draft_id>/audit", methods=["POST"])
def audit_extension_draft(draft_id: str):
    try:
        return jsonify({"success": True, "draft": extension_draft_payload(run_extension_draft_audit(draft_id))})
    except KeyError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except (AuditStaleError, ResumeQualityAuditStaleConflictError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except (ValueError, ResumeQualityAuditValidationError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/extension/drafts/<draft_id>/audit/apply", methods=["POST"])
def apply_extension_audit(draft_id: str):
    try:
        return jsonify({"success": True, "draft": extension_draft_payload(apply_extension_draft_audit(draft_id))})
    except KeyError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except (AuditStaleError, ResumeQualityAuditStaleConflictError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except (ValueError, ResumeQualityAuditValidationError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/extension/drafts/<draft_id>/audit/keep-current", methods=["POST"])
def keep_current_extension_audit(draft_id: str):
    try:
        draft = extension_drafts.keep_current_audit(draft_id)
        return jsonify({"success": True, "draft": extension_draft_payload(draft)})
    except KeyError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except AuditStaleError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route("/api/extension/drafts/<draft_id>/audit/resolve", methods=["POST"])
def resolve_extension_audit(draft_id: str):
    try:
        data = request.get_json(silent=True) or {}
        draft = resolve_extension_draft_audit(draft_id, data.get("decisions"))
        return jsonify({"success": True, "draft": extension_draft_payload(draft)})
    except KeyError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except (AuditStaleError, ResumeQualityAuditStaleConflictError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except (ValueError, ResumeQualityAuditValidationError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/extension/drafts/<draft_id>/pdf", methods=["POST"])
def create_extension_pdf(draft_id: str):
    try:
        draft = extension_drafts.get(draft_id)
        if not draft:
            return jsonify({"success": False, "error": "Resume draft not found."}), 404
        return jsonify({"success": True, "draft": extension_draft_payload(generate_extension_pdf(draft))})
    except ExtensionPdfAuditConflict as exc:
        return jsonify({"success": False, "error": str(exc), "audit_status": exc.audit_status}), 409
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/extension/drafts/<draft_id>/mark-applied", methods=["POST"])
def mark_extension_draft_applied(draft_id: str):
    try:
        draft = extension_draft_payload(extension_drafts.get(draft_id))
        if not draft:
            return jsonify({"success": False, "error": "Resume draft not found."}), 404
        if draft.get("status") != "pdf_ready" or draft.get("pdf_stale") or not Path(draft.get("pdf_path", "")).exists():
            raise ValueError("Generate the latest PDF before marking this application as applied.")
        data = request.get_json() or {}
        application = build_tracker_application_record(
            company_name=draft.get("company_name", ""),
            job_description=draft.get("job_description", ""),
            resume_content=draft.get("resume_content", ""),
            analysis_payload=draft.get("analysis") or {},
            applied_date=str(data.get("applied_date", "")).strip() or today_iso_date(),
            status=str(data.get("status", "Applied")),
            source=str(data.get("source", "LinkedIn")),
            job_url=draft.get("canonical_url", ""),
            notes=str(data.get("notes", "")),
            pdf_path=draft.get("pdf_path", ""),
            output_dir=draft.get("output_dir", ""),
            contact_override=draft.get("contact_snapshot") or {},
            identity=draft.get("identity_id", ""),
            experience_history_override=draft.get("experience_history_snapshot") or [],
            enabled_experience_keys=draft.get("enabled_experience_keys") or [],
            parsed_resume_override=draft.get("preview") or draft.get("resume_snapshot") or {},
        )
        saved_application = upsert_tracker_application(application)
        updated = extension_drafts.update(draft_id, {"application_id": saved_application.get("id", ""), "status": "applied", "stage": "complete"})
        applications = list_tracker_applications()
        return jsonify({
            "success": True,
            "draft": extension_draft_payload(updated),
            "application": saved_application,
            "summary": summarize_tracker({"applications": applications}),
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/extension/drafts/<draft_id>/editor-session", methods=["POST"])
def create_extension_editor_session(draft_id: str):
    draft = extension_draft_payload(extension_drafts.get(draft_id))
    if not draft:
        return jsonify({"success": False, "error": "Resume draft not found."}), 404
    session_id = uuid.uuid4().hex
    ai_sessions[session_id] = {
        "job_description": draft.get("job_description", ""),
        "advertised_job_title": draft.get("role_title", ""),
        "turns": ([{"revision_request": "", "analysis": draft.get("analysis") or {}, "resume_text": draft.get("resume_content", ""), "created_at": datetime.now(timezone.utc).isoformat()}] if draft.get("resume_content") else []),
        "analysis": draft.get("analysis") or None,
        "title_summary": draft.get("title_summary") or None,
        "skills": draft.get("skills") or None,
        "core_resume": (merge_core_sections(draft.get("title_summary") or {}, draft.get("skills") or {}) if draft.get("title_summary") and draft.get("skills") else None),
        "experience_recent": draft.get("experience_recent") or None,
        "experience_older": draft.get("experience_older") or None,
        "enabled_experience_keys": draft.get("enabled_experience_keys") or [],
        "resume_content": draft.get("resume_content") or "",
        "resume_revision": int(draft.get("resume_revision") or 1),
        "profile_snapshot": draft.get("profile_snapshot") or {},
        "resume_versions": copy.deepcopy(draft.get("resume_versions") or {}),
        "active_resume_version": draft.get("active_resume_version") or "",
        "audit_status": draft.get("audit_status") or "not_started",
        "audit_result": draft.get("audit_result"),
        "audit_proposal": draft.get("audit_proposal"),
        "audit_base_revision": draft.get("audit_base_revision"),
        "audit_base_hash": draft.get("audit_base_hash") or None,
        "audit_created_at": draft.get("audit_created_at"),
        "audit_applied_at": draft.get("audit_applied_at"),
        "extension_draft_id": draft_id,
        "has_manual_resume_edits": int(draft.get("resume_revision") or 1) > 1,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    ensure_ai_session_state(ai_sessions[session_id])
    return jsonify({"success": True, "session_id": session_id, "draft": draft})


@app.route("/api/extension/drafts/<draft_id>/reachout", methods=["POST"])
def generate_extension_reachout(draft_id: str):
    try:
        draft = extension_draft_payload(extension_drafts.get(draft_id))
        if not draft:
            return jsonify({"success": False, "error": "Resume draft not found."}), 404
        if not str(draft.get("resume_content", "")).strip() or not draft.get("analysis"):
            raise ValueError("Generate the resume before creating a reachout message.")

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY is not configured"}), 500

        data = request.get_json() or {}
        started = time.perf_counter()
        reachout_payload = generate_reachout_message(
            api_key=api_key,
            job_description=draft.get("job_description", ""),
            analysis_payload=draft.get("analysis") or {},
            current_resume_content=draft.get("resume_content", ""),
            recipient_name=str(data.get("recipient_name", "")),
            target_company=draft.get("company_name", ""),
            target_role=draft.get("role_title", ""),
        )
        issues = validate_reachout_payload(reachout_payload)
        if issues:
            raise ValueError("Reachout generation failed validation: " + " | ".join(issues[:3]))
        return jsonify({
            "success": True,
            "reachout": reachout_payload,
            "timing": {"reachout_ms": int((time.perf_counter() - started) * 1000)},
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Reachout generation failed: {exc}"}), 500


def answer_pdf_path(
    draft: dict,
    *,
    max_age_hours: int | None = None,
    now: datetime | None = None,
) -> Path:
    """Return the current draft PDF or raise a user-facing eligibility error."""
    pdf_path = str(draft.get("pdf_path", "")).strip()
    if (
        draft.get("pdf_stale")
        or int(draft.get("pdf_revision") or 0) != int(draft.get("resume_revision") or 1)
        or not pdf_path
        or not Path(pdf_path).exists()
    ):
        raise ValueError("Generate the latest PDF before generating answers.")

    if max_age_hours is not None:
        generated_at_text = str(draft.get("pdf_generated_at", "")).strip()
        if not generated_at_text:
            raise ValueError("The selected PDF does not have a generation timestamp. Generate it again.")
        try:
            generated_at = datetime.fromisoformat(generated_at_text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("The selected PDF has an invalid generation timestamp. Generate it again.") from exc
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        if (current_time - generated_at.astimezone(timezone.utc)).total_seconds() > max_age_hours * 60 * 60:
            raise ValueError(f"The selected PDF is older than {max_age_hours} hours. Generate a new PDF to answer this application.")

    return Path(pdf_path)


@app.route("/api/extension/drafts/<draft_id>/followup", methods=["POST"])
def generate_extension_followup(draft_id: str):
    try:
        draft = extension_draft_payload(extension_drafts.get(draft_id))
        if not draft:
            return jsonify({"success": False, "error": "Resume draft not found."}), 404
        data = request.get_json() or {}
        question = str(data.get("question", "")).strip()
        if not question:
            raise ValueError("Enter a follow-up question.")
        pdf_path = answer_pdf_path(draft)
        if not draft.get("analysis"):
            raise ValueError("Generate the resume before answering follow-up questions.")

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY is not configured"}), 500

        started = time.perf_counter()
        followup_payload = generate_followup_answer(
            api_key=api_key,
            job_description=draft.get("job_description", ""),
            analysis_payload=draft.get("analysis") or {},
            question=question,
            resume_pdf_text=extract_text_from_pdf(str(pdf_path)),
        )
        return jsonify({
            "success": True,
            "followup": followup_payload,
            "timing": {"followup_ms": int((time.perf_counter() - started) * 1000)},
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Follow-up generation failed: {exc}"}), 500


SENSITIVE_APPLICATION_QUESTION_RE = re.compile(
    r"\b(work authorization|authorized to work|sponsor|sponsorship|visa|salary|compensation|pay range|"
    r"desired pay|start date|available to start|availability|security clearance|criminal|felony|conviction|"
    r"disability|veteran|race|ethnicity|gender|sexual orientation|demographic|eeo|equal employment)\b",
    re.IGNORECASE,
)


@app.route("/api/extension/drafts/<draft_id>/application-answer", methods=["POST"])
def generate_extension_application_answer(draft_id: str):
    try:
        draft = extension_draft_payload(extension_drafts.get(draft_id))
        if not draft:
            return jsonify({"success": False, "error": "Resume draft not found."}), 404
        data = request.get_json() or {}
        question = str(data.get("question", "")).strip()
        if not question:
            raise ValueError("Select an application question first.")
        if SENSITIVE_APPLICATION_QUESTION_RE.search(question):
            raise ValueError("Answer this question manually because it requires personal or legal confirmation.")
        pdf_path = answer_pdf_path(draft, max_age_hours=24)
        if not draft.get("analysis"):
            raise ValueError("The selected resume does not have its job analysis.")
        max_characters = max(0, min(int(data.get("max_characters") or 0), 5000))
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY is not configured"}), 500

        started = time.perf_counter()
        answer = generate_followup_answer(
            api_key=api_key,
            job_description=draft.get("job_description", ""),
            analysis_payload=draft.get("analysis") or {},
            question=question,
            resume_pdf_text=extract_text_from_pdf(str(pdf_path)),
            max_characters=max_characters,
        )
        return jsonify({
            "success": True,
            "answer": answer,
            "timing": {"application_answer_ms": int((time.perf_counter() - started) * 1000)},
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Application answer generation failed: {exc}"}), 500


@app.route("/api/tracker", methods=["GET"])
def get_tracker():
    try:
        sort_key = str(request.args.get("sort", "applied_date")).strip()
        applications = sorted_tracker_applications(list_tracker_applications(), sort_key=sort_key)
        return jsonify({
            "success": True,
            "applications": applications,
            "summary": summarize_tracker({"applications": applications}),
            "statuses": TRACKER_STATUSES,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tracker/company-history", methods=["GET"])
def get_tracker_company_history():
    try:
        company_name = str(request.args.get("company", "")).strip()
        history = tracker_company_history(company_name)
        return jsonify({"success": True, **history})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tracker/applications", methods=["POST"])
def create_tracker_application():
    try:
        data = request.get_json() or {}
        company_name = str(data.get("company_name", "")).strip()
        resume_content = str(data.get("resume_content", "")).strip()
        job_description = str(data.get("job_description", "")).strip()
        applied_date = str(data.get("applied_date", "")).strip() or today_iso_date()
        if not resume_content:
            return jsonify({"success": False, "error": "Resume content is required"}), 400
        if not company_name and not str((data.get("analysis") or {}).get("company_name", "")).strip():
            return jsonify({"success": False, "error": "Company name is required"}), 400

        target_output_dir = str(data.get("output_dir", "")).strip()
        application = build_tracker_application_record(
            company_name=company_name,
            job_description=job_description,
            resume_content=resume_content,
            analysis_payload=data.get("analysis") or {},
            applied_date=applied_date,
            status=str(data.get("status", "Applied")),
            source=str(data.get("source", "")),
            job_url=str(data.get("job_url", "")),
            notes=str(data.get("notes", "")),
            pdf_path=str(data.get("pdf_path", "")),
            output_dir=target_output_dir,
            contact_override=data.get("contact_override") or {},
            identity=str(data.get("identity", "outlook")),
            experience_history_override=data.get("experience_history_override"),
            enabled_experience_keys=data.get("enabled_experience_keys"),
            parsed_resume_override=data.get("resume_snapshot_override"),
        )
        if data.get("job_id"):
            application["job_id"] = str(data.get("job_id", "")).strip()
        response_application = upsert_tracker_application(application)
        merged_applications = list_tracker_applications()
        return jsonify({
            "success": True,
            "application": response_application,
            "summary": summarize_tracker({"applications": merged_applications}),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tracker/applications/<application_id>/status", methods=["POST"])
def update_tracker_application_status(application_id: str):
    try:
        data = request.get_json() or {}
        new_status = normalize_tracker_status(data.get("status", ""))
        note = str(data.get("note", "")).strip()
        effective_date = str(data.get("effective_date", "")).strip() or today_iso_date()
        updated_record = update_tracker_status_record(application_id, new_status, note, effective_date)
        merged_applications = list_tracker_applications()
        return jsonify({
            "success": True,
            "application": updated_record,
            "summary": summarize_tracker({"applications": merged_applications}),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tracker/applications/<application_id>/open-file", methods=["POST"])
def open_tracker_application_file(application_id: str):
    try:
        record = tracker_application_by_id(application_id)
        if not record:
            return jsonify({"success": False, "error": "Application not found."}), 404

        output_dir = str(record.get("output_dir", "")).strip()
        pdf_path = str(record.get("pdf_path", "")).strip()
        target_path = None
        if output_dir:
            target_path = Path(output_dir).expanduser()
        elif pdf_path:
            target_path = Path(pdf_path).expanduser()

        if target_path is None or not target_path.exists():
            return jsonify({"success": False, "error": "Saved resume path is not available."}), 404

        open_path(target_path)
        return jsonify({"success": True, "opened_path": str(target_path)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/status", methods=["GET"])
def ai_status():
    ready, message = is_ai_generation_ready()
    return jsonify({
        "ready": ready,
        "message": message,
        "model": RESUME_MODEL,
        "analysis_model": ANALYSIS_MODEL,
        "resume_model": RESUME_MODEL,
        "synthesis_model": SYNTHESIS_MODEL,
        "audit_model": AUDIT_MODEL,
        "synthesis_reasoning_effort": SYNTHESIS_REASONING_EFFORT,
        "audit_reasoning_effort": AUDIT_REASONING_EFFORT,
        "memory_limit": AI_MEMORY_LIMIT,
    })


@app.route("/api/ai/reset", methods=["POST"])
def reset_ai_memory():
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id", "")).strip()
    if session_id:
        ai_sessions.pop(session_id, None)
    return jsonify({"success": True, "session_id": None, "memory_count": 0})


@app.route("/api/ai/analyze", methods=["POST"])
def analyze_ai_content():
    try:
        data = request.get_json() or {}
        job_description = str(data.get("job_description", "")).strip()
        revision_request = str(data.get("revision_request", "")).strip()
        current_resume_content = str(data.get("current_resume_content", "")).strip()
        session_id = str(data.get("session_id", "")).strip() or None
        reset_memory = bool(data.get("reset_memory", False))
        enabled_experience_keys = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))

        if not job_description:
            return jsonify({"success": False, "error": "Job description is required"}), 400

        if len(job_description) > 20000:
            return jsonify({"success": False, "error": "Job description is too long"}), 400

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY is not configured"}), 500

        session_id, session = get_ai_session(session_id, job_description, reset_memory)
        session["enabled_experience_keys"] = enabled_experience_keys
        incoming_revision_context = normalize_revision_context(revision_request, current_resume_content)
        if incoming_revision_context is not None:
            session["revision_context"] = incoming_revision_context
        cached_analysis = session.get("analysis")
        timing = {"analysis_ms": 0, "total_ms": 0}
        if cached_analysis:
            analysis_payload = cached_analysis
        else:
            started = time.perf_counter()
            analysis_payload = analyze_job_description(
                api_key=api_key,
                job_description=job_description,
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            timing = {"analysis_ms": elapsed, "total_ms": elapsed}
            session["analysis"] = analysis_payload

        session["updated_at"] = time.time()

        return jsonify({
            "success": True,
            "session_id": session_id,
            "memory_count": len(session.get("turns", [])),
            "memory_limit": AI_MEMORY_LIMIT,
            "analysis": analysis_payload,
            "model": ANALYSIS_MODEL,
            "timing": timing,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/transcribe", methods=["POST"])
def transcribe_audio():
    try:
        audio_file = request.files.get("audio")
        target = str(request.form.get("target", "jd")).strip()
        if target not in {"jd", "refinement"}:
            target = "jd"

        if audio_file is None or not audio_file.filename:
            return jsonify({"success": False, "error": "Audio file is required"}), 400

        suffix = Path(audio_file.filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
            audio_file.save(temp_audio)
            temp_path = Path(temp_audio.name)

        try:
            model = get_whisper_model()
            segments, _info = model.transcribe(str(temp_path), vad_filter=True, beam_size=1)
            transcript = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        finally:
            temp_path.unlink(missing_ok=True)

        if not transcript:
            return jsonify({"success": False, "error": "No speech detected"}), 400

        return jsonify({"success": True, "text": transcript, "target": target})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/generate", methods=["POST"])
def generate_ai_content():
    try:
        data = request.get_json() or {}
        job_description = str(data.get("job_description", "")).strip()
        revision_request = str(data.get("revision_request", "")).strip()
        current_resume_content = str(data.get("current_resume_content", "")).strip()
        session_id = str(data.get("session_id", "")).strip() or None
        reset_memory = bool(data.get("reset_memory", False))
        enabled_experience_keys = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))

        if not job_description:
            return jsonify({"success": False, "error": "Job description is required"}), 400

        if len(job_description) > 20000:
            return jsonify({"success": False, "error": "Job description is too long"}), 400

        session_id, session = get_ai_session(session_id, job_description, reset_memory)
        session["enabled_experience_keys"] = enabled_experience_keys
        memory_turns = session.get("turns", [])[-AI_MEMORY_LIMIT:]
        cached_analysis = session.get("analysis")

        model_payload = call_openai_resume_engine(
            job_description,
            revision_request,
            memory_turns,
            current_resume_content,
            cached_analysis=cached_analysis,
            enabled_experience_keys=enabled_experience_keys,
        )
        resume_payload = model_payload["resume"]
        analysis_payload = model_payload["analysis"]
        resume_payload["_enabled_experience_keys"] = enabled_experience_keys
        resume_text = format_generated_resume_text(resume_payload)
        timing = model_payload.get("timing", {})

        turn = {
            "revision_request": revision_request,
            "analysis": analysis_payload,
            "resume_text": resume_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        session["turns"] = (session.get("turns", []) + [turn])[-AI_MEMORY_LIMIT:]
        session["analysis"] = analysis_payload
        session["updated_at"] = time.time()

        return jsonify({
            "success": True,
            "session_id": session_id,
            "memory_count": len(session["turns"]),
            "memory_limit": AI_MEMORY_LIMIT,
            "analysis": analysis_payload,
            "content": resume_text,
            "model": RESUME_MODEL,
            "analysis_model": ANALYSIS_MODEL,
            "resume_model": RESUME_MODEL,
            "timing": timing,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/generate-core", methods=["POST"])
def generate_ai_core():
    try:
        data = request.get_json() or {}
        job_description = str(data.get("job_description", "")).strip()
        revision_request = str(data.get("revision_request", "")).strip()
        current_resume_content = str(data.get("current_resume_content", "")).strip()
        session_id = str(data.get("session_id", "")).strip() or None
        reset_memory = bool(data.get("reset_memory", False))
        enabled_experience_keys = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))

        if not job_description:
            return jsonify({"success": False, "error": "Job description is required"}), 400

        session_id, session = get_ai_session(session_id, job_description, reset_memory)
        session["enabled_experience_keys"] = enabled_experience_keys
        analysis_payload = session.get("analysis")
        if not analysis_payload:
            raise AIStageError("analysis", "JD analysis is required before core generation.")

        memory_turns = session.get("turns", [])[-AI_MEMORY_LIMIT:]
        memory_block = "\n\n".join(compact_turn_for_prompt(turn) for turn in memory_turns if turn)

        started = time.perf_counter()
        try:
            core_payload = generate_resume_core_from_analysis(
                api_key=os.getenv("OPENAI_API_KEY", "").strip(),
                job_description=job_description,
                analysis_payload=analysis_payload,
                revision_request=revision_request,
                current_resume_content=current_resume_content,
                memory_block=memory_block,
            )
        except Exception as exc:
            raise AIStageError("core_generation", f"Core resume generation failed: {exc}", analysis=analysis_payload) from exc
        timing = {"core_ms": int((time.perf_counter() - started) * 1000)}
        timing["total_ms"] = timing["core_ms"]

        issues = validate_core_payload(core_payload, analysis_payload)
        if issues:
            raise AIStageError(
                "core_generation",
                "Core resume generation failed validation: " + " | ".join(issues[:3]),
                analysis=analysis_payload,
                timing=timing,
            )

        core_content = format_core_resume_text(core_payload)
        core_payload["_enabled_experience_keys"] = enabled_experience_keys
        session["core_resume"] = core_payload
        session["updated_at"] = time.time()

        return jsonify({
            "success": True,
            "session_id": session_id,
            "memory_count": len(session.get("turns", [])),
            "memory_limit": AI_MEMORY_LIMIT,
            "analysis": analysis_payload,
            "core": core_payload,
            "content": core_content,
            "model": RESUME_MODEL,
            "timing": timing,
        })
    except AIStageError as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "stage": e.stage,
            "analysis": e.analysis,
            "timing": e.timing,
            "session_id": session_id if 'session_id' in locals() else None,
            "memory_count": len(session.get("turns", [])) if 'session' in locals() else 0,
            "memory_limit": AI_MEMORY_LIMIT,
        }), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/generate-title-summary", methods=["POST"])
def generate_ai_title_summary():
    try:
        data = request.get_json() or {}
        session_id = str(data.get("session_id", "")).strip() or None
        enabled_experience_keys = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))
        if not session_id:
            return jsonify({"success": False, "error": "An active JD session is required."}), 400
        if session_id not in ai_sessions:
            return jsonify({"success": False, "error": "AI session not found."}), 404

        session = ensure_ai_session_state(ai_sessions[session_id])
        supplied_advertised_title = str(
            data.get("advertised_job_title", "")
        ).strip()
        if supplied_advertised_title:
            session["advertised_job_title"] = supplied_advertised_title
        session["enabled_experience_keys"] = enabled_experience_keys
        analysis_payload = session.get("analysis")
        if not analysis_payload:
            raise AIStageError("analysis", "JD analysis is required before title and summary generation.")

        started = time.perf_counter()
        title_summary = generate_title_summary_from_analysis(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            analysis_payload=analysis_payload,
        )
        timing = {"title_summary_ms": int((time.perf_counter() - started) * 1000)}
        timing["total_ms"] = timing["title_summary_ms"]

        issues = validate_title_summary_payload(title_summary, analysis_payload)
        if issues:
            raise AIStageError("title_summary_generation", "Title and summary generation failed validation: " + " | ".join(issues[:3]), analysis=analysis_payload, timing=timing)

        session["title_summary"] = title_summary
        session["experience_recent"] = None
        session["experience_older"] = None
        if session.get("skills"):
            session["core_resume"] = merge_core_sections(title_summary, session["skills"])
            session["core_resume"]["_analysis"] = analysis_payload
        session["updated_at"] = time.time()
        return jsonify({
            "success": True,
            "session_id": session_id,
            "title_summary": title_summary,
            "content": format_title_summary_text(title_summary),
            "timing": timing,
        })
    except AIStageError as e:
        return jsonify({"success": False, "error": str(e), "stage": e.stage, "analysis": e.analysis, "timing": e.timing}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/generate-skills", methods=["POST"])
def generate_ai_skills():
    try:
        data = request.get_json() or {}
        session_id = str(data.get("session_id", "")).strip() or None
        enabled_experience_keys = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))
        if not session_id:
            return jsonify({"success": False, "error": "An active JD session is required."}), 400
        if session_id not in ai_sessions:
            return jsonify({"success": False, "error": "AI session not found."}), 404

        session = ensure_ai_session_state(ai_sessions[session_id])
        session["enabled_experience_keys"] = enabled_experience_keys
        analysis_payload = session.get("analysis")
        if not analysis_payload:
            raise AIStageError("analysis", "JD analysis is required before skills generation.")

        started = time.perf_counter()
        skills_payload = generate_skills_from_analysis(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            analysis_payload=analysis_payload,
            revision_context=session.get("revision_context"),
        )
        timing = {"skills_ms": int((time.perf_counter() - started) * 1000)}
        timing["total_ms"] = timing["skills_ms"]

        skills_payload["updated_skills"] = normalize_updated_skills(skills_payload.get("updated_skills", []))
        issues = validate_skills_only_payload(skills_payload, analysis_payload)
        if issues:
            raise AIStageError("skills_generation", "Skills generation failed validation: " + " | ".join(issues[:3]), analysis=analysis_payload, timing=timing)

        session["skills"] = skills_payload
        session["experience_recent"] = None
        session["experience_older"] = None
        if session.get("title_summary"):
            session["core_resume"] = merge_core_sections(session["title_summary"], skills_payload)
            session["core_resume"]["_analysis"] = analysis_payload
        session["updated_at"] = time.time()
        return jsonify({
            "success": True,
            "session_id": session_id,
            "skills": skills_payload,
            "content": format_skills_text(skills_payload),
            "timing": timing,
        })
    except AIStageError as e:
        return jsonify({"success": False, "error": str(e), "stage": e.stage, "analysis": e.analysis, "timing": e.timing}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/review-core", methods=["POST"])
def review_ai_core():
    try:
        data = request.get_json() or {}
        session_id = str(data.get("session_id", "")).strip() or None
        enabled_experience_keys = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))
        if not session_id:
            return jsonify({"success": False, "error": "An active JD session is required."}), 400
        if session_id not in ai_sessions:
            return jsonify({"success": False, "error": "AI session not found."}), 404

        session = ensure_ai_session_state(ai_sessions[session_id])
        session["enabled_experience_keys"] = enabled_experience_keys
        analysis_payload = session.get("analysis")
        title_summary = session.get("title_summary")
        skills_payload = session.get("skills")
        if not analysis_payload:
            raise AIStageError("analysis", "JD analysis is required before core review.")
        if not title_summary or not skills_payload:
            raise AIStageError("core_generation", "Title, summary, and skills are required before core review.", analysis=analysis_payload)

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        order_key = skill_category_order_key_for_analysis(analysis_payload)
        ordered_categories = skill_category_order_for_key(order_key)
        experience_payload = None
        if session.get("experience_recent") and session.get("experience_older"):
            experience_payload = {"experience": {}}
            experience_payload["experience"].update(session["experience_recent"].get("experience", {}))
            experience_payload["experience"].update(session["experience_older"].get("experience", {}))
            experience_payload["_enabled_experience_keys"] = enabled_experience_keys
        started = time.perf_counter()
        corrected_payload = refine_core_sections(
            api_key=api_key,
            analysis_payload=analysis_payload,
            title_summary_payload=title_summary,
            skills_payload=skills_payload,
            experience_payload=experience_payload,
        )
        timing = {"core_refinement_ms": int((time.perf_counter() - started) * 1000)}

        corrected_title_summary = {
            "updated_title": str(corrected_payload.get("updated_title", "")).strip() or str(title_summary.get("updated_title", "")).strip(),
            "updated_summary": str(corrected_payload.get("updated_summary", "")).strip(),
        }
        corrected_skills = normalize_skills_for_order(
            {"updated_skills": corrected_payload.get("updated_skills", [])},
            ordered_categories,
        )

        summary_issues = validate_title_summary_payload(corrected_title_summary, analysis_payload, summary_max_buffer=10)
        skills_issues = validate_skills_only_payload(corrected_skills, analysis_payload)
        title_review_issues = []
        if experience_payload:
            blueprints = filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_experience_keys)
            title_review_issues = validate_experience_title_review_payload(corrected_payload, blueprints, analysis_payload)
        issues = summary_issues + skills_issues + title_review_issues
        if issues:
            corrected_title_summary = title_summary
            corrected_skills = skills_payload
            revised = False
        else:
            revised = (
                corrected_title_summary.get("updated_title", "").strip() != str(title_summary.get("updated_title", "")).strip()
                or
                corrected_title_summary.get("updated_summary", "").strip() != str(title_summary.get("updated_summary", "")).strip()
                or normalize_updated_skills(corrected_skills.get("updated_skills", []))
                != normalize_updated_skills(skills_payload.get("updated_skills", []))
                or (
                    experience_payload is not None
                    and any(
                        str(((corrected_payload.get("experience_titles") or {}).get(key, "")).strip())
                        != str((((experience_payload.get("experience") or {}).get(key) or {}).get("title", "")).strip())
                        for key in (corrected_payload.get("experience_titles") or {}).keys()
                    )
                )
            )

        session["title_summary"] = corrected_title_summary
        session["skills"] = corrected_skills
        session["core_resume"] = merge_core_sections(session["title_summary"], session["skills"])
        session["core_resume"]["_analysis"] = analysis_payload
        session["core_resume"]["_enabled_experience_keys"] = enabled_experience_keys
        if experience_payload:
            reviewed_recent = apply_reviewed_titles_to_experience_payload(session["experience_recent"], corrected_payload)
            reviewed_older = apply_reviewed_titles_to_experience_payload(session["experience_older"], corrected_payload)
            session["experience_recent"] = reviewed_recent
            session["experience_older"] = reviewed_older
        session["updated_at"] = time.time()
        timing["total_ms"] = timing["core_refinement_ms"]

        response_content = format_core_resume_text(session["core_resume"])
        title_warnings: list[str] = []
        if experience_payload:
            experience_payload = {"experience": {}}
            experience_payload["experience"].update(session["experience_recent"].get("experience", {}))
            experience_payload["experience"].update(session["experience_older"].get("experience", {}))
            experience_payload["_enabled_experience_keys"] = enabled_experience_keys
            response_content = format_generated_resume_text(merge_resume_payloads(session["core_resume"], experience_payload))
            title_warnings = collect_experience_title_warnings(experience_payload, analysis_payload)

        return jsonify({
            "success": True,
            "session_id": session_id,
            "revised": revised,
            "core": session["core_resume"],
            "experience": experience_payload,
            "title_warnings": title_warnings,
            "content": response_content,
            "timing": timing,
        })
    except AIStageError as e:
        return jsonify({"success": False, "error": str(e), "stage": e.stage, "analysis": e.analysis, "timing": e.timing}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/generate-experience", methods=["POST"])
def generate_ai_experience():
    try:
        data = request.get_json() or {}
        job_description = str(data.get("job_description", "")).strip()
        revision_request = str(data.get("revision_request", "")).strip()
        current_resume_content = str(data.get("current_resume_content", "")).strip()
        session_id = str(data.get("session_id", "")).strip() or None
        reset_memory = bool(data.get("reset_memory", False))
        enabled_experience_keys = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))

        if not job_description:
            return jsonify({"success": False, "error": "Job description is required"}), 400

        session_id, session = get_ai_session(session_id, job_description, reset_memory)
        session["enabled_experience_keys"] = enabled_experience_keys
        analysis_payload = session.get("analysis")
        core_payload = session.get("core_resume")
        if not analysis_payload:
            raise AIStageError("analysis", "JD analysis is required before experience generation.")
        if not core_payload:
            raise AIStageError("core_generation", "Core resume sections are required before experience generation.", analysis=analysis_payload)

        memory_turns = session.get("turns", [])[-AI_MEMORY_LIMIT:]
        memory_block = "\n\n".join(compact_turn_for_prompt(turn) for turn in memory_turns if turn)

        started = time.perf_counter()
        try:
            experience_payload = generate_resume_experience_from_analysis(
                api_key=os.getenv("OPENAI_API_KEY", "").strip(),
                job_description=job_description,
                analysis_payload=analysis_payload,
                core_payload=core_payload,
                revision_request=revision_request,
                current_resume_content=current_resume_content,
                memory_block=memory_block,
                enabled_experience_keys=enabled_experience_keys,
            )
        except Exception as exc:
            raise AIStageError("experience_generation", f"Experience generation failed: {exc}", analysis=analysis_payload) from exc
        timing = {"experience_ms": int((time.perf_counter() - started) * 1000)}
        timing["total_ms"] = timing["experience_ms"]

        merged_payload = merge_resume_payloads(core_payload, experience_payload)
        resume_text = format_generated_resume_text(merged_payload)
        title_warnings = collect_experience_title_warnings(experience_payload, analysis_payload)

        turn = {
            "revision_request": revision_request,
            "analysis": analysis_payload,
            "resume_text": resume_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        session["turns"] = (session.get("turns", []) + [turn])[-AI_MEMORY_LIMIT:]
        session["updated_at"] = time.time()

        return jsonify({
            "success": True,
            "session_id": session_id,
            "memory_count": len(session["turns"]),
            "memory_limit": AI_MEMORY_LIMIT,
            "analysis": analysis_payload,
            "experience": experience_payload,
            "title_warnings": title_warnings,
            "content": resume_text,
            "model": RESUME_MODEL,
            "timing": timing,
        })
    except AIStageError as e:
        response = {
            "success": False,
            "error": str(e),
            "stage": e.stage,
            "analysis": e.analysis,
            "timing": e.timing,
            "session_id": session_id if 'session_id' in locals() else None,
            "memory_count": len(session.get("turns", [])) if 'session' in locals() else 0,
            "memory_limit": AI_MEMORY_LIMIT,
        }
        if 'session' in locals() and session.get("core_resume"):
            response["content"] = format_core_resume_text(session["core_resume"])
        return jsonify(response), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/generate-experience-recent", methods=["POST"])
def generate_ai_experience_recent():
    return _generate_ai_experience_subset(recent=True)


@app.route("/api/ai/generate-experience-older", methods=["POST"])
def generate_ai_experience_older():
    return _generate_ai_experience_subset(recent=False)


def _generate_ai_experience_subset(*, recent: bool):
    try:
        data = request.get_json() or {}
        session_id = str(data.get("session_id", "")).strip() or None
        enabled_experience_keys = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))
        if not session_id:
            return jsonify({"success": False, "error": "An active JD session is required."}), 400
        if session_id not in ai_sessions:
            return jsonify({"success": False, "error": "AI session not found."}), 404

        session = ensure_ai_session_state(ai_sessions[session_id])
        session["enabled_experience_keys"] = enabled_experience_keys
        analysis_payload = session.get("analysis")
        skills_payload = session.get("skills")
        if not analysis_payload:
            raise AIStageError("analysis", "JD analysis is required before experience generation.")
        if not skills_payload:
            raise AIStageError("skills_generation", "Preliminary skills are required before experience generation.", analysis=analysis_payload)

        all_blueprints = filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_experience_keys)
        recent_keys = set(EXPERIENCE_BLUEPRINT_KEYS[:2])
        blueprints = [blueprint for blueprint in all_blueprints if (blueprint["key"] in recent_keys) == recent]
        model = RESUME_MODEL
        timeout_seconds = OPENAI_RESUME_TIMEOUT_SECONDS

        started = time.perf_counter()
        subset_payload = generate_experience_subset_from_analysis(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            analysis_payload=analysis_payload,
            preliminary_skills_payload=skills_payload,
            blueprints=blueprints,
            model=model,
            timeout_seconds=timeout_seconds,
            revision_context=session.get("revision_context"),
        )
        timing_key = "recent_experience_ms" if recent else "older_experience_ms"
        timing = {timing_key: int((time.perf_counter() - started) * 1000)}
        timing["total_ms"] = timing[timing_key]

        issues = validate_experience_subset_payload_with_analysis(subset_payload, blueprints, analysis_payload)
        if issues:
            raise AIStageError(
                "experience_generation",
                "Experience generation failed validation: " + " | ".join(issues[:3]),
                analysis=analysis_payload,
                timing=timing,
            )

        subset_key = "experience_recent" if recent else "experience_older"
        session[subset_key] = subset_payload
        if session.get("experience_recent") and session.get("experience_older"):
            merged_experience = ai_session_combined_experience(session)
            title_warnings = collect_experience_title_warnings(merged_experience, analysis_payload)
            session["updated_at"] = time.time()
            response = {
                "success": True,
                "session_id": session_id,
                "experience": merged_experience,
                "title_warnings": title_warnings,
                "timing": timing,
                "complete": True,
            }
            if session.get("title_summary"):
                session["core_resume"] = merge_core_sections(session["title_summary"], skills_payload)
                session["core_resume"]["_analysis"] = analysis_payload
                session["core_resume"]["_enabled_experience_keys"] = enabled_experience_keys
                response["content"] = format_ai_session_resume(session, all_blueprints)
            return jsonify(response)

        session["updated_at"] = time.time()
        return jsonify({
            "success": True,
            "session_id": session_id,
            "experience": subset_payload,
            "timing": timing,
            "complete": False,
        })
    except AIStageError as e:
        response = {"success": False, "error": str(e), "stage": e.stage, "analysis": e.analysis, "timing": e.timing}
        return jsonify(response), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/final-synthesis", methods=["POST"])
def final_synthesize_ai_resume():
    try:
        data = request.get_json(silent=True) or {}
        session_id = str(data.get("session_id", "")).strip()
        if not session_id:
            return jsonify({"success": False, "error": "session_id is required."}), 400
        if session_id not in ai_sessions:
            return jsonify({"success": False, "error": "AI session not found."}), 404

        session = ensure_ai_session_state(ai_sessions[session_id])
        had_finalized_resume = bool(
            str(session.get("resume_content", "")).strip()
            and session.get("title_summary")
            and session.get("skills")
        )
        previous_resume_hash = None
        if had_finalized_resume:
            previous_blueprints = ai_session_active_blueprints(session)
            previous_resume_hash = canonical_json_hash(
                ai_session_canonical_resume(session, previous_blueprints)
            )
        if "enabled_experience_keys" in data:
            session["enabled_experience_keys"] = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))
        enabled_keys = normalize_enabled_experience_keys(session.get("enabled_experience_keys"))
        active_blueprints = filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_keys)
        if not active_blueprints:
            raise ValueError("Keep at least one experience role enabled.")

        analysis_payload = session.get("analysis")
        preliminary_skills = session.get("skills")
        if not analysis_payload:
            raise AIStageError("analysis", "JD analysis is required before final synthesis.")
        if not preliminary_skills:
            raise AIStageError("skills_generation", "Preliminary skills are required before final synthesis.", analysis=analysis_payload)
        if session.get("experience_recent") is None or session.get("experience_older") is None:
            raise AIStageError(
                "experience_generation",
                "Recent and older experience generation must finish before final synthesis.",
                analysis=analysis_payload,
            )

        combined_experience = ai_session_combined_experience(session)
        missing_keys = [
            blueprint["key"]
            for blueprint in active_blueprints
            if blueprint["key"] not in combined_experience["experience"]
        ]
        if missing_keys:
            raise AIStageError(
                "experience_generation",
                "Experience generation is incomplete for: " + ", ".join(missing_keys) + ".",
                analysis=analysis_payload,
            )

        started = time.perf_counter()
        synthesized = generate_final_synthesis_from_analysis(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            job_description=str(session.get("job_description", "")),
            analysis_payload=analysis_payload,
            preliminary_skills_payload=preliminary_skills,
            combined_experience_payload=combined_experience,
            active_blueprints=active_blueprints,
            revision_context=session.get("revision_context"),
        )
        timing = {"final_synthesis_ms": int((time.perf_counter() - started) * 1000)}
        timing["total_ms"] = timing["final_synthesis_ms"]

        issues = validate_final_synthesis_payload(synthesized, active_blueprints, analysis_payload)
        if issues:
            raise AIStageError(
                "final_synthesis",
                "Final synthesis failed validation: " + " | ".join(issues[:3]),
                analysis=analysis_payload,
                timing=timing,
            )

        session["title_summary"] = {
            "updated_title": str(synthesized.get("updated_title", "")).strip(),
            "updated_summary": str(synthesized.get("updated_summary", "")).strip(),
        }
        session["skills"] = {
            "updated_skills": copy.deepcopy(synthesized.get("updated_skills") or [])
        }
        session["experience_recent"] = apply_reviewed_titles_to_experience_payload(
            session["experience_recent"],
            synthesized,
        )
        session["experience_older"] = apply_reviewed_titles_to_experience_payload(
            session["experience_older"],
            synthesized,
        )
        session["core_resume"] = merge_core_sections(session["title_summary"], session["skills"])
        session["core_resume"]["_analysis"] = analysis_payload
        session["core_resume"]["_enabled_experience_keys"] = enabled_keys
        session["resume_content"] = format_ai_session_resume(session, active_blueprints)
        session["has_manual_resume_edits"] = False
        synthesized_resume_hash = canonical_json_hash(
            ai_session_canonical_resume(session, active_blueprints)
        )
        if had_finalized_resume and synthesized_resume_hash != previous_resume_hash:
            session["resume_revision"] = int(session.get("resume_revision") or 1) + 1
        clear_ai_session_audit(session)
        session["resume_versions"] = {}
        capture_ai_session_resume_version(
            session,
            "original",
            active_blueprints,
        )
        session["updated_at"] = time.time()

        turn = {
            "revision_request": "",
            "analysis": analysis_payload,
            "resume_text": session["resume_content"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        session["turns"] = (session.get("turns", []) + [turn])[-AI_MEMORY_LIMIT:]
        experience = ai_session_combined_experience(session)
        return jsonify({
            "success": True,
            "session_id": session_id,
            "content": session["resume_content"],
            "resume": ai_session_canonical_resume(session, active_blueprints),
            "title_summary": session["title_summary"],
            "skills": session["skills"],
            "core": session["core_resume"],
            "experience": experience,
            "resume_revision": session["resume_revision"],
            "audit_status": session["audit_status"],
            "resume_versions": copy.deepcopy(session["resume_versions"]),
            "active_resume_version": session["active_resume_version"],
            "title_warnings": collect_experience_title_warnings(experience, analysis_payload),
            "timing": timing,
        })
    except AIStageError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
            "stage": exc.stage,
            "analysis": exc.analysis,
            "timing": exc.timing,
        }), 400
    except (ValueError, ResumeQualityAuditValidationError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/ai/quality-audit", methods=["POST"])
def audit_ai_resume_quality():
    try:
        data = request.get_json(silent=True) or {}
        session_id = str(data.get("session_id", "")).strip()
        if not session_id:
            return jsonify({"success": False, "error": "session_id is required."}), 400
        if session_id not in ai_sessions:
            return jsonify({"success": False, "error": "AI session not found."}), 404

        session = ensure_ai_session_state(ai_sessions[session_id])
        supplied_advertised_title = str(
            data.get("advertised_job_title", "")
        ).strip()
        if supplied_advertised_title:
            session["advertised_job_title"] = supplied_advertised_title
        if "enabled_experience_keys" in data:
            session["enabled_experience_keys"] = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))
        active_blueprints = ai_session_active_blueprints(session)
        if not active_blueprints:
            raise ValueError("Keep at least one experience role enabled.")
        if not session.get("analysis") or not session.get("title_summary") or not session.get("skills"):
            raise ValueError("Complete final synthesis before running the quality audit.")

        supplied_content = str(data.get("current_resume_content", "")).strip()
        if supplied_content:
            accept_ai_session_resume_content(session, supplied_content, active_blueprints)

        current_resume = ai_session_canonical_resume(session, active_blueprints)
        missing_keys = [
            blueprint["key"]
            for blueprint in active_blueprints
            if not str(
                ((current_resume.get("experience") or {}).get(blueprint["key"]) or {}).get("title", "")
            ).strip()
            or not (
                ((current_resume.get("experience") or {}).get(blueprint["key"]) or {}).get("bullets")
            )
        ]
        if missing_keys:
            raise ValueError("Complete final synthesis before running the quality audit.")

        base_revision = int(session.get("resume_revision") or 1)
        base_hash = canonical_json_hash(current_resume)
        created_at = datetime.now(timezone.utc).isoformat()
        session["audit_status"] = "running"
        session["audit_result"] = None
        session["audit_proposal"] = None
        session["audit_base_revision"] = base_revision
        session["audit_base_hash"] = base_hash
        session["audit_created_at"] = created_at
        session["audit_applied_at"] = None
        session["updated_at"] = time.time()

        try:
            result = generate_resume_quality_audit(
                api_key=os.getenv("OPENAI_API_KEY", "").strip(),
                job_description=str(session.get("job_description", "")),
                analysis_payload=session.get("analysis") or {},
                current_resume=current_resume,
                active_blueprints=active_blueprints,
                candidate_profile=session.get("profile_snapshot") or {},
                advertised_job_title=str(
                    session.get("advertised_job_title", "")
                ),
                user_edit_context={
                    "has_manual_edits": bool(
                        session.get("has_manual_resume_edits")
                    ),
                    "edited_paths": [],
                },
            )
        except Exception as exc:
            session["audit_status"] = "technical_failed"
            session["audit_result"] = _quality_audit_failure_metadata(exc)
            session["audit_proposal"] = None
            session["audit_base_revision"] = base_revision
            session["audit_base_hash"] = base_hash
            session["audit_created_at"] = created_at
            session["audit_applied_at"] = None
            session["updated_at"] = time.time()
            raise

        if (
            int(session.get("resume_revision") or 1) != base_revision
            or canonical_json_hash(ai_session_canonical_resume(session, active_blueprints)) != base_hash
        ):
            session["audit_status"] = "stale"
            session["audit_proposal"] = None
            raise ResumeQualityAuditStaleConflictError(
                base_hash,
                canonical_json_hash(ai_session_canonical_resume(session, active_blueprints)),
            )

        decision = str(result.get("decision", "")).strip()
        if decision not in {"approved", "changes_suggested", "manual_attention"}:
            error = ResumeQualityAuditValidationError(["Invalid audit decision."])
            session["audit_status"] = "technical_failed"
            session["audit_result"] = _quality_audit_failure_metadata(error)
            session["audit_proposal"] = None
            session["updated_at"] = time.time()
            raise error
        result = copy.deepcopy(result)
        result["base_hash"] = base_hash
        if "original" not in (session.get("resume_versions") or {}):
            capture_ai_session_resume_version(
                session,
                "original",
                active_blueprints,
            )
        applied_at = None
        if decision == "changes_suggested":
            reviewed_resume = apply_resume_quality_audit_proposal(
                expected_base_hash=base_hash,
                current_resume=current_resume,
                audit_result=result,
                analysis_payload=session.get("analysis") or {},
                active_blueprints=active_blueprints,
                candidate_profile=session.get("profile_snapshot") or {},
            )
            update_ai_session_structured_resume(
                session,
                reviewed_resume,
                active_blueprints,
            )
            session["resume_revision"] = int(session.get("resume_revision") or 1) + 1
            accepted_change_ids = [
                record["change_id"]
                for record in _quality_audit_change_records(
                    result.get("changes") or {}
                )
            ]
            result["accepted_change_ids"] = accepted_change_ids
            result["rejected_change_ids"] = []
            result["auto_applied"] = True
            decision = "applied"
            applied_at = datetime.now(timezone.utc).isoformat()
            capture_ai_session_resume_version(
                session,
                "luna_reviewed",
                active_blueprints,
            )
        elif decision == "approved":
            capture_ai_session_resume_version(
                session,
                "luna_reviewed",
                active_blueprints,
            )
        session["audit_status"] = decision
        session["audit_result"] = result
        session["audit_proposal"] = None
        session["audit_base_revision"] = base_revision
        session["audit_base_hash"] = base_hash
        session["audit_created_at"] = created_at
        session["audit_applied_at"] = applied_at
        session["updated_at"] = time.time()
        active_resume = ai_session_canonical_resume(
            session,
            active_blueprints,
        )
        return jsonify({
            "success": True,
            "session_id": session_id,
            "audit": result,
            "audit_status": decision,
            "audit_result": result,
            "audit_proposal": session["audit_proposal"],
            "audit_base_revision": base_revision,
            "audit_base_hash": base_hash,
            "audit_created_at": created_at,
            "audit_applied_at": applied_at,
            "resume_revision": session["resume_revision"],
            "content": session.get("resume_content", ""),
            "resume": active_resume,
            "title_summary": session.get("title_summary") or {},
            "skills": session.get("skills") or {},
            "experience": ai_session_combined_experience(session),
            "resume_versions": copy.deepcopy(session.get("resume_versions") or {}),
            "active_resume_version": session.get("active_resume_version") or "",
        })
    except ResumeQualityAuditStaleConflictError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except ResumeQualityAuditValidationError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/ai/quality-audit/apply", methods=["POST"])
def apply_ai_resume_quality_audit():
    try:
        data = request.get_json(silent=True) or {}
        session_id = str(data.get("session_id", "")).strip()
        if not session_id:
            return jsonify({"success": False, "error": "session_id is required."}), 400
        if session_id not in ai_sessions:
            return jsonify({"success": False, "error": "AI session not found."}), 404

        expected_base_hash = str(
            data.get("expected_base_hash", data.get("audit_base_hash", ""))
        ).strip()
        if not expected_base_hash:
            raise ValueError("expected_base_hash is required.")

        session = ensure_ai_session_state(ai_sessions[session_id])
        active_blueprints = ai_session_active_blueprints(session)
        supplied_content = str(data.get("current_resume_content", "")).strip()
        if supplied_content:
            accept_ai_session_resume_content(session, supplied_content, active_blueprints)

        current_resume = ai_session_canonical_resume(session, active_blueprints)
        current_hash = canonical_json_hash(current_resume)
        if (
            session.get("audit_status") != "changes_suggested"
            or str(session.get("audit_base_hash") or "") != expected_base_hash
            or int(session.get("audit_base_revision") or 0) != int(session.get("resume_revision") or 1)
            or current_hash != expected_base_hash
        ):
            session["audit_status"] = "stale"
            session["audit_proposal"] = None
            session["updated_at"] = time.time()
            raise ResumeQualityAuditStaleConflictError(expected_base_hash, current_hash)

        applied = apply_resume_quality_audit_proposal(
            expected_base_hash=expected_base_hash,
            current_resume=current_resume,
            audit_result=session.get("audit_result") or {},
            analysis_payload=session.get("analysis") or {},
            active_blueprints=active_blueprints,
            candidate_profile=session.get("profile_snapshot") or {},
        )
        update_ai_session_structured_resume(session, applied, active_blueprints)
        session["resume_revision"] = int(session.get("resume_revision") or 1) + 1
        session["audit_status"] = "applied"
        session["audit_proposal"] = None
        if isinstance(session.get("audit_result"), dict):
            change_ids = [
                record["change_id"]
                for record in _quality_audit_change_records(
                    session["audit_result"].get("changes") or {}
                )
            ]
            session["audit_result"] = {
                **session["audit_result"],
                "accepted_change_ids": change_ids,
                "rejected_change_ids": [],
            }
        session["audit_applied_at"] = datetime.now(timezone.utc).isoformat()
        session["updated_at"] = time.time()
        return jsonify({
            "success": True,
            "session_id": session_id,
            "audit_status": session["audit_status"],
            "audit_result": session.get("audit_result"),
            "audit_proposal": None,
            "audit_base_revision": session.get("audit_base_revision"),
            "audit_base_hash": session.get("audit_base_hash"),
            "audit_applied_at": session["audit_applied_at"],
            "resume_revision": session["resume_revision"],
            "content": session["resume_content"],
            "resume": ai_session_canonical_resume(session, active_blueprints),
            "title_summary": session["title_summary"],
            "skills": session["skills"],
            "experience": ai_session_combined_experience(session),
        })
    except ResumeQualityAuditStaleConflictError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except (ValueError, ResumeQualityAuditValidationError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/ai/quality-audit/resolve", methods=["POST"])
def resolve_ai_resume_quality_audit():
    try:
        data = request.get_json(silent=True) or {}
        session_id = str(data.get("session_id", "")).strip()
        if not session_id:
            return jsonify({"success": False, "error": "session_id is required."}), 400
        if session_id not in ai_sessions:
            return jsonify({"success": False, "error": "AI session not found."}), 404
        session = ensure_ai_session_state(ai_sessions[session_id])
        if session.get("audit_status") != "changes_suggested":
            raise ValueError("There are no unresolved review changes.")

        expected_base_hash = str(
            data.get("expected_base_hash")
            or session.get("audit_base_hash")
            or ""
        ).strip()
        active_blueprints = ai_session_active_blueprints(session)
        supplied_content = str(data.get("current_resume_content", "")).strip()
        if supplied_content:
            accept_ai_session_resume_content(
                session,
                supplied_content,
                active_blueprints,
            )
        current_resume = ai_session_canonical_resume(session, active_blueprints)
        current_hash = canonical_json_hash(current_resume)
        if (
            int(session.get("audit_base_revision") or 0)
            != int(session.get("resume_revision") or 1)
            or current_hash != expected_base_hash
        ):
            session["audit_status"] = "stale"
            session["audit_proposal"] = None
            session["updated_at"] = time.time()
            raise ResumeQualityAuditStaleConflictError(
                expected_base_hash,
                current_hash,
            )

        decisions = data.get("decisions")
        resolved, change_ids, all_rejected = resolve_resume_quality_audit_decisions(
            expected_base_hash=expected_base_hash,
            current_resume=current_resume,
            audit_result=session.get("audit_result") or {},
            decisions=decisions,
            analysis_payload=session.get("analysis") or {},
            active_blueprints=active_blueprints,
            candidate_profile=session.get("profile_snapshot") or {},
        )
        normalized = normalize_resume_quality_audit_decisions(
            decisions,
            change_ids,
        )
        if all_rejected:
            session["audit_status"] = "kept_current"
        else:
            update_ai_session_structured_resume(
                session,
                resolved,
                active_blueprints,
            )
            session["resume_revision"] = int(session.get("resume_revision") or 1) + 1
            session["audit_status"] = "applied"
            session["audit_applied_at"] = datetime.now(timezone.utc).isoformat()
        session["audit_proposal"] = None
        if isinstance(session.get("audit_result"), dict):
            session["audit_result"] = {
                **session["audit_result"],
                "accepted_change_ids": sorted(
                    change_id for change_id, decision in normalized.items()
                    if decision == "accept"
                ),
                "rejected_change_ids": sorted(
                    change_id for change_id, decision in normalized.items()
                    if decision == "reject"
                ),
            }
        session["updated_at"] = time.time()
        return jsonify({
            "success": True,
            "session_id": session_id,
            "audit_status": session["audit_status"],
            "audit_result": session.get("audit_result"),
            "audit_proposal": None,
            "audit_base_revision": session.get("audit_base_revision"),
            "audit_base_hash": session.get("audit_base_hash"),
            "audit_applied_at": session.get("audit_applied_at"),
            "resume_revision": session["resume_revision"],
            "content": session.get("resume_content", ""),
            "resume": ai_session_canonical_resume(session, active_blueprints),
            "title_summary": session.get("title_summary") or {},
            "skills": session.get("skills") or {},
            "experience": ai_session_combined_experience(session),
        })
    except ResumeQualityAuditStaleConflictError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except (ValueError, ResumeQualityAuditValidationError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/ai/quality-audit/keep-current", methods=["POST"])
def keep_current_ai_resume_quality_audit():
    try:
        data = request.get_json(silent=True) or {}
        session_id = str(data.get("session_id", "")).strip()
        if not session_id:
            return jsonify({"success": False, "error": "session_id is required."}), 400
        if session_id not in ai_sessions:
            return jsonify({"success": False, "error": "AI session not found."}), 404
        session = ensure_ai_session_state(ai_sessions[session_id])
        if session.get("audit_status") != "changes_suggested":
            raise ValueError("There is no unresolved audit to keep.")

        session["audit_status"] = "kept_current"
        session["audit_proposal"] = None
        if isinstance(session.get("audit_result"), dict):
            change_ids = [
                record["change_id"]
                for record in _quality_audit_change_records(
                    session["audit_result"].get("changes") or {}
                )
            ]
            session["audit_result"] = {
                **session["audit_result"],
                "accepted_change_ids": [],
                "rejected_change_ids": change_ids,
            }
        session["updated_at"] = time.time()
        active_blueprints = ai_session_active_blueprints(session)
        return jsonify({
            "success": True,
            "session_id": session_id,
            "audit_status": session["audit_status"],
            "audit_result": session.get("audit_result"),
            "audit_proposal": None,
            "resume_revision": session["resume_revision"],
            "content": session.get("resume_content", ""),
            "resume": ai_session_canonical_resume(session, active_blueprints),
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route("/api/ai/regenerate", methods=["POST"])
def regenerate_ai_resume():
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id", "")).strip()
    if not session_id:
        return jsonify({"success": False, "error": "session_id is required."}), 400
    if session_id not in ai_sessions:
        return jsonify({"success": False, "error": "AI session not found."}), 404

    session = ensure_ai_session_state(ai_sessions[session_id])
    session["turns"] = []
    session["title_summary"] = None
    session["skills"] = None
    session["core_resume"] = None
    session["experience_recent"] = None
    session["experience_older"] = None
    session["resume_content"] = ""
    session["resume_revision"] = int(session.get("resume_revision") or 1) + 1
    clear_ai_session_audit(session)
    session["updated_at"] = time.time()
    state = ai_session_state_payload(session)
    return jsonify({
        "success": True,
        "session_id": session_id,
        "session": state,
        **state,
    })


@app.route("/api/ai/generate-reachout", methods=["POST"])
def generate_ai_reachout():
    try:
        data = request.get_json() or {}
        job_description = str(data.get("job_description", "")).strip()
        current_resume_content = str(data.get("current_resume_content", "")).strip()
        session_id = str(data.get("session_id", "")).strip() or None

        if not job_description:
            return jsonify({"success": False, "error": "Job description is required"}), 400

        if not current_resume_content:
            return jsonify({"success": False, "error": "Generate the resume first before creating a reachout message."}), 400

        if not session_id or session_id not in ai_sessions:
            return jsonify({"success": False, "error": "An active JD session is required before creating a reachout message."}), 400

        session = ai_sessions[session_id]
        analysis_payload = session.get("analysis")
        if not analysis_payload:
            return jsonify({"success": False, "error": "JD analysis is required before creating a reachout message."}), 400

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY is not configured"}), 500

        started = time.perf_counter()
        try:
            reachout_payload = generate_reachout_message(
                api_key=api_key,
                job_description=job_description,
                analysis_payload=analysis_payload,
                current_resume_content=current_resume_content,
                recipient_name=str(data.get("recipient_name", "")),
                target_company=str(data.get("company_name", "")),
                target_role=str(data.get("role_title", "")),
            )
        except Exception as exc:
            raise AIStageError("reachout_generation", f"Reachout generation failed: {exc}", analysis=analysis_payload) from exc

        timing = {"reachout_ms": int((time.perf_counter() - started) * 1000)}
        timing["total_ms"] = timing["reachout_ms"]

        issues = validate_reachout_payload(reachout_payload)
        if issues:
            raise AIStageError(
                "reachout_generation",
                "Reachout generation failed validation: " + " | ".join(issues[:3]),
                analysis=analysis_payload,
                timing=timing,
            )

        session["updated_at"] = time.time()

        return jsonify({
            "success": True,
            "session_id": session_id,
            "reachout": reachout_payload,
            "timing": timing,
        })
    except AIStageError as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "stage": e.stage,
            "analysis": e.analysis,
            "timing": e.timing,
            "session_id": session_id if 'session_id' in locals() else None,
        }), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/generate-followup", methods=["POST"])
def generate_ai_followup():
    try:
        data = request.get_json() or {}
        job_description = str(data.get("job_description", "")).strip()
        question = str(data.get("question", "")).strip()
        pdf_path = str(data.get("pdf_path", "")).strip()
        session_id = str(data.get("session_id", "")).strip() or None

        if not job_description:
            return jsonify({"success": False, "error": "Job description is required"}), 400
        if not question:
            return jsonify({"success": False, "error": "A follow-up question is required."}), 400
        if not pdf_path:
            return jsonify({"success": False, "error": "Generate the final PDF first before answering follow-up questions."}), 400
        if not session_id or session_id not in ai_sessions:
            return jsonify({"success": False, "error": "An active JD session is required before answering follow-up questions."}), 400

        session = ai_sessions[session_id]
        analysis_payload = session.get("analysis")
        if not analysis_payload:
            return jsonify({"success": False, "error": "JD analysis is required before answering follow-up questions."}), 400

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY is not configured"}), 500

        resume_pdf_text = extract_text_from_pdf(pdf_path)

        started = time.perf_counter()
        try:
            followup_payload = generate_followup_answer(
                api_key=api_key,
                job_description=job_description,
                analysis_payload=analysis_payload,
                question=question,
                resume_pdf_text=resume_pdf_text,
            )
        except Exception as exc:
            raise AIStageError("followup_generation", f"Follow-up answer generation failed: {exc}", analysis=analysis_payload) from exc

        timing = {"followup_ms": int((time.perf_counter() - started) * 1000)}
        timing["total_ms"] = timing["followup_ms"]
        session["updated_at"] = time.time()

        return jsonify({
            "success": True,
            "session_id": session_id,
            "followup": followup_payload,
            "timing": timing,
        })
    except AIStageError as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "stage": e.stage,
            "analysis": e.analysis,
            "timing": e.timing,
        }), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def generate():
    """Generate resume DOCX and start PDF conversion."""
    try:
        data = request.get_json() or {}
        content = data.get("content", "").strip()
        has_resume_override = isinstance(data.get("resume_override"), dict)
        resume_override = data.get("resume_override") if has_resume_override else None
        validated_resume_override = None

        if has_resume_override:
            ai_session_id = str(data.get("ai_session_id", "")).strip()
            if not ai_session_id:
                return jsonify({
                    "success": False,
                    "error": "An active AI session is required to generate this PDF.",
                }), 400
            if ai_session_id not in ai_sessions:
                return jsonify({
                    "success": False,
                    "error": "AI session not found. Regenerate the resume before creating the PDF.",
                }), 404

            session = ensure_ai_session_state(ai_sessions[ai_session_id])
            try:
                resume_state_changed, active_blueprints = prepare_ai_session_for_pdf(
                    session,
                    content,
                    data.get("enabled_experience_keys")
                    if "enabled_experience_keys" in data
                    else None,
                )
            except ValueError as exc:
                return jsonify({
                    "success": False,
                    "error": str(exc),
                }), 400

            audit_status = str(session.get("audit_status") or "not_started")
            if audit_status not in AI_PDF_ALLOWED_AUDIT_STATUSES:
                return jsonify({
                    "success": False,
                    "error": (
                        "Resume review is not resolved for the current revision. "
                        "Complete the review before generating the PDF."
                    ),
                    "audit_status": audit_status,
                    "resume_revision": int(session.get("resume_revision") or 1),
                }), 409

            canonical_session = ai_session_canonical_resume(
                session,
                active_blueprints,
            )
            if resume_state_changed:
                resume_override = resume_override_with_canonical_content(
                    resume_override,
                    canonical_session,
                    active_blueprints,
                )
            canonical_override, validated_resume_override = canonical_resume_override_for_pdf(
                resume_override,
                active_blueprints,
            )
            if canonical_json_hash(canonical_override) != canonical_json_hash(canonical_session):
                return jsonify({
                    "success": False,
                    "error": (
                        "Resume preview does not match the reviewed resume content. "
                        "Refresh the preview and complete the review before generating the PDF."
                    ),
                    "audit_status": audit_status,
                    "resume_revision": int(session.get("resume_revision") or 1),
                }), 409

        # Validate
        errors, warnings = validate_updated_content(content)
        if errors:
            return jsonify({
                "success": False,
                "error": f"Validation failed: {errors[0]}"
            }), 400

        # Parse content
        if has_resume_override:
            merged_resume = validated_resume_override
        else:
            base_resume = load_base_resume()
            merged_resume = parse_updated_content_to_resume(content, base_resume)
            merged_resume = apply_profile_overrides(merged_resume)
            merged_resume = apply_experience_history_override(merged_resume, data.get("experience_history_override"))
            merged_resume = apply_enabled_experience_filter(merged_resume, data.get("enabled_experience_keys"))
        selected_identity = identity_profile_by_id(data.get("identity", ""))
        identity = selected_identity.get("id", "outlook")
        format_profile = selected_identity.get("format_profile", "outlook")

        contact_override = data.get("contact_override") or {}
        if isinstance(contact_override, dict):
            merged_resume["contact"] = {
                **merged_resume.get("contact", {}),
                **{
                    key: str(contact_override.get(key, "")).strip()
                    for key in ("location", "phone", "email")
                    if str(contact_override.get(key, "")).strip()
                },
            }

        # Create output directory
        title = merged_resume.get("title", "Resume")
        company_name = data.get("company_name", "").strip()
        # Use custom folder name if provided, otherwise generate from title
        custom_folder = data.get("folder_name", "").strip()
        folder_source = display_folder_name(company_name, title, custom_folder)
        folder_name = safe_folder_name(folder_source, settings["output_directory"])
        out_dir = Path(settings["output_directory"]) / folder_name
        out_dir.mkdir(parents=True, exist_ok=True)

        # Build DOCX
        docx_path = out_dir / "tharun manikonda resume.docx"
        build_resume_docx(merged_resume, str(docx_path), format_profile=format_profile)

        # Start background PDF conversion
        pdf_path = out_dir / "tharun manikonda resume.pdf"
        status_path = out_dir / "pdf_status.json"
        metadata = {
            "job_id": str(data.get("job_id", "")).strip(),
            "folder": folder_name,
            "company_name": company_name,
            "identity": identity,
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "docx": str(docx_path),
            "pdf": str(pdf_path),
            "status_path": str(status_path),
            "output_dir": str(out_dir),
        }

        # Launch background PDF conversion.
        start_pdf_conversion(docx_path, pdf_path, status_path)
        return jsonify({
            "success": True,
            "folder": folder_name,
            "title": title,
            "docx": str(docx_path),
            "pdf": str(pdf_path),
            "status_path": str(status_path),
            "output_dir": str(out_dir),
            "metadata": metadata,
        })

    except Exception as e:
        print(f"Error in generate: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/status", methods=["GET"])
def status():
    """Get PDF conversion status."""
    try:
        status_path = request.args.get("path", "").strip()
        if not status_path:
            return jsonify({"error": "Missing 'path' parameter"}), 400

        status_data = get_conversion_status(status_path)
        return jsonify(status_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/config/base_resume.json", methods=["GET"])
def get_base_resume():
    """Serve base resume JSON for frontend parsing."""
    return send_file(
        BASE_RESUME_PATH,
        mimetype="application/json"
    )


@app.route("/api/download", methods=["GET"])
def download():
    """Download or preview PDF file."""
    try:
        pdf_path = request.args.get("path", "").strip()
        preview = request.args.get("preview", "").lower() == "true"

        if not pdf_path:
            return jsonify({"error": "Missing 'path' parameter"}), 400

        try:
            resolved_path = require_within_output(pdf_path)
        except FileNotFoundError:
            return jsonify({"error": "PDF not found"}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403

        filename = resolved_path.name
        file_size = resolved_path.stat().st_size
        status = 200
        headers = {}

        range_header = request.headers.get("Range", "")
        match = re.match(r"bytes=(\d*)-(\d*)$", range_header)

        if match:
            start_raw, end_raw = match.groups()

            if start_raw == "" and end_raw == "":
                return Response(status=416, headers={"Content-Range": f"bytes */{file_size}"})

            if start_raw == "":
                suffix_length = int(end_raw)
                start = max(file_size - suffix_length, 0)
                end = file_size - 1
            else:
                start = int(start_raw)
                end = int(end_raw) if end_raw else file_size - 1
                end = min(end, file_size - 1)

            if start >= file_size or start > end:
                return Response(status=416, headers={"Content-Range": f"bytes */{file_size}"})

            length = end - start + 1
            with open(resolved_path, "rb") as f:
                f.seek(start)
                data = f.read(length)

            status = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        else:
            with open(resolved_path, "rb") as f:
                data = f.read()
            length = file_size

        response = Response(data, status=status, mimetype="application/pdf")
        response.headers["Content-Length"] = str(length)
        response.headers["Accept-Ranges"] = "bytes"

        if not preview:
            response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        else:
            response.headers["Content-Disposition"] = f'inline; filename="{filename}"'

        for key, value in headers.items():
            response.headers[key] = value

        response.headers["Content-Type"] = "application/pdf"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/open-folder", methods=["POST"])
def open_folder():
    """Open a generated resume folder in the local file manager."""
    try:
        data = request.get_json() or {}
        folder_path = data.get("path", "").strip()
        if not folder_path:
            return jsonify({"success": False, "error": "Missing folder path"}), 400
        folder = require_within_output(folder_path)
        if folder.is_file():
            folder = folder.parent
        open_path(folder)
        return jsonify({"success": True})
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Folder not found"}), 404
    except PermissionError as e:
        return jsonify({"success": False, "error": str(e)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/select-output-directory", methods=["POST"])
def select_output_directory():
    """Choose an output directory with a native local dialog when available."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(initialdir=settings.get("output_directory") or str(default_output_dir()))
        root.destroy()

        if not selected:
            return jsonify({"success": False, "cancelled": True})

        output_directory = str(Path(selected).expanduser().resolve())
        Path(output_directory).mkdir(parents=True, exist_ok=True)
        settings["output_directory"] = output_directory
        save_settings(settings)
        return jsonify({"success": True, "output_directory": output_directory})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check."""
    ok, msg = get_pdf_conversion_status()
    ai_ok, ai_msg = is_ai_generation_ready()
    return jsonify({
        "status": "ok",
        "pdf_conversion_ready": ok,
        "pdf_conversion_status": msg,
        "ai_generation_ready": ai_ok,
        "ai_generation_status": ai_msg,
        "output_directory": settings.get("output_directory"),
        "output_directory_writable": os.access(settings.get("output_directory", ""), os.W_OK),
        "settings_file": str(SETTINGS_FILE),
        "timestamp": datetime.now().isoformat()
    })


@app.after_request
def add_caching_headers(response):
    """Add caching headers for performance."""
    # Skip for file downloads and binary responses
    if response.direct_passthrough or response.is_streamed:
        return response

    if response.content_type and ('text/css' in response.content_type or 'javascript' in response.content_type):
        response.cache_control.max_age = 604800  # 1 week
        response.cache_control.public = True
    return response


if os.getenv("RESUME_DISABLE_EXTENSION_WORKER", "").strip().lower() not in {"1", "true", "yes"}:
    ensure_extension_worker_started()


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5001))
    app.run(debug=False, host="127.0.0.1", port=port, threaded=True)
