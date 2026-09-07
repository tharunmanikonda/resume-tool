"""Job discovery sources, ATS fetchers, dedupe, and lead persistence."""

from __future__ import annotations

import hashlib
import html
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import parse_qs, urlparse
import urllib.request

from sqlalchemy import func, or_, select

from cpt_checker import check_cpt_company
from database import JobLead, JobSource, ResumeDraft, session_scope, utcnow


SOURCE_TYPES = {"linkedin_search", "greenhouse", "lever", "ashby", "rippling"}
LEAD_STATUSES = {"new", "saved", "hidden", "draft_created", "applied", "stale", "closed"}
ACTIVE_LEAD_STATUSES = {"new", "saved", "draft_created"}
RELEVANCE_STATUSES = {"candidate", "filtered_out", "needs_review"}
DEFAULT_INCLUDE_KEYWORDS = (
    "software engineer", "backend", "full stack", "frontend", "python", "java",
    "react", "cloud", "data engineer", "ai engineer", "machine learning",
)
TITLE_INCLUDE_KEYWORDS = (
    "software engineer", "backend", "full stack", "frontend", "data engineer",
    "ai engineer", "machine learning engineer", "platform engineer", "devops",
    "site reliability", "sre", "infrastructure engineer",
)
DEFAULT_EXCLUDE_KEYWORDS = (
    "staff", "principal", "director", "manager", "clearance", "security clearance",
    "citizenship required", "u.s. citizen", "us citizen", "secret clearance",
)
PREFERRED_TERMS = ("full-time", "full time", "internship", "new grad", "entry-level", "entry level", "junior")


@dataclass(frozen=True)
class JobCandidate:
    source: str
    source_company_key: str
    external_job_id: str
    company_name: str
    role_title: str
    location: str
    job_url: str
    apply_url: str
    posted_at: datetime | None
    description: str
    raw_snapshot: dict


def clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def html_to_text(value) -> str:
    unescaped = html.unescape(str(value or ""))
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", unescaped)
    text = re.sub(r"(?i)</\s*(p|div|li|h[1-6]|tr)\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t\r\f\v]+", " ", text).replace("\n ", "\n").strip()


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def parse_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000
        return datetime.fromtimestamp(number, timezone.utc)
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        if text_value.endswith("Z"):
            text_value = f"{text_value[:-1]}+00:00"
        parsed = datetime.fromisoformat(text_value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def canonical_json_hash(values: Iterable) -> str:
    payload = json.dumps(list(values), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def identity_hash_for(candidate: JobCandidate) -> str:
    source = clean_text(candidate.source).lower()
    source_key = clean_text(candidate.source_company_key).lower()
    external_id = clean_text(candidate.external_job_id)
    if external_id:
        return canonical_json_hash([source, source_key, external_id])
    return canonical_json_hash([
        source,
        normalized_key(candidate.company_name),
        normalized_key(candidate.role_title),
        normalized_key(candidate.location),
        clean_text(candidate.job_url).rstrip("/").lower(),
    ])


def content_hash_for(candidate: JobCandidate) -> str:
    return canonical_json_hash([
        clean_text(candidate.role_title).lower(),
        clean_text(candidate.company_name).lower(),
        clean_text(candidate.location).lower(),
        clean_text(candidate.job_url).rstrip("/"),
        clean_text(candidate.apply_url).rstrip("/"),
        candidate.posted_at.isoformat() if candidate.posted_at else "",
        clean_text(candidate.description),
    ])


def classify_relevance(candidate: JobCandidate) -> tuple[str, str]:
    title = candidate.role_title.lower()
    haystack = " ".join((
        candidate.role_title,
        candidate.company_name,
        candidate.location,
        candidate.description[:4000],
        json.dumps(candidate.raw_snapshot, ensure_ascii=True)[:4000],
    )).lower()
    for keyword in DEFAULT_EXCLUDE_KEYWORDS:
        if keyword in haystack:
            return "filtered_out", f"Excluded by keyword: {keyword}"
    title_match = next((keyword for keyword in TITLE_INCLUDE_KEYWORDS if keyword in title), "")
    if title_match:
        preferred = next((term for term in PREFERRED_TERMS if term in haystack), "")
        return "candidate", f"Title matched: {title_match}{f' · {preferred}' if preferred else ''}."
    if any(keyword in haystack for keyword in DEFAULT_INCLUDE_KEYWORDS):
        return "needs_review", "Description matched a target keyword, but title needs review."
    return "needs_review", "No target role keyword matched."


def source_url_for(source_type: str, source_key: str, url: str = "") -> str:
    if url:
        return url
    key = clean_text(source_key)
    if source_type == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{key}/jobs?content=true"
    if source_type == "lever":
        return f"https://api.lever.co/v0/postings/{key}?mode=json"
    if source_type == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{key}?includeCompensation=true"
    if source_type == "rippling":
        return f"https://api.rippling.com/platform/api/ats/v1/board/{key}/jobs"
    return url


def fetch_json(url: str, timeout: int = 20):
    request = urllib.request.Request(url, headers={"User-Agent": "resume-tool-job-discovery/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def greenhouse_candidates(source: dict) -> list[JobCandidate]:
    key = source["source_key"]
    payload = fetch_json(source_url_for("greenhouse", key, source.get("url", "")))
    jobs = payload.get("jobs") if isinstance(payload, dict) else payload
    candidates = []
    for job in jobs or []:
        job_id = clean_text(job.get("id"))
        title = clean_text(job.get("title"))
        company = clean_text(job.get("company_name") or source.get("company_name") or source.get("name"))
        location = clean_text((job.get("location") or {}).get("name") if isinstance(job.get("location"), dict) else job.get("location"))
        url = clean_text(job.get("absolute_url"))
        candidates.append(JobCandidate(
            source="greenhouse",
            source_company_key=key,
            external_job_id=job_id,
            company_name=company,
            role_title=title,
            location=location,
            job_url=url,
            apply_url=url,
            posted_at=parse_datetime(job.get("first_published") or job.get("updated_at")),
            description=html_to_text(job.get("content")),
            raw_snapshot=job,
        ))
    return candidates


def lever_candidates(source: dict) -> list[JobCandidate]:
    key = source["source_key"]
    payload = fetch_json(source_url_for("lever", key, source.get("url", "")))
    jobs = payload.get("postings") if isinstance(payload, dict) else payload
    candidates = []
    for job in jobs or []:
        categories = job.get("categories") if isinstance(job.get("categories"), dict) else {}
        candidates.append(JobCandidate(
            source="lever",
            source_company_key=key,
            external_job_id=clean_text(job.get("id")),
            company_name=clean_text(source.get("company_name") or source.get("name")),
            role_title=clean_text(job.get("text")),
            location=clean_text(categories.get("location")),
            job_url=clean_text(job.get("hostedUrl")),
            apply_url=clean_text(job.get("applyUrl") or job.get("hostedUrl")),
            posted_at=parse_datetime(job.get("createdAt")),
            description=clean_text(job.get("descriptionPlain")) or html_to_text(job.get("description")),
            raw_snapshot=job,
        ))
    return candidates


def ashby_candidates(source: dict) -> list[JobCandidate]:
    key = source["source_key"]
    payload = fetch_json(source_url_for("ashby", key, source.get("url", "")))
    jobs = payload.get("jobs") if isinstance(payload, dict) else payload
    candidates = []
    for job in jobs or []:
        location = job.get("location")
        if isinstance(location, dict):
            location = location.get("name") or location.get("city")
        candidates.append(JobCandidate(
            source="ashby",
            source_company_key=key,
            external_job_id=clean_text(job.get("id")),
            company_name=clean_text(source.get("company_name") or source.get("name")),
            role_title=clean_text(job.get("title")),
            location=clean_text(location),
            job_url=clean_text(job.get("jobUrl")),
            apply_url=clean_text(job.get("applyUrl") or job.get("jobUrl")),
            posted_at=parse_datetime(job.get("publishedAt")),
            description=clean_text(job.get("descriptionPlain")) or html_to_text(job.get("descriptionHtml")),
            raw_snapshot=job,
        ))
    return candidates


def rippling_candidates(source: dict) -> list[JobCandidate]:
    key = source["source_key"]
    payload = fetch_json(source_url_for("rippling", key, source.get("url", "")))
    jobs = payload.get("jobs") if isinstance(payload, dict) else payload
    candidates = []
    for job in jobs or []:
        department = job.get("department") if isinstance(job.get("department"), dict) else {}
        work_location = job.get("workLocation") if isinstance(job.get("workLocation"), dict) else {}
        url = clean_text(job.get("url") or f"https://ats.rippling.com/{key}/jobs/{clean_text(job.get('uuid'))}")
        title = clean_text(job.get("name") or job.get("title"))
        candidates.append(JobCandidate(
            source="rippling",
            source_company_key=key,
            external_job_id=clean_text(job.get("uuid") or job.get("id")),
            company_name=clean_text(source.get("company_name") or source.get("name")),
            role_title=title,
            location=clean_text(work_location.get("label") or job.get("location")),
            job_url=url,
            apply_url=url,
            posted_at=parse_datetime(job.get("createdAt") or job.get("publishedAt")),
            description=clean_text(job.get("description") or department.get("label")),
            raw_snapshot=job,
        ))
    return candidates


def linkedin_candidates(_source: dict) -> list[JobCandidate]:
    return []


FETCHERS = {
    "greenhouse": greenhouse_candidates,
    "lever": lever_candidates,
    "ashby": ashby_candidates,
    "rippling": rippling_candidates,
    "linkedin_search": linkedin_candidates,
}


def serialize_source(row: JobSource) -> dict:
    return {
        "id": row.id,
        "source_type": row.source_type,
        "name": row.name,
        "company_name": row.company_name or "",
        "source_key": row.source_key,
        "url": row.url or "",
        "enabled": bool(row.enabled),
        "scan_frequency": row.scan_frequency or "daily",
        "last_scan_started_at": row.last_scan_started_at.isoformat() if row.last_scan_started_at else "",
        "last_scan_finished_at": row.last_scan_finished_at.isoformat() if row.last_scan_finished_at else "",
        "last_scan_status": row.last_scan_status or "",
        "last_scan_error": row.last_scan_error or "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def serialize_lead(row: JobLead, *, include_description: bool = False) -> dict:
    payload = {
        "id": row.id,
        "source": row.source,
        "source_company_key": row.source_company_key,
        "external_job_id": row.external_job_id or "",
        "identity_hash": row.identity_hash,
        "content_hash": row.content_hash,
        "company_name": row.company_name,
        "role_title": row.role_title,
        "location": row.location or "",
        "job_url": row.job_url or "",
        "apply_url": row.apply_url or "",
        "posted_at": row.posted_at.isoformat() if row.posted_at else "",
        "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else "",
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else "",
        "last_changed_at": row.last_changed_at.isoformat() if row.last_changed_at else "",
        "missing_seen_count": int(row.missing_seen_count or 0),
        "status": row.status,
        "relevance_status": row.relevance_status,
        "relevance_reason": row.relevance_reason or "",
        "cpt_status": row.cpt_status or "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }
    if include_description:
        payload["job_description"] = html_to_text(row.job_description or "")
        payload["raw_snapshot"] = row.raw_snapshot or {}
    return payload


def normalize_source_payload(payload: dict, existing: JobSource | None = None) -> dict:
    source_type = clean_text(payload.get("source_type") or payload.get("type") or (existing.source_type if existing else "")).lower()
    if source_type not in SOURCE_TYPES:
        raise ValueError("Unsupported job source type.")
    url = clean_text(payload.get("url") if "url" in payload else (existing.url if existing else ""))
    source_key = clean_text(payload.get("source_key") if "source_key" in payload else (existing.source_key if existing else ""))
    if not source_key and source_type == "linkedin_search" and url:
        parsed = urlparse(url)
        source_key = clean_text(parse_qs(parsed.query).get("keywords", [""])[0]) or parsed.netloc + parsed.path
    if not source_key:
        raise ValueError("Source key is required.")
    name = clean_text(payload.get("name") if "name" in payload else (existing.name if existing else ""))
    if not name:
        name = clean_text(payload.get("company_name") or source_key)
    return {
        "source_type": source_type,
        "name": name,
        "company_name": clean_text(payload.get("company_name") if "company_name" in payload else (existing.company_name if existing else "")),
        "source_key": source_key,
        "url": url,
        "enabled": bool(payload.get("enabled")) if "enabled" in payload else (existing.enabled if existing else True),
        "scan_frequency": clean_text(payload.get("scan_frequency") if "scan_frequency" in payload else (existing.scan_frequency if existing else "daily")) or "daily",
    }


def create_source(payload: dict) -> dict:
    values = normalize_source_payload(payload)
    with session_scope() as db:
        row = JobSource(id="source-" + uuid.uuid4().hex, **values)
        db.add(row)
        db.flush()
        return serialize_source(row)


def list_sources() -> list[dict]:
    with session_scope() as db:
        rows = db.scalars(select(JobSource).order_by(JobSource.enabled.desc(), JobSource.updated_at.desc())).all()
        return [serialize_source(row) for row in rows]


def update_source(source_id: str, payload: dict) -> dict:
    with session_scope() as db:
        row = db.get(JobSource, source_id)
        if not row:
            raise KeyError("Job source not found.")
        values = normalize_source_payload(payload, row)
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = utcnow()
        db.flush()
        return serialize_source(row)


def _upsert_candidate(db, candidate: JobCandidate, now: datetime, cpt_status: str = "") -> tuple[str, str | None]:
    identity_hash = identity_hash_for(candidate)
    content_hash = content_hash_for(candidate)
    relevance_status, relevance_reason = classify_relevance(candidate)
    row = db.scalars(select(JobLead).where(JobLead.identity_hash == identity_hash)).first()
    if row:
        changed = row.content_hash != content_hash
        if changed:
            row.content_hash = content_hash
            row.last_changed_at = now
            row.company_name = candidate.company_name or row.company_name
            row.role_title = candidate.role_title or row.role_title
            row.location = candidate.location or row.location
            row.job_url = candidate.job_url or row.job_url
            row.apply_url = candidate.apply_url or row.apply_url
            row.job_description = candidate.description or row.job_description
            row.raw_snapshot = candidate.raw_snapshot or row.raw_snapshot
            if candidate.posted_at:
                row.posted_at = candidate.posted_at
        row.last_seen_at = now
        row.missing_seen_count = 0
        row.relevance_status = relevance_status
        row.relevance_reason = relevance_reason
        row.cpt_status = cpt_status or row.cpt_status
        if row.status in {"stale", "closed"}:
            row.status = "new"
        row.updated_at = now
        return ("updated" if changed else "unchanged"), row.id

    status = "new"
    row = JobLead(
        id="lead-" + uuid.uuid4().hex,
        source=candidate.source,
        source_company_key=candidate.source_company_key,
        external_job_id=candidate.external_job_id,
        identity_hash=identity_hash,
        content_hash=content_hash,
        company_name=candidate.company_name,
        role_title=candidate.role_title,
        location=candidate.location,
        job_url=candidate.job_url,
        apply_url=candidate.apply_url,
        job_description=candidate.description,
        posted_at=candidate.posted_at,
        first_seen_at=now,
        last_seen_at=now,
        last_changed_at=now,
        missing_seen_count=0,
        status=status,
        relevance_status=relevance_status,
        relevance_reason=relevance_reason,
        cpt_status=cpt_status,
        raw_snapshot=candidate.raw_snapshot,
    )
    db.add(row)
    return ("filtered_out" if relevance_status == "filtered_out" else "new"), row.id


def _mark_missing_jobs(db, source: JobSource, seen_hashes: set[str], now: datetime) -> None:
    if source.source_type == "linkedin_search":
        return
    rows = db.scalars(select(JobLead).where(
        JobLead.source == source.source_type,
        JobLead.source_company_key == source.source_key,
        JobLead.status.in_(tuple(ACTIVE_LEAD_STATUSES | {"stale"})),
    )).all()
    for row in rows:
        if row.identity_hash in seen_hashes:
            continue
        row.missing_seen_count = int(row.missing_seen_count or 0) + 1
        if row.missing_seen_count >= 10:
            row.status = "closed"
        elif row.missing_seen_count >= 3:
            row.status = "stale"
        row.updated_at = now


def scan_source(source_id: str) -> dict:
    now = utcnow()
    with session_scope() as db:
        source = db.get(JobSource, source_id)
        if not source:
            raise KeyError("Job source not found.")
        source.last_scan_started_at = now
        source.last_scan_status = "running"
        source.last_scan_error = ""
        db.flush()
        source_payload = serialize_source(source)

    result = {"source_id": source_id, "fetched": 0, "new": 0, "updated": 0, "unchanged": 0, "filtered_out": 0, "errors": 0}
    try:
        candidates = FETCHERS[source_payload["source_type"]](source_payload)
        result["fetched"] = len(candidates)
        enriched = [
            (candidate, (check_cpt_company(candidate.company_name).get("status") if candidate.company_name else "unavailable") or "unavailable")
            for candidate in candidates
        ]
        seen_hashes: set[str] = set()
        with session_scope() as db:
            source = db.get(JobSource, source_id)
            for candidate, cpt_status in enriched:
                if not candidate.external_job_id and not candidate.job_url:
                    continue
                identity_hash = identity_hash_for(candidate)
                seen_hashes.add(identity_hash)
                bucket, _lead_id = _upsert_candidate(db, candidate, now, cpt_status)
                result[bucket] = result.get(bucket, 0) + 1
            _mark_missing_jobs(db, source, seen_hashes, now)
            source.last_scan_finished_at = utcnow()
            source.last_scan_status = "success"
            source.last_scan_error = ""
            source.updated_at = utcnow()
            db.flush()
        return result
    except Exception as exc:
        with session_scope() as db:
            source = db.get(JobSource, source_id)
            if source:
                source.last_scan_finished_at = utcnow()
                source.last_scan_status = "failed"
                source.last_scan_error = str(exc)
                source.updated_at = utcnow()
        result["errors"] = 1
        result["error"] = str(exc)
        return result


def scan_all_enabled_sources() -> dict:
    with session_scope() as db:
        source_ids = list(db.scalars(select(JobSource.id).where(JobSource.enabled.is_(True))).all())
    results = [scan_source(source_id) for source_id in source_ids]
    totals = {"sources": len(source_ids), "fetched": 0, "new": 0, "updated": 0, "unchanged": 0, "filtered_out": 0, "errors": 0}
    for result in results:
        for key in ("fetched", "new", "updated", "unchanged", "filtered_out", "errors"):
            totals[key] += int(result.get(key, 0))
    return {"totals": totals, "results": results}


def list_leads(filters: dict) -> dict:
    limit = max(1, min(int(filters.get("limit") or 50), 100))
    offset = max(0, int(filters.get("offset") or 0))
    with session_scope() as db:
        statement = select(JobLead)
        if clean_text(filters.get("status")):
            statement = statement.where(JobLead.status == clean_text(filters["status"]))
        if clean_text(filters.get("source")):
            statement = statement.where(JobLead.source == clean_text(filters["source"]))
        if clean_text(filters.get("cpt_status")):
            statement = statement.where(JobLead.cpt_status == clean_text(filters["cpt_status"]))
        if clean_text(filters.get("relevance_status")):
            statement = statement.where(JobLead.relevance_status == clean_text(filters["relevance_status"]))
        if str(filters.get("fresh", "")).lower() in {"1", "true", "yes"}:
            statement = statement.where(
                JobLead.status.in_(("new", "saved")),
                JobLead.relevance_status == "candidate",
            )
        query = clean_text(filters.get("q")).lower()
        if query:
            like = f"%{query}%"
            statement = statement.where(or_(
                func.lower(JobLead.company_name).like(like),
                func.lower(JobLead.role_title).like(like),
                func.lower(JobLead.location).like(like),
            ))
        location = clean_text(filters.get("location")).lower()
        if location:
            statement = statement.where(func.lower(JobLead.location).like(f"%{location}%"))
        total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = db.scalars(
            statement.order_by(
                JobLead.posted_at.desc().nullslast(),
                JobLead.first_seen_at.desc(),
            ).limit(limit).offset(offset)
        ).all()
        return {
            "leads": [serialize_lead(row) for row in rows],
            "total": int(total),
            "limit": limit,
            "offset": offset,
        }


def get_lead(lead_id: str) -> dict | None:
    with session_scope() as db:
        row = db.get(JobLead, lead_id)
        return serialize_lead(row, include_description=True) if row else None


def update_lead(lead_id: str, payload: dict) -> dict:
    allowed_statuses = LEAD_STATUSES
    with session_scope() as db:
        row = db.get(JobLead, lead_id)
        if not row:
            raise KeyError("Job lead not found.")
        if "status" in payload:
            status = clean_text(payload.get("status")).lower()
            if status not in allowed_statuses:
                raise ValueError("Unsupported job lead status.")
            row.status = status
        if "relevance_status" in payload:
            relevance = clean_text(payload.get("relevance_status")).lower()
            if relevance not in RELEVANCE_STATUSES:
                raise ValueError("Unsupported relevance status.")
            row.relevance_status = relevance
        if "relevance_reason" in payload:
            row.relevance_reason = clean_text(payload.get("relevance_reason"))
        row.updated_at = utcnow()
        db.flush()
        return serialize_lead(row, include_description=True)


def mark_lead_applied_from_draft(draft: dict) -> None:
    lead_id = clean_text(draft.get("job_lead_id") or (draft.get("source_metadata") or {}).get("job_lead_id"))
    if not lead_id:
        return
    with session_scope() as db:
        row = db.get(JobLead, lead_id)
        if row:
            row.status = "applied"
            row.updated_at = utcnow()


def promote_lead_to_draft_payload(lead_id: str) -> dict:
    lead = get_lead(lead_id)
    if not lead:
        raise KeyError("Job lead not found.")
    if len(clean_text(lead.get("job_description"))) < 120:
        raise ValueError("This job lead does not have enough description text to generate a resume.")
    return {
        "source": lead["source"],
        "external_job_id": lead["external_job_id"],
        "url": lead["job_url"],
        "company_name": lead["company_name"],
        "role_title": lead["role_title"],
        "location": lead["location"],
        "job_description": lead["job_description"],
        "source_metadata": {
            "job_lead_id": lead_id,
            "discovery_source": lead["source"],
            "identity_hash": lead["identity_hash"],
        },
    }


def attach_lead_to_draft(draft_id: str, lead_id: str) -> None:
    with session_scope() as db:
        draft = db.get(ResumeDraft, draft_id)
        lead = db.get(JobLead, lead_id)
        if draft:
            draft.job_lead_id = lead_id
            draft.source_metadata = {**(draft.source_metadata or {}), "job_lead_id": lead_id}
            draft.updated_at = utcnow()
        if lead:
            lead.status = "draft_created"
            lead.updated_at = utcnow()
