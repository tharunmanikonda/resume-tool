#!/usr/bin/env python3
"""
Modern Flask Resume Generator App
- Manual content input → Parse → Generate PDF
- No AI needed, just template replacement
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
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

# Load environment variables from .env file
load_dotenv()


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

TRACKER_STATUSES = ["Applied", "Updated", "Converted", "Ghosted", "Rejected"]

ANALYSIS_MODEL = os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-4o-mini")
RESUME_MODEL = os.getenv("OPENAI_RESUME_MODEL", "gpt-5-mini")
ANALYSIS_TEMPERATURE = 0.2
RESUME_TEMPERATURE = 0.4
AI_MEMORY_LIMIT = 2
ANALYSIS_MAX_OUTPUT_TOKENS = 2400
RESUME_MAX_OUTPUT_TOKENS = 7800
SMALL_OUTPUT_HEADROOM = 200
MEDIUM_OUTPUT_HEADROOM = 300
LARGE_OUTPUT_HEADROOM = 500
OPENAI_ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("OPENAI_ANALYSIS_TIMEOUT_SECONDS", "120"))
OPENAI_RESUME_TIMEOUT_SECONDS = int(os.getenv("OPENAI_RESUME_TIMEOUT_SECONDS", "180"))
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


def tracker_company_history(company_name: str) -> dict:
    normalized = normalize_company_lookup(company_name)
    if not normalized:
        return {"company_name": str(company_name or "").strip(), "count": 0, "applications": []}

    store = load_tracker_store()
    applications = merge_tracker_applications(store)
    matches = [
        item for item in applications
        if normalize_company_lookup(item.get("company_name", "")) == normalized
    ]
    matches = sorted_tracker_applications(matches, sort_key="applied_date", descending=True)
    summarized = []
    for item in matches:
        summarized.append({
            "id": item.get("id", ""),
            "company_name": item.get("company_name", ""),
            "applied_date": item.get("applied_date", ""),
            "status": normalize_tracker_status(item.get("status", "")),
            "role_title": item.get("role_title", ""),
            "resume_title": str((item.get("resume_snapshot") or {}).get("title", "")).strip() or item.get("role_title", ""),
            "folder_group": item.get("folder_group", ""),
            "output_dir": item.get("output_dir", ""),
            "job_url": item.get("job_url", ""),
        })
    return {
        "company_name": matches[0].get("company_name", company_name) if matches else str(company_name or "").strip(),
        "count": len(matches),
        "applications": summarized,
    }


def tracker_application_by_id(application_id: str) -> dict | None:
    store = load_tracker_store()
    applications = merge_tracker_applications(store)
    return next((item for item in applications if str(item.get("id", "")) == str(application_id)), None)


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
    return True, f"Ready (analysis={ANALYSIS_MODEL}, resume={RESUME_MODEL})"


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
            "turns": [],
            "analysis": None,
            "title_summary": None,
            "skills": None,
            "core_resume": None,
            "experience_recent": None,
            "experience_older": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        ai_sessions[new_session_id] = session
        return new_session_id, session

    session = ai_sessions[session_id]
    if session.get("job_description") != job_description:
        session["job_description"] = job_description
        session["turns"] = []
        session["analysis"] = None
        session["title_summary"] = None
        session["skills"] = None
        session["core_resume"] = None
        session["experience_recent"] = None
        session["experience_older"] = None
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


def compact_analysis_for_generation(analysis_payload: dict) -> dict:
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
        "skill_category_order_key": str(analysis_payload.get("skill_category_order_key", "")).strip(),
        "prompt_family_key": str(analysis_payload.get("prompt_family_key", "")).strip(),
        "core_problem": str(analysis_payload.get("core_problem", "")).strip(),
        "hire_problem": str(analysis_payload.get("hire_problem", "")).strip(),
        "desired_outcomes": compact_list(analysis_payload.get("desired_outcomes", []), 4),
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

    if (
        normalized.get("prompt_family_key") == "solutions_customer"
        and "integration" in combined_signals
        and looks_backend_integration
        and not looks_customer_facing
    ):
        normalized["role_family"] = "backend application engineering"
        normalized["prompt_family_key"] = "software_engineering"
        normalized["skill_category_order_key"] = "backend_application"
    elif (
        "integration" in role_family_lower
        and looks_backend_integration
        and not looks_customer_facing
    ):
        normalized["role_family"] = "backend application engineering"
        normalized["prompt_family_key"] = "software_engineering"
        normalized["skill_category_order_key"] = "backend_application"

    if not str(normalized.get("skill_category_order_key", "")).strip():
        normalized["skill_category_order_key"] = infer_skill_category_order_key(normalized.get("role_family", ""))
    if not str(normalized.get("prompt_family_key", "")).strip():
        normalized["prompt_family_key"] = infer_prompt_family_key(normalized.get("role_family", ""))
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
            "Infer the company context, role family, problem, system, skills and technologies mentioned, and behavioral signals.",
            "Role family must describe the actual job shape, not a generic software-engineer label.",
            "Prefer precise role-family labels such as: full-stack product engineering, backend application engineering, data engineering, analytics engineering, data science, machine learning engineering, platform engineering, distributed systems engineering, cloud infrastructure engineering, security engineering, application security engineering, cloud security engineering, solutions engineering, implementation engineering, AI application engineering, agentic AI engineering, AI agent engineering, data analyst, business analyst, marketing analyst, product analyst, operations analyst, or GTM engineering.",
            "Choose exactly one skill_category_order_key from this fixed set: fullstack_product, backend_application, data_engineering, data_science, platform_distributed, embedded_systems, ai_application, agentic_ai_engineering, security_engineering, solutions_engineering, analyst_data, analyst_business, analyst_marketing, gtm_engineering.",
            "Pick the skill_category_order_key that best fits the role family and technical center of the JD.",
            "Choose exactly one prompt_family_key from this fixed set: software_engineering, data_engineering, data_science, platform_systems, agentic_ai_engineering, security_engineering, analyst_data, analyst_business, analyst_marketing, solutions_customer, gtm_engineering.",
            "Pick the prompt_family_key that best matches the role family and what the later prompts should optimize for.",
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
            "Return only structured analysis matching the schema.",
        ]
    )


def build_ai_resume_prompt() -> str:
    blueprint_lines = []
    enabled_keys = resume.get("_enabled_experience_keys")
    for blueprint in filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_keys):
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
            "- Each bullet must be 25-30 words",
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
            "[Strong Verb] + [System built/optimized] + using [1-3 tools] + under [constraint or engineering decision] + resulting in [measurable impact].",
            "",
            "Each bullet must include:",
            "- Real system context",
            "- 1-3 tools or relevant technical skills",
            "- At least one:",
            "  - constraint such as scale, latency, concurrency, failures",
            "  - or engineering decision such as caching, batching, async, indexing",
            "- At least one measurable metric such as %, latency, scale, volume, or count",
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
            "- Use measurable achievements wherever possible",
            "- Make impact visible through numbers, metrics, volume, latency, accuracy, scale, cost, reliability, or speed",
            "- Be specific instead of hand-wavy whenever the candidate could realistically defend the detail",
            "- Do not force exact years of experience into the summary unless that count is explicitly grounded by the candidate profile or clearly implied by the fixed timeline",
            "- Prefer a compact positioning summary over a dense stack summary",
            "- Prefer believable metrics over suspiciously perfect precision; when a softer, defensible metric communicates the same impact, use it",
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
            "- Each bullet has system + tool + constraint/decision + metric",
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
            "- include systems, technologies, and problems solved",
            "- do not state an explicit years-of-experience count unless it is clearly safe and helpful",
            "- align to the company's domain without overclaiming direct domain expertise",
            "- do not echo company marketing language, product slogans, or copied business phrasing from the JD",
            "- prefer transferable product and workflow framing over company-specific wording when the domain match is only adjacent",
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
            "Treat all important JD-mentioned skills and technologies as valid signals for the final section.",
            "",
            "SKILLS:",
            "- use only the provided categories",
            "- do not invent new categories",
            "- each item must be one concrete tool, platform, language, framework, database, cloud service, enterprise system, or concise capability name",
            "- no explanations, no qualifier text, no mini-sentences",
            "- prefer exact product and technology names over abstract wording whenever the JD supports them",
            "- include tools explicitly named in the JD first",
            "- include closely related enterprise tools only when they fit the JD's domain, category, and role family",
            "- do not use vague filler like 'data-driven solutions', 'deployment strategies', or 'technical discussions'",
            "- do not add broad software concepts such as software design, system design, event-driven systems, debugging, or stakeholder communication unless the exact phrase appears in the JD or it is clearly needed as a standard skill label",
            "- do not repeat the same concept across categories",
            "- skip a category only if it is truly irrelevant; otherwise fill it with 2-5 strong items",
            "- each item must read like a real recruiter-searchable skill, not a broken fragment or half sentence",
            "- if an item looks truncated, awkward, abstract, or too descriptive, rewrite it into a clean recruiter-scan term or remove it",
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
            "- recent roles should highlight pipelines, warehousing, orchestration, data quality, reporting data flows, and measurable operational improvement",
            "- describe systems and workflows in data terms rather than generic product-engineering language",
        ],
        "data_science": [
            "- recent roles should highlight model development, experimentation, feature work, evaluation, deployment support, and measurable business or product impact",
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
            "- Bullet count per company must match exactly",
            "- Each bullet must be 25-30 words",
            "- Recent and relevant roles should do more of the selling",
            *family_rules.get(prompt_family_key, family_rules["software_engineering"]),
            "",
            "BULLET FORMULA:",
            "[Strong Verb] + [System built/optimized] + using [1-3 tools] + under [constraint or engineering decision] + resulting in [measurable impact].",
            "",
            "Each bullet must include:",
            "- real system context",
            "- 1-3 tools or relevant technical skills",
            "- a constraint or engineering decision",
            "- a measurable metric",
            "- active language showing what changed because of the work",
            "- one main accomplishment per bullet",
            "- natural sentence flow instead of visibly templated clause stacking",
            "",
            "ORIGINALITY AND GROUNDING RULES:",
            "- Preserve originality",
            "- Prefer simpler believable technical wording over named-tool substitution",
            "- Do not introduce named infrastructure products unless they materially improve clarity and feel realistically grounded",
            "- Do not introduce named platforms, products, or vendors that are missing from the JD or selected skills just because they are common for the role family",
            "- If a bullet sounds like benchmark distributed-systems copy, simplify it into more natural resume language",
            "- Tailor by emphasis and detail selection, not by rewriting history",
            "- If the target role is FAE, solutions engineering, sales engineering, or technical pre-sales, preserve believable engineering titles and shift the bullets toward demos, integrations, troubleshooting, customer communication, and adoption support only where that remains grounded",
            "- Keep each company aligned to its own realistic role family and time period instead of forcing perfect JD symmetry across all roles",
            "- Prefer believable metrics over suspiciously polished precision when both communicate the same impact",
            "- Avoid revenue, dollar-value, exact-user-count, or very sharp throughput claims unless they are especially well-supported by the candidate's role context",
            "",
            "PROJECT STORY RULE:",
            "- Each company must read as one coherent project story",
            "- Early bullets establish system and problem",
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
            "- selected skills should guide the stack used in bullets; do not invent a different stack from the skills section",
        ],
        "data_engineering": [
            "- selected skills should guide the stack used in bullets; prioritize SQL, pipelines, warehousing, orchestration, and data-quality workflows",
            "- describe systems and impacts in data workflow terms",
        ],
        "data_science": [
            "- selected skills should guide the stack used in bullets; prioritize model development, experimentation, feature work, evaluation, ML platforms, and measurable decision or product impact",
            "- use ML or data-science framing rather than pipeline-engineering framing unless pipelines are central to the JD",
            "- do not introduce ML libraries or model platforms unless they appear in the JD or selected skills",
        ],
        "agentic_ai_engineering": [
            "- selected skills should guide the stack used in bullets; prioritize agent orchestration, LLM APIs, MCP or tool protocols, governance controls, retrieval or memory, evals, tracing, and production reliability",
            "- use agentic AI infrastructure framing rather than generic backend or distributed-systems framing",
            "- do not introduce MCP, agent frameworks, vector databases, or governance tools unless they appear in the JD or selected skills",
        ],
        "platform_systems": [
            "- selected skills should guide the stack used in bullets; prioritize infrastructure, reliability, observability, scale, and system tradeoffs",
        ],
        "security_engineering": [
            "- selected skills should guide the stack used in bullets; prioritize security controls, IAM, vulnerability management, cloud security, SIEM or detection, compliance, and incident response",
            "- use security-engineering framing rather than backend feature-delivery framing",
            "- do not introduce backend frameworks unless they already appear in the JD or selected skills",
            "- do not introduce compliance frameworks unless they already appear in the JD or selected skills",
        ],
        "analyst_data": [
            "- selected skills should guide the stack used in bullets; prioritize reporting, SQL analysis, dashboards, experimentation, and insight delivery",
            "- use workflow, stakeholder, and business-impact framing rather than engineering implementation framing when appropriate",
            "- prefer analyst proof points such as reporting adoption, accuracy, time saved, reconciliation, KPI visibility, and decision support impact",
            "- do not introduce named BI or analyst tools in bullets unless the JD or selected skills already include them",
        ],
        "analyst_business": [
            "- selected skills should guide the stack used in bullets; prioritize requirements, process analysis, reporting, KPI tracking, and stakeholder communication",
            "- use business workflow framing rather than engineering implementation framing when appropriate",
            "- prefer analyst proof points such as UAT, requirements clarity, process-cycle reduction, reporting accuracy, exception handling, and stakeholder alignment",
            "- do not introduce named ERP, WMS, CRM, or enterprise tools in bullets unless the JD or selected skills already include them",
        ],
        "analyst_marketing": [
            "- selected skills should guide the stack used in bullets; prioritize campaign reporting, attribution, funnel analysis, experimentation, and growth insights",
            "- use marketing workflow framing rather than engineering implementation framing when appropriate",
            "- prefer analyst proof points such as campaign lift, funnel conversion, cohort trends, reporting adoption, and experiment outcomes",
            "- do not introduce named CRM, BI, or marketing platforms in bullets unless the JD or selected skills already include them",
        ],
        "gtm_engineering": [
            "- selected skills should guide the stack used in bullets; prioritize CRM workflows, GTM automation, routing, enrichment, outbound systems, reporting, and revops coordination",
            "- use GTM workflow framing rather than generic product-engineering language when appropriate",
            "- prefer GTM proof points such as routing accuracy, enrichment coverage, pipeline visibility, campaign or outbound efficiency, adoption, and stakeholder alignment outcomes",
            "- do not introduce named GTM, CRM, sequencing, or enrichment platforms in bullets unless the JD or selected skills already include them",
            "- if a named GTM tool is not already present in the JD or selected skills, rewrite it as a generic workflow or platform reference instead of adding the tool name",
        ],
        "solutions_customer": [
            "- selected skills should guide the stack used in bullets; prioritize integrations, troubleshooting, customer enablement, and adoption support",
        ],
    }
    return "\n".join(
        [
            "You are a resume reconstruction engine.",
            "Build only the Professional Experience entries requested.",
            "Assume the candidate has 4+ years of experience.",
            "Use the analysis object and selected skills as the source of truth.",
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
            "- recent roles should sell harder than older roles",
            "- each bullet must be 25-30 words",
            "",
            "BULLET DESIGN:",
            "- the first bullet under each company is a simple summary bullet in plain language",
            "- the first bullet must be 25-40 words; the ideal range is 25-30 words",
            "- the first bullet should describe the role and scope clearly without becoming dense",
            "- do not make the first bullet shorter than 25 words",
            "- do not treat the first bullet like a compact fragment; write it as a full accomplishment sentence",
            "- all later bullets should follow:",
            "  - What: the skill, keyword, or qualification",
            "  - How: how it was used",
            "  - Why: why it mattered or what changed",
            "",
            "BULLET FORMULA:",
            "[Strong Verb] + [System or workflow] + using [1-3 tools] + under [constraint or engineering decision] + resulting in [measurable impact].",
            "",
            "Each bullet must include:",
            "- real system or workflow context",
            "- 1-3 tools or technical skills from the selected skills or supporting stack",
            "- a constraint or engineering decision",
            "- a measurable metric",
            "- one main accomplishment per bullet",
            *family_rules.get(prompt_family_key, family_rules["software_engineering"]),
            "- older roles should use the lighter, earlier-career portion of the selected skills instead of inheriting the most modern or specialized parts of the stack",
            "- keep KPMG and Trigent technology choices believable for 2020-2022, their company anchors, and normal exposure progression",
            "- do not backfill newer tools, AI frameworks, or unusually convenient target-stack substitutions into older roles unless the anchor strongly supports them",
            "- if a bullet wants to mention a named platform that is not already in the JD or selected skills, replace it with a generic workflow phrase instead",
            "- prefer simpler wording over dense clause chains when both communicate the same accomplishment",
            "- avoid bullets that read like a rigid template; vary rhythm and sentence structure naturally",
            "",
            "Keep each company as one coherent project story.",
            "Prefer believable metrics over suspicious precision.",
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


def build_ai_core_review_prompt() -> str:
    return "\n".join(
        [
            "You review only the resume summary and skills section for a tailored target-fit resume.",
            "Use the analysis object as the source of truth.",
            "Judge whether the current summary and skills are ready to keep or should be revised.",
            "Focus on three risks:",
            "- summary that sounds copied from company or JD wording, too generic, or mis-emphasized for the role",
            "- skills that include broad capabilities instead of named tools, miss obvious JD tools, or are awkwardly categorized",
            "- wording that sounds stiff, overpacked, truncated, or visibly AI-generated instead of natural resume writing",
            "Flag summaries that stack too many tools, systems, or clauses into one sentence.",
            "Flag skills that read like broken fragments, process phrases, or abstract concepts instead of named recruiter-searchable tools.",
            "Do not flag a skills section just because it could include more adjacent tools; refinement must not broaden the stack.",
            "Do not review professional experience.",
            "Be concise and practical.",
            "Return only the final result matching the schema.",
        ]
    )


def build_ai_core_correction_prompt() -> str:
    return "\n".join(
        [
            "You refine only the resume summary and skills section for a tailored target-fit resume.",
            "Use the analysis object and current draft as the source of truth.",
            "Keep the title unchanged outside the schema; only return Updated Summary and Updated Skills.",
            "Inspect the current summary and skills, improve them only if needed, and otherwise keep them close to the draft.",
            "Follow the role family and the JD facts from the analysis object.",
            "Use the skills_mentioned list, responsibilities, and workflows to keep the strongest role match visible.",
            "Use only the provided skill categories and keep them in the provided order.",
            "Focus on sharper role emphasis, cleaner summary phrasing, and more concrete, believable skills.",
            "Do not let the refinement smooth a data, platform, AI application, or solutions role back into generic software-engineering language.",
            "Do not replace strong concrete stack or workflow terms with broader wording just because it sounds cleaner.",
            "If the summary mentions years of experience at all, it must say 4+ years and never anything higher.",
            "Do not copy JD wording directly.",
            "Make the writing sound human and recruiter-natural, not optimized or assembled.",
            "Break up dense phrasing, remove stacked jargon, and rewrite truncated skill items into clean terms.",
            "Do not touch professional experience.",
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
            "skill_category_order_key": {"type": "string", "enum": sorted(SKILL_CATEGORY_ORDER_TEMPLATES.keys())},
            "prompt_family_key": {"type": "string", "enum": ["software_engineering", "data_engineering", "platform_systems", "analyst_data", "analyst_business", "analyst_marketing", "solutions_customer", "gtm_engineering"]},
            "core_problem": {"type": "string"},
            "hire_problem": {"type": "string"},
            "desired_outcomes": {"type": "array", "items": {"type": "string"}},
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
            "skill_category_order_key",
            "prompt_family_key",
            "core_problem",
            "hire_problem",
            "desired_outcomes",
            "system_description",
            "responsibilities",
            "workflows",
            "skills_mentioned",
            "behavioral_signals",
            "gaps",
        ],
    }


def ai_resume_schema() -> dict:
    allowed_skill_categories = sorted(ALLOWED_SKILL_CATEGORIES)
    skill_item_schema = {
        "type": "string",
        "minLength": 2,
        "maxLength": 48,
        "pattern": r"^[A-Za-z0-9+#.&' -]+$",
    }
    experience_properties = {}
    required_experience_keys = []
    for blueprint in current_experience_blueprints():
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


def ai_core_correction_schema(allowed_skill_categories: list[str] | None = None) -> dict:
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
        },
        "required": ["updated_summary", "updated_skills"],
    }


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

ENGINEERING_TITLE_MARKERS = {
    "engineer",
    "developer",
    "full stack",
    "frontend",
    "backend",
    "applied ai",
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
    prompt_family_key = infer_prompt_family_key((analysis_payload or {}).get("role_family", ""))
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
    prompt_family_key = infer_prompt_family_key((analysis_payload or {}).get("role_family", ""))
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

    normalized_cleaned = cleaned.lower()
    if prompt_family_key.startswith("analyst_") and any(marker in normalized_cleaned for marker in ENGINEERING_TITLE_MARKERS):
        return fallback_title, (
            f"{blueprint['company']}: model returned title '{cleaned}', but it conflicts with the analyst-family routing. "
            f"Fallback title '{fallback_title}' was applied."
        )
    if prompt_family_key == "gtm_engineering" and "gtm engineer" not in normalized_cleaned and any(marker in normalized_cleaned for marker in ENGINEERING_TITLE_MARKERS):
        return fallback_title, (
            f"{blueprint['company']}: model returned title '{cleaned}', but it conflicts with the GTM-family routing. "
            f"Fallback title '{fallback_title}' was applied."
        )

    return cleaned or fallback_title, None


def format_generated_resume_text(resume_payload: dict) -> str:
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
    for blueprint in filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_keys):
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
    req = urllib.request.Request(
        OPENAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=request_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error ({exc.code}): {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"OpenAI API request timed out after {request_timeout_seconds}s") from exc


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
    response_payload = _post_openai_payload(
        api_key=api_key,
        payload=payload,
        request_timeout_seconds=request_timeout_seconds,
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
    prompt_family = str(analysis_payload.get("prompt_family_key", "")).strip().lower()
    return prompt_family in {"analyst_data", "analyst_business", "analyst_marketing"}


def is_gtm_prompt_family(analysis_payload: dict) -> bool:
    prompt_family = str(analysis_payload.get("prompt_family_key", "")).strip().lower()
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


def validate_model_payload(model_payload: dict) -> list[str]:
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

    for blueprint in current_experience_blueprints():
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
            if not (25 <= word_count <= 30):
                issues.append(f"{blueprint['company']} bullet {index} must be 25-30 words; got {word_count}.")
            if not bullet.endswith("."):
                issues.append(f"{blueprint['company']} bullet {index} must end with a period.")
            if not re.search(r"\d", bullet):
                issues.append(f"{blueprint['company']} bullet {index} must contain a measurable metric.")
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
    if len(message) > 300:
        issues.append(f"Reachout message must be 300 characters or fewer; got {len(message)}.")
    if isinstance(char_count, int) and char_count != len(message):
        issues.append("Reachout character count does not match the message length.")
    if re.search(r"[•#\"“”]", message):
        issues.append("Reachout message contains unsupported formatting.")

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
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
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
        developer_prompt=build_ai_resume_prompt(),
        user_prompt="\n\n".join(resume_user_parts),
        schema_name="resume_generation",
        schema=ai_resume_schema(),
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
    order_key = str(analysis_payload.get("skill_category_order_key", "")).strip() or infer_skill_category_order_key(
        analysis_payload.get("role_family", "")
    )
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
    prompt_family_key = str(analysis_payload.get("prompt_family_key", "")).strip() or infer_prompt_family_key(
        analysis_payload.get("role_family", "")
    )
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
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    prompt_family_key = str(analysis_payload.get("prompt_family_key", "")).strip() or infer_prompt_family_key(
        analysis_payload.get("role_family", "")
    )
    order_key = str(analysis_payload.get("skill_category_order_key", "")).strip() or infer_skill_category_order_key(
        analysis_payload.get("role_family", "")
    )
    ordered_categories = skill_category_order_for_key(order_key)
    user_parts = [
        "Analysis:\n" + json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
        f"Skill category order key: {order_key}",
        "Fill these categories in this exact order:",
        json.dumps(ordered_categories, ensure_ascii=False),
    ]

    def run_generation(extra_instruction: str = "") -> dict:
        prompt_parts = list(user_parts)
        if extra_instruction:
            prompt_parts.append(extra_instruction)
        raw_payload = call_openai_structured_output(
            api_key=api_key,
            model=ANALYSIS_MODEL,
            temperature=ANALYSIS_TEMPERATURE,
            developer_prompt=build_ai_resume_skills_prompt(prompt_family_key),
            user_prompt="\n\n".join(prompt_parts),
            schema_name="resume_skills_generation",
            schema=ai_skills_schema(ordered_categories),
            max_output_tokens=with_output_headroom(2600, MEDIUM_OUTPUT_HEADROOM),
            request_timeout_seconds=OPENAI_ANALYSIS_TIMEOUT_SECONDS,
            reasoning_effort="low",
        )
        return normalize_skills_for_order(raw_payload, ordered_categories)

    skills_payload = run_generation()
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
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    current_core = merge_core_sections(title_summary_payload, skills_payload)
    order_key = str(analysis_payload.get("skill_category_order_key", "")).strip() or infer_skill_category_order_key(
        analysis_payload.get("role_family", "")
    )
    ordered_categories = skill_category_order_for_key(order_key)
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
    ]
    return call_openai_structured_output(
        api_key=api_key,
        model=RESUME_MODEL,
        temperature=RESUME_TEMPERATURE,
        developer_prompt=build_ai_core_correction_prompt(),
        user_prompt="\n\n".join(user_parts),
        schema_name="resume_core_correction",
        schema=ai_core_correction_schema(ordered_categories),
        max_output_tokens=with_output_headroom(2600, MEDIUM_OUTPUT_HEADROOM),
        request_timeout_seconds=OPENAI_RESUME_TIMEOUT_SECONDS,
        reasoning_effort="low",
    )


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
    prompt_family_key = str(analysis_payload.get("prompt_family_key", "")).strip() or infer_prompt_family_key(
        analysis_payload.get("role_family", "")
    )
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
    if unsupported_tool_issues:
        retry_lines = [
            "Previous attempt used named tools in experience bullets that are not supported by the JD.",
            "Rewrite those bullets using JD-grounded tools or generic workflow language.",
            "If the JD does not mention a named tool, do not introduce one in any bullet.",
            "Fix these exact issues:",
            *[f"- {issue}" for issue in unsupported_tool_issues],
        ]
        experience_payload = run_generation("\n".join(retry_lines))

    experience_payload = sanitize_experience_payload_for_prompt_family(experience_payload, analysis_payload)
    experience_payload["_enabled_experience_keys"] = [blueprint["key"] for blueprint in blueprints]
    return experience_payload


def generate_experience_subset_from_analysis(
    *,
    api_key: str,
    analysis_payload: dict,
    core_payload: dict,
    blueprints: list[dict],
    model: str,
    timeout_seconds: int,
) -> dict:
    compact_analysis = compact_analysis_for_generation(analysis_payload)
    prompt_family_key = str(analysis_payload.get("prompt_family_key", "")).strip() or infer_prompt_family_key(
        analysis_payload.get("role_family", "")
    )
    compact_core = {
        "updated_title": str(core_payload.get("updated_title", "")).strip(),
        "updated_summary": str(core_payload.get("updated_summary", "")).strip(),
        "updated_skills": core_payload.get("updated_skills", []),
    }
    user_parts = [
        "Analysis:",
        json.dumps(compact_analysis, ensure_ascii=False, separators=(",", ":")),
        "Selected resume core:",
        json.dumps(compact_core, ensure_ascii=False, separators=(",", ":")),
    ]
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
    if unsupported_tool_issues:
        retry_lines = [
            "Previous attempt used named tools in experience bullets that are not supported by the JD.",
            "Rewrite those bullets using JD-grounded tools or generic workflow language.",
            "If the JD does not mention a named tool, do not introduce one in any bullet.",
            "Fix these exact issues:",
            *[f"- {issue}" for issue in unsupported_tool_issues],
        ]
        experience_payload = run_generation("\n".join(retry_lines))
    experience_payload["_enabled_experience_keys"] = [blueprint["key"] for blueprint in blueprints]
    return experience_payload


def generate_reachout_message(
    *,
    api_key: str,
    job_description: str,
    analysis_payload: dict,
    current_resume_content: str = "",
) -> dict:
    compact_analysis = compact_analysis_for_reachout(analysis_payload)
    resume_snapshot = extract_reachout_resume_snapshot(current_resume_content)
    target_company = ""
    company_match = re.search(r"^\s*([A-Z][A-Za-z0-9&.,' -]{1,80})\s+is\s+", job_description.strip())
    if company_match:
        target_company = company_match.group(1).strip()

    user_parts = [
        "Write one LinkedIn reachout message for a recruiter or hiring manager.",
        "Keep it under 300 characters total.",
        "Match this shape exactly:",
        "Hey <name>, keeping this short:",
        "I'm a full-stack engineer working across React, Node.js, Python, and Postgres.",
        "I'm especially interested in this role because it fits customer-driven product work and AI workflow delivery.",
        "What can I do to get an interview? Thanks for your time!",
        f"Target company: {target_company or 'unknown'}",
        f"Target role: {compact_analysis.get('target_role', '')}",
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
    if len(message) > 300:
        message = message[:300].rstrip()
        if " " in message:
            message = message.rsplit(" ", 1)[0].rstrip(" ,.;")
    return {"message": message, "char_count": len(message)}


def call_openai_resume_engine(
    job_description: str,
    revision_request: str,
    memory_turns: list[dict],
    current_resume_content: str = "",
    cached_analysis: dict | None = None,
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

    issues = validate_model_payload({"analysis": analysis_payload, "resume": parsed_resume})
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


def load_permanent_profile_doc() -> dict | None:
    if not Path(PERMANENT_PROFILE_FILE).exists():
        return None
    return load_json_file(Path(PERMANENT_PROFILE_FILE), load_profile_template())


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

    for field in ("projects", "certifications", "experience_history"):
        if field in override and isinstance(override.get(field), list):
            merged[field] = override.get(field)

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


def start_pdf_conversion(docx_path: Path, pdf_path: Path, status_path: Path) -> None:
    script_dir = Path(__file__).resolve().parent
    proc = subprocess.Popen(
        [
            sys.executable,
            str(script_dir / "convert_pdf_job.py"),
            "--docx", str(docx_path),
            "--pdf", str(pdf_path),
            "--status", str(status_path),
            "--timeout", "180",
            "--delete-docx",
        ],
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
        "projects": resume.get("projects", []),
        "certifications": resume.get("certifications", []),
        "experience_history": profile_experience_history_from_resume(resume),
    }


def current_profile() -> dict:
    base_profile = normalize_profile(profile_from_resume(load_base_resume()))
    permanent_doc = load_permanent_profile_doc()
    permanent = normalize_profile(merge_profile_docs(base_profile, permanent_doc)) if permanent_doc else base_profile
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

    normalized_history: list[dict] = []
    for blueprint in EXPERIENCE_BLUEPRINTS:
        raw_entry = next(
            (
                item for item in experience_history
                if isinstance(item, dict) and str(item.get("key", "")).strip() == blueprint["key"]
            ),
            {},
        )
        normalized_history.append(
            {
                "key": blueprint["key"],
                "company": str(raw_entry.get("company", "")).strip(),
                "location": str(raw_entry.get("location", "")).strip(),
                "title": str(raw_entry.get("title", "")).strip(),
                "dates": str(raw_entry.get("dates", "")).strip(),
                "enabled": bool(raw_entry.get("enabled", True)),
            }
        )

    return {
        "name": str(payload.get("name", "")).strip(),
        "contact": {
            "location": str(contact.get("location", "")).strip(),
            "phone": str(contact.get("phone", "")).strip(),
            "email": str(contact.get("email", "")).strip(),
        },
        "projects": normalized_projects,
        "certifications": [str(item).strip() for item in certifications if str(item).strip()],
        "experience_history": normalized_history,
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


clear_session_profile_doc()
migrate_legacy_profile_if_needed()


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


@app.route("/api/tracker", methods=["GET"])
def get_tracker():
    try:
        sort_key = str(request.args.get("sort", "applied_date")).strip()
        store = load_tracker_store()
        applications = sorted_tracker_applications(merge_tracker_applications(store), sort_key=sort_key)
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

        store = load_tracker_store()
        target_output_dir = str(data.get("output_dir", "")).strip()
        existing = None
        if target_output_dir:
            existing = next((item for item in store["applications"] if str(item.get("output_dir", "")).strip() == target_output_dir), None)
        if not existing and target_output_dir:
            existing = next((item for item in scan_output_tracker_applications() if str(item.get("output_dir", "")).strip() == target_output_dir), None)

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
        if existing:
            history = list(existing.get("history") or [])
            if not history:
                history = application.get("history", [])
            application["id"] = str(existing.get("id", application["id"]))
            application["created_at"] = str(existing.get("created_at", application["created_at"]))
            application["history"] = history
            application["status"] = normalize_tracker_status(data.get("status", existing.get("status", "Applied")))
            application["status_updated_date"] = applied_date if application["status"] != existing.get("status") else str(existing.get("status_updated_date", applied_date))
            application["last_updated_date"] = datetime.now().isoformat(timespec="seconds")
            application["notes"] = str(data.get("notes", "")).strip() or str(existing.get("notes", "")).strip()
            if application["status"] != existing.get("status"):
                application["history"] = history + [{
                    "status": application["status"],
                    "changed_at": application["last_updated_date"],
                    "effective_date": application["status_updated_date"],
                    "note": application["notes"],
                }]

            replaced = False
            for index, item in enumerate(store["applications"]):
                if str(item.get("id", "")) == application["id"] or str(item.get("output_dir", "")).strip() == target_output_dir:
                    store["applications"][index] = application
                    replaced = True
                    break
            if not replaced:
                store["applications"].append(application)
        else:
            store["applications"].append(application)
        save_tracker_store(store)
        merged_applications = merge_tracker_applications(store)
        response_application = next(
            (
                item for item in merged_applications
                if str(item.get("id", "")) == str(application.get("id", ""))
                or (target_output_dir and str(item.get("output_dir", "")).strip() == target_output_dir)
            ),
            application,
        )
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
        store = load_tracker_store()
        applications = store.get("applications", [])
        record = next((item for item in applications if item.get("id") == application_id), None)
        if not record:
            discovered = next((item for item in scan_output_tracker_applications() if item.get("id") == application_id), None)
            if not discovered:
                return jsonify({"success": False, "error": "Application not found"}), 404
            record = {**discovered}
            applications.append(record)

        now_iso = datetime.now().isoformat(timespec="seconds")
        record["status"] = new_status
        record["last_updated_date"] = now_iso
        record["status_updated_date"] = effective_date
        if note:
            record["notes"] = note
        history = record.get("history") or []
        history.append({
            "status": new_status,
            "changed_at": now_iso,
            "effective_date": effective_date,
            "note": note,
        })
        record["history"] = history
        save_tracker_store(store)
        merged_applications = merge_tracker_applications(store)
        updated_record = next((item for item in merged_applications if item.get("id") == application_id), record)
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
        enabled_experience_keys = normalize_enabled_experience_keys(data.get("enabled_experience_keys"))

        if not job_description:
            return jsonify({"success": False, "error": "Job description is required"}), 400

        if len(job_description) > 20000:
            return jsonify({"success": False, "error": "Job description is too long"}), 400

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY is not configured"}), 500

        session_id, session = get_ai_session(session_id, job_description, reset_memory)
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
        if not session_id or session_id not in ai_sessions:
            return jsonify({"success": False, "error": "An active JD session is required."}), 400

        session = ai_sessions[session_id]
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
        if not session_id or session_id not in ai_sessions:
            return jsonify({"success": False, "error": "An active JD session is required."}), 400

        session = ai_sessions[session_id]
        session["enabled_experience_keys"] = enabled_experience_keys
        analysis_payload = session.get("analysis")
        if not analysis_payload:
            raise AIStageError("analysis", "JD analysis is required before skills generation.")

        started = time.perf_counter()
        skills_payload = generate_skills_from_analysis(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            analysis_payload=analysis_payload,
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
        if not session_id or session_id not in ai_sessions:
            return jsonify({"success": False, "error": "An active JD session is required."}), 400

        session = ai_sessions[session_id]
        session["enabled_experience_keys"] = enabled_experience_keys
        analysis_payload = session.get("analysis")
        title_summary = session.get("title_summary")
        skills_payload = session.get("skills")
        if not analysis_payload:
            raise AIStageError("analysis", "JD analysis is required before core review.")
        if not title_summary or not skills_payload:
            raise AIStageError("core_generation", "Title, summary, and skills are required before core review.", analysis=analysis_payload)

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        order_key = str(analysis_payload.get("skill_category_order_key", "")).strip() or infer_skill_category_order_key(
            analysis_payload.get("role_family", "")
        )
        ordered_categories = skill_category_order_for_key(order_key)
        started = time.perf_counter()
        corrected_payload = refine_core_sections(
            api_key=api_key,
            analysis_payload=analysis_payload,
            title_summary_payload=title_summary,
            skills_payload=skills_payload,
        )
        timing = {"core_refinement_ms": int((time.perf_counter() - started) * 1000)}

        corrected_title_summary = {
            "updated_title": str(title_summary.get("updated_title", "")).strip(),
            "updated_summary": str(corrected_payload.get("updated_summary", "")).strip(),
        }
        corrected_skills = normalize_skills_for_order(
            {"updated_skills": corrected_payload.get("updated_skills", [])},
            ordered_categories,
        )

        summary_issues = validate_title_summary_payload(corrected_title_summary, analysis_payload, summary_max_buffer=10)
        skills_issues = validate_skills_only_payload(corrected_skills, analysis_payload)
        issues = summary_issues + skills_issues
        if issues:
            corrected_title_summary = title_summary
            corrected_skills = skills_payload
            revised = False
        else:
            revised = (
                corrected_title_summary.get("updated_summary", "").strip() != str(title_summary.get("updated_summary", "")).strip()
                or normalize_updated_skills(corrected_skills.get("updated_skills", []))
                != normalize_updated_skills(skills_payload.get("updated_skills", []))
            )

        session["title_summary"] = corrected_title_summary
        session["skills"] = corrected_skills
        session["core_resume"] = merge_core_sections(session["title_summary"], session["skills"])
        session["core_resume"]["_analysis"] = analysis_payload
        session["core_resume"]["_enabled_experience_keys"] = enabled_experience_keys
        session["updated_at"] = time.time()
        timing["total_ms"] = timing["core_refinement_ms"]

        response_content = format_core_resume_text(session["core_resume"])
        experience_payload = None
        title_warnings: list[str] = []
        if session.get("experience_recent") and session.get("experience_older"):
            experience_payload = {"experience": {}}
            experience_payload["experience"].update(session["experience_recent"].get("experience", {}))
            experience_payload["experience"].update(session["experience_older"].get("experience", {}))
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
        if not session_id or session_id not in ai_sessions:
            return jsonify({"success": False, "error": "An active JD session is required."}), 400

        session = ai_sessions[session_id]
        session["enabled_experience_keys"] = enabled_experience_keys
        analysis_payload = session.get("analysis")
        title_summary = session.get("title_summary")
        skills_payload = session.get("skills")
        if not analysis_payload:
            raise AIStageError("analysis", "JD analysis is required before experience generation.")
        if not title_summary or not skills_payload:
            raise AIStageError("core_generation", "Title, summary, and skills are required before experience generation.", analysis=analysis_payload)

        core_payload = merge_core_sections(title_summary, skills_payload)
        core_payload["_analysis"] = analysis_payload
        core_payload["_enabled_experience_keys"] = enabled_experience_keys
        all_blueprints = filter_blueprints_by_enabled_keys(current_experience_blueprints(), enabled_experience_keys)
        recent_keys = set(EXPERIENCE_BLUEPRINT_KEYS[:2])
        blueprints = [blueprint for blueprint in all_blueprints if (blueprint["key"] in recent_keys) == recent]
        model = RESUME_MODEL
        timeout_seconds = OPENAI_RESUME_TIMEOUT_SECONDS

        started = time.perf_counter()
        subset_payload = generate_experience_subset_from_analysis(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            analysis_payload=analysis_payload,
            core_payload=core_payload,
            blueprints=blueprints,
            model=model,
            timeout_seconds=timeout_seconds,
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
        session["core_resume"] = core_payload
        if session.get("experience_recent") and session.get("experience_older"):
            merged_experience = {"experience": {}}
            merged_experience["experience"].update(session["experience_recent"].get("experience", {}))
            merged_experience["experience"].update(session["experience_older"].get("experience", {}))
            merged_payload = merge_resume_payloads(core_payload, merged_experience)
            resume_text = format_generated_resume_text(merged_payload)
            title_warnings = collect_experience_title_warnings(merged_experience, analysis_payload)
            turn = {
                "revision_request": "",
                "analysis": analysis_payload,
                "resume_text": resume_text,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            session["turns"] = (session.get("turns", []) + [turn])[-AI_MEMORY_LIMIT:]
            session["updated_at"] = time.time()
            return jsonify({
                "success": True,
                "session_id": session_id,
                "content": resume_text,
                "experience": merged_experience,
                "title_warnings": title_warnings,
                "timing": timing,
                "complete": True,
            })

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


@app.route("/api/generate", methods=["POST"])
def generate():
    """Generate resume DOCX and start PDF conversion."""
    try:
        data = request.get_json()
        content = data.get("content", "").strip()
        resume_override = data.get("resume_override") if isinstance(data.get("resume_override"), dict) else None

        # Validate
        errors, warnings = validate_updated_content(content)
        if errors:
            return jsonify({
                "success": False,
                "error": f"Validation failed: {errors[0]}"
            }), 400

        # Parse content
        if resume_override:
            merged_resume = apply_enabled_experience_filter(dict(resume_override), data.get("enabled_experience_keys"))
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


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5001))
    app.run(debug=False, host="127.0.0.1", port=port, threaded=True)
