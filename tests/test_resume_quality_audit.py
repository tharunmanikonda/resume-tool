import copy

import pytest

import app as resume_app


ANALYSIS = {
    "target_role": "Backend Engineer",
    "role_family": "backend application engineering",
    "skill_category_order_key": "backend_application",
    "prompt_family_key": "software_engineering",
    "core_problem": "Build reliable backend services",
    "top_requirements": ["Python", "FastAPI", "PostgreSQL"],
    "skills_mentioned": ["Python", "FastAPI", "PostgreSQL", "AWS", "Docker"],
    "domain_terms": [],
}

SUMMARY = (
    "Backend engineer with experience building reliable APIs and practical data workflows across "
    "enterprise and product environments. Delivered Python services, PostgreSQL integrations, cloud "
    "deployments, and observability improvements that made systems easier to operate. Work spans "
    "customer-facing delivery and internal platforms, with a focus on measurable outcomes, clear "
    "technical decisions, and dependable execution. Brings strong system design, testing, and "
    "collaboration skills to complex software problems without overstating domain experience. "
    "Communicates tradeoffs clearly and works closely with product and operations teams."
)

REWRITTEN_BULLET = (
    "Built FastAPI services and PostgreSQL integrations that improved workflow reliability by 20% "
    "while giving enterprise delivery teams clearer deployment checks and dependable operational support."
)


def active_blueprints():
    blueprint = copy.deepcopy(resume_app.EXPERIENCE_BLUEPRINTS[0])
    blueprint.update({
        "bullet_min": 2,
        "bullet_max": 3,
        "anchor": "Python, FastAPI, PostgreSQL, APIs, deployment checks",
        "metric_evidence": "Improved workflow reliability by 20%.",
    })
    return [blueprint]


def current_resume():
    role_key = active_blueprints()[0]["key"]
    return {
        "updated_title": "Backend Software Engineer",
        "updated_summary": SUMMARY,
        "updated_skills": [
            {"category": "Programming Languages", "items": ["Python", "Java"]},
            {"category": "Backend Engineering", "items": ["FastAPI", "RESTful APIs"]},
            {"category": "Data & Storage", "items": ["PostgreSQL", "SQL"]},
            {"category": "Cloud & Infrastructure", "items": ["AWS", "Docker"]},
            {"category": "Testing & Quality", "items": ["Integration Testing", "Unit Testing"]},
            {"category": "DevOps & CI/CD", "items": ["CI/CD", "GitHub Actions"]},
        ],
        "experience": {
            role_key: {
                "title": "Software Engineer",
                "bullets": [
                    (
                        "Built FastAPI services that improved workflow reliability by 20% across "
                        "enterprise delivery teams while strengthening deployment checks and operational support."
                    ),
                    (
                        "Delivered PostgreSQL integrations with Python automation for dependable "
                        "customer-facing systems, clearer data flows, and more consistent release validation."
                    ),
                ],
            }
        },
    }


def scores():
    return {
        "ats_alignment": 90,
        "technical_credibility": 92,
        "human_tone": 88,
        "evidence_quality": 93,
        "career_coherence": 91,
    }


def empty_changes():
    return resume_app._empty_resume_quality_audit_changes()


def audit_result(decision="approved", changes=None):
    resolved_changes = copy.deepcopy(
        changes if changes is not None else empty_changes()
    )
    return {
        "schema_version": "2",
        "decision": decision,
        "overall_score": 91,
        "review_summary": "The resume is credible, focused, and easy to scan.",
        "review_basis": {
            "advertised_job_title": "Backend Engineer",
            "normalized_market_title": "Backend Engineer",
            "top_title_assessment": (
                "change_recommended"
                if isinstance(resolved_changes.get("top_title"), dict)
                else "aligned"
            ),
            "experience_title_assessment": (
                "change_recommended"
                if resolved_changes.get("experience_titles")
                else "coherent"
            ),
            "title_rationale": "The titles were checked against the posted role and career evidence.",
            "technical_recruiter_priorities": ["Recognizable backend title"],
            "hiring_manager_priorities": ["Reliable API delivery"],
            "principal_engineer_priorities": ["Credible system ownership"],
        },
        "component_scores": scores(),
        "manual_findings": [],
        "non_blocking_gaps": [],
        "changes": resolved_changes,
    }


def title_change():
    changes = empty_changes()
    changes["top_title"] = {
        "change_id": "title.market-standard",
        "suggested": "Backend Engineer",
        "reason": "Use the common market title used by the target role.",
        "supported_by": ["technical_recruiter", "hiring_manager"],
        "evidence_refs": ["upstream.mckinsey.title"],
    }
    return changes


def bullet_change(*, change_id="experience.mckinsey.rewrite-1", bullet=REWRITTEN_BULLET):
    blueprint = active_blueprints()[0]
    changes = empty_changes()
    changes["experience"] = [{
        "role_key": blueprint["key"],
        "company": blueprint["company"],
        "current_bullet_count": 2,
        "proposed_bullet_count": 2,
        "reason": "Make the existing evidence more direct.",
        "change_groups": [{
            "change_id": change_id,
            "reason": "Combine the supported action and outcome into one clear bullet.",
            "supported_by": ["hiring_manager", "principal_engineer"],
            "removals": [{"bullet_number": 1}],
            "additions": [{
                "new_position": 1,
                "new_bullet": bullet,
                "replaces_bullet_numbers": [1],
                "evidence_refs": [
                    "upstream.mckinsey.bullet.1",
                    "profile.mckinsey.anchor",
                ],
            }],
        }],
    }]
    return changes


@pytest.fixture(autouse=True)
def isolate_resume_shape_validation(monkeypatch):
    monkeypatch.setattr(
        resume_app,
        "_quality_audit_resume_validation_issues",
        lambda *_args, **_kwargs: [],
    )


def validate(result):
    return resume_app.validate_resume_quality_audit_result(
        result,
        current_resume=current_resume(),
        analysis_payload=ANALYSIS,
        active_blueprints=active_blueprints(),
    )


def test_approved_review_has_no_changes():
    validated = validate(audit_result())

    assert validated["schema_version"] == "2"
    assert validated["decision"] == "approved"
    assert validated["review_groups"] == []
    assert validated["changes"] == empty_changes()


def test_title_patch_returns_stable_review_group():
    validated = validate(audit_result("changes_suggested", title_change()))

    assert validated["decision"] == "changes_suggested"
    assert validated["review_groups"] == [{
        "section": "top_title",
        "change_id": "title.market-standard",
        "suggested": "Backend Engineer",
        "reason": "Use the common market title used by the target role.",
        "supported_by": ["technical_recruiter", "hiring_manager"],
        "evidence_refs": ["upstream.mckinsey.title"],
        "current": "Backend Software Engineer",
        "proposed": "Backend Engineer",
    }]


def test_duplicate_model_change_ids_are_normalized_with_requirement_links():
    changes = title_change()
    changes["summary"] = {
        "change_id": "title.market-standard",
        "suggested": SUMMARY,
        "reason": "Keep the summary focused on supported backend evidence.",
        "supported_by": ["technical_recruiter", "hiring_manager"],
        "evidence_refs": ["upstream.summary"],
    }
    result = audit_result("changes_suggested", changes)
    result["requirement_resolutions"] = [{
        "requirement_id": "req.backend-positioning",
        "requirement": "Use direct backend positioning",
        "priority": "important",
        "claim_type": "engineering_capability",
        "evidence_fit": "direct",
        "resume_action": "patch_required",
        "status": "patched_direct",
        "evidence_refs": ["upstream.summary"],
        "change_ids": ["title.market-standard"],
        "reason": "Both patches express the supported backend positioning.",
    }]

    normalized = resume_app._normalize_quality_audit_change_ids(result)

    assert result["changes"]["summary"]["change_id"] == "title.market-standard"
    assert normalized["changes"]["top_title"]["change_id"] == "title.market-standard"
    assert normalized["changes"]["summary"]["change_id"] == "title.market-standard-2"
    assert normalized["requirement_resolutions"][0]["change_ids"] == [
        "title.market-standard",
        "title.market-standard-2",
    ]

    validated = validate(result)
    validated_ids = {
        group["change_id"] for group in validated["review_groups"]
    } | {
        item["change_id"] for item in validated["withheld_changes"]
    }
    assert "title.market-standard" in validated_ids
    assert "title.market-standard-2" in validated_ids


def test_atomic_bullet_rewrite_removes_and_inserts_as_one_change():
    result = audit_result("changes_suggested", bullet_change())
    validated = validate(result)
    resolved, decided_ids, all_rejected = resume_app.resolve_resume_quality_audit_decisions(
        expected_base_hash=validated["base_hash"],
        current_resume=current_resume(),
        audit_result=validated,
        decisions={"experience.mckinsey.rewrite-1": "accept"},
        analysis_payload=ANALYSIS,
        active_blueprints=active_blueprints(),
    )

    role_key = active_blueprints()[0]["key"]
    assert decided_ids == ["experience.mckinsey.rewrite-1"]
    assert all_rejected is False
    assert resolved["experience"][role_key]["bullets"][0] == REWRITTEN_BULLET
    assert len(resolved["experience"][role_key]["bullets"]) == 2


def test_rejecting_every_patch_preserves_current_resume():
    validated = validate(audit_result("changes_suggested", title_change()))
    resolved, decided_ids, all_rejected = resume_app.resolve_resume_quality_audit_decisions(
        expected_base_hash=validated["base_hash"],
        current_resume=current_resume(),
        audit_result=validated,
        decisions={"title.market-standard": "reject"},
        analysis_payload=ANALYSIS,
        active_blueprints=active_blueprints(),
    )

    assert decided_ids == ["title.market-standard"]
    assert all_rejected is True
    assert resolved == current_resume()


def test_unsupported_patch_is_withheld_without_discarding_valid_patch():
    changes = title_change()
    unsafe = bullet_change(
        change_id="experience.mckinsey.unsupported",
        bullet=(
            "Built Kubernetes services that improved workflow reliability by 55% across enterprise "
            "delivery teams while strengthening release automation and operational support."
        ),
    )
    changes["experience"] = unsafe["experience"]

    validated = validate(audit_result("changes_suggested", changes))

    assert validated["decision"] == "changes_suggested"
    assert [group["change_id"] for group in validated["review_groups"]] == [
        "title.market-standard"
    ]
    assert validated["withheld_changes"] == [{
        "change_id": "experience.mckinsey.unsupported",
        "section": "experience",
        "reason": "Unsupported numeric claims: 55%.",
    }]


def test_all_unsupported_patches_become_non_blocking_gaps():
    validated = validate(audit_result(
        "changes_suggested",
        bullet_change(
            bullet=(
                "Built Kubernetes services that improved workflow reliability by 55% across enterprise "
                "delivery teams while strengthening release automation and operational support."
            ),
        ),
    ))

    assert validated["decision"] == "approved"
    assert validated["review_groups"] == []
    assert validated["manual_findings"] == []
    assert validated["non_blocking_gaps"][0]["id"].startswith("withheld.")


def test_required_patch_rejected_by_grounding_becomes_gap_without_repair():
    changes = bullet_change(
        bullet=(
            "Built Kubernetes services that improved workflow reliability by 55% across enterprise "
            "delivery teams while strengthening release automation and operational support."
        ),
    )
    result = audit_result("changes_suggested", changes)
    result["requirement_resolutions"] = [{
        "requirement_id": "req.kubernetes",
        "requirement": "Deploy backend services with Kubernetes",
        "priority": "important",
        "claim_type": "named_technology",
        "evidence_fit": "transferable",
        "resume_action": "patch_required",
        "status": "patched_transferable",
        "evidence_refs": ["upstream.mckinsey.bullet.1"],
        "change_ids": ["experience.mckinsey.rewrite-1"],
        "reason": "The proposed rewrite attempted to surface deployment evidence.",
    }]

    validated = validate(result)

    assert validated["decision"] == "approved"
    resolution = validated["requirement_resolutions"][0]
    assert resolution["resume_action"] == "gap_only"
    assert resolution["status"] == "unresolved"
    assert resolution["change_ids"] == []
    assert validated["requirement_resolution_diagnostics"][0]["issue"] == (
        "linked_patches_withheld"
    )


def test_project_evidence_can_resolve_requirement_with_safe_patch():
    changes = empty_changes()
    changes["skills"]["skill_additions"] = [{
        "change_id": "skills.backend.add-langchain",
        "category": "Backend Engineering",
        "skill": "LangChain",
        "reason": "Surface directly supplied project evidence relevant to the target role.",
        "supported_by": ["technical_recruiter", "principal_engineer"],
        "evidence_refs": ["profile.project.1.bullet.1"],
    }]
    result = audit_result("changes_suggested", changes)
    result["requirement_resolutions"] = [{
        "requirement_id": "req.llm-orchestration",
        "requirement": "Experience building LLM orchestration workflows",
        "priority": "important",
        "claim_type": "engineering_capability",
        "evidence_fit": "direct",
        "resume_action": "patch_required",
        "status": "patched_direct",
        "evidence_refs": ["profile.project.1.bullet.1"],
        "change_ids": ["skills.backend.add-langchain"],
        "reason": "The supplied project directly demonstrates LangChain orchestration.",
    }]

    validated = resume_app.validate_resume_quality_audit_result(
        result,
        current_resume=current_resume(),
        analysis_payload=ANALYSIS,
        active_blueprints=active_blueprints(),
        candidate_profile={
            "projects": [{
                "name": "Document Assistant",
                "bullets": [
                    "Built retrieval workflows with Python and LangChain for enterprise documents."
                ],
            }],
        },
    )

    assert validated["decision"] == "changes_suggested"
    assert validated["requirement_resolutions"][0]["status"] == "patched_direct"
    assert validated["requirement_resolutions"][0]["change_ids"] == [
        "skills.backend.add-langchain"
    ]


def test_genuinely_unsupported_requirement_becomes_non_blocking_gap():
    result = audit_result()
    result["requirement_resolutions"] = [{
        "requirement_id": "req.mobile-store",
        "requirement": "Published production applications to a mobile app store",
        "priority": "important",
        "claim_type": "engineering_capability",
        "evidence_fit": "none",
        "resume_action": "gap_only",
        "status": "unresolved",
        "evidence_refs": [],
        "change_ids": [],
        "reason": "No supplied role, project, certification, or validated claim proves publication.",
    }]

    validated = validate(result)

    assert validated["decision"] == "approved"
    assert validated["requirement_resolutions"][0]["status"] == "unresolved"
    assert validated["non_blocking_gaps"][-1]["id"] == "requirement.req.mobile-store"


def test_already_covered_requirement_does_not_fail_when_luna_links_patch():
    changes = title_change()
    result = audit_result("changes_suggested", changes)
    result["requirement_resolutions"] = [{
        "requirement_id": "R-010",
        "requirement": "Use a market-standard backend title",
        "priority": "important",
        "claim_type": "engineering_capability",
        "evidence_fit": "direct",
        "resume_action": "already_covered",
        "status": "already_covered",
        "evidence_refs": ["upstream.mckinsey.title"],
        "change_ids": ["title.market-standard"],
        "reason": "The requirement is covered, with an optional title refinement.",
    }]

    validated = validate(result)

    assert validated["decision"] == "changes_suggested"
    assert validated["requirement_resolutions"][0]["status"] == "already_covered"
    assert validated["requirement_resolutions"][0]["change_ids"] == []
    assert validated["changes"]["top_title"]["change_id"] == "title.market-standard"
    assert validated["requirement_resolution_diagnostics"] == [{
        "requirement_id": "R-010",
        "issue": "incompatible_change_ids_removed",
        "details": ["title.market-standard"],
    }]


def test_supported_engineering_requirement_cannot_remain_unpatched():
    result = audit_result()
    result["requirement_resolutions"] = [{
        "requirement_id": "req.implementation-docs",
        "requirement": "Create implementation guides and detailed test-result documentation",
        "priority": "important",
        "claim_type": "engineering_capability",
        "evidence_fit": "transferable",
        "resume_action": "gap_only",
        "status": "unresolved",
        "evidence_refs": ["upstream.mckinsey.bullet.2"],
        "change_ids": [],
        "reason": "The existing release-validation evidence can support a transferable rewrite.",
    }]

    with pytest.raises(
        resume_app.ResumeQualityAuditRepairRequiredError,
        match="requires a valid linked patch",
    ):
        validate(result)


def test_warehouse_and_travel_requirements_are_forced_to_gap_only():
    changes = title_change()
    result = audit_result("changes_suggested", changes)
    result["requirement_resolutions"] = [{
        "requirement_id": "req.warehouse-travel",
        "requirement": "Travel to warehouse sites for conveyor commissioning",
        "priority": "critical",
        "claim_type": "engineering_capability",
        "evidence_fit": "direct",
        "resume_action": "patch_required",
        "status": "patched_direct",
        "evidence_refs": ["upstream.mckinsey.title"],
        "change_ids": ["title.market-standard"],
        "reason": "The previous review incorrectly treated an application condition as resume evidence.",
    }]

    validated = validate(result)

    resolution = validated["requirement_resolutions"][0]
    assert resolution["claim_type"] == "domain_context"
    assert resolution["resume_action"] == "gap_only"
    assert resolution["status"] == "unresolved"
    assert resolution["change_ids"] == []
    assert validated["decision"] == "approved"
    assert validated["non_blocking_gaps"][-1]["kind"] == "domain_context"


def test_skill_removal_cannot_silently_collapse_category():
    changes = empty_changes()
    changes["skills"]["skill_removals"] = [{
        "change_id": "skills.languages.remove-java",
        "category": "Programming Languages",
        "skill": "Java",
        "reason": "Reduce less relevant language coverage.",
        "supported_by": ["technical_recruiter"],
    }]

    validated = validate(audit_result("changes_suggested", changes))

    assert validated["decision"] == "approved"
    assert validated["changes"] == empty_changes()
    assert validated["withheld_changes"] == [{
        "change_id": "skills.languages.remove-java",
        "section": "skills.skill_removals",
        "reason": (
            "Removing this item would leave 'Programming Languages' with fewer "
            "than two supported skills. The category was preserved."
        ),
    }]


def test_invalid_bullet_position_is_withheld_instead_of_clamped():
    changes = bullet_change()
    changes["experience"][0]["change_groups"][0]["additions"][0]["new_position"] = 9

    validated = validate(audit_result("changes_suggested", changes))

    assert validated["decision"] == "approved"
    assert validated["withheld_changes"][0]["reason"] == (
        "An added bullet has an invalid final position."
    )


def test_stale_base_hash_cannot_apply_changes():
    validated = validate(audit_result("changes_suggested", title_change()))
    edited = current_resume()
    edited["updated_title"] = "Senior Backend Engineer"

    with pytest.raises(resume_app.ResumeQualityAuditStaleConflictError):
        resume_app.resolve_resume_quality_audit_decisions(
            expected_base_hash=validated["base_hash"],
            current_resume=edited,
            audit_result=validated,
            decisions={"title.market-standard": "accept"},
            analysis_payload=ANALYSIS,
            active_blueprints=active_blueprints(),
        )


def test_schema_is_patch_only_and_never_contains_full_resume():
    schema_text = str(resume_app.ai_resume_quality_audit_schema(active_blueprints()))

    assert "proposed_resume" not in schema_text
    assert "updated_summary" not in schema_text
    assert "changes_suggested" in schema_text
    assert "change_id" in schema_text
    assert "review_basis" in schema_text
    assert "supported_by" in schema_text
    assert "non_blocking_gaps" in schema_text
    assert "claim_type" in schema_text
    assert "evidence_fit" in schema_text
    assert "resume_action" in schema_text


def test_title_assessment_requires_matching_title_patch():
    result = audit_result()
    result["review_basis"]["top_title_assessment"] = "change_recommended"

    with pytest.raises(
        resume_app.ResumeQualityAuditValidationError,
        match="top-title change requires",
    ):
        validate(result)


def test_summary_can_retain_named_technology_from_validated_manifest():
    changes = empty_changes()
    changes["summary"] = {
        "change_id": "summary.retain-postgresql",
        "suggested": SUMMARY,
        "reason": "Keep the supported database evidence visible.",
        "supported_by": ["technical_recruiter", "principal_engineer"],
        "evidence_refs": ["upstream.mckinsey.title"],
    }

    validated = validate(audit_result("changes_suggested", changes))

    assert validated["decision"] == "changes_suggested"
    assert validated["withheld_changes"] == []


def test_generation_uses_luna_medium_and_retries_for_output_limit(monkeypatch):
    calls = []
    approved = audit_result()

    def fake_call(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError(
                "OpenAI API returned no final output "
                "(status=incomplete, details={'reason':'max_output_tokens'})"
            )
        return copy.deepcopy(approved)

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    generated = resume_app.generate_resume_quality_audit(
        api_key="test-key",
        job_description="Build reliable Python APIs.",
        analysis_payload=ANALYSIS,
        current_resume=current_resume(),
        active_blueprints=active_blueprints(),
        advertised_job_title="Senior Backend Engineer",
        user_edit_context={"has_manual_edits": True, "edited_paths": ["summary"]},
    )

    assert [call["max_output_tokens"] for call in calls] == [8000, 12000]
    assert all(call["model"] == "gpt-5.6-luna" for call in calls)
    assert all(call["reasoning_effort"] == "medium" for call in calls)
    assert all(call["background"] is True for call in calls)
    assert all(
        call["background_timeout_seconds"]
        == resume_app.OPENAI_AUDIT_BACKGROUND_TIMEOUT_SECONDS
        for call in calls
    )
    assert generated["attempt_count"] == 2
    assert generated["decision"] == "approved"
    assert generated["execution_mode"] == "background"
    assert generated["review_basis"]["advertised_job_title"] == "Senior Backend Engineer"
    structured_input = calls[-1]["user_prompt"]
    assert '"advertised_title":"Senior Backend Engineer"' in structured_input
    assert '"advertised_title_is_authoritative":true' in structured_input
    assert '"has_manual_edits":true' in structured_input


def test_generation_repairs_missing_supported_engineering_patch_once(monkeypatch):
    calls = []
    incomplete = audit_result()
    incomplete["requirement_resolutions"] = [{
        "requirement_id": "req.implementation-docs",
        "requirement": "Create implementation guides and detailed test-result documentation",
        "priority": "important",
        "claim_type": "engineering_capability",
        "evidence_fit": "transferable",
        "resume_action": "gap_only",
        "status": "unresolved",
        "evidence_refs": ["upstream.mckinsey.bullet.2"],
        "change_ids": [],
        "reason": "Transferable release-validation evidence exists.",
    }]
    repaired = audit_result("changes_suggested", bullet_change())
    repaired["requirement_resolutions"] = [{
        "requirement_id": "req.implementation-docs",
        "requirement": "Create implementation guides and detailed test-result documentation",
        "priority": "important",
        "claim_type": "engineering_capability",
        "evidence_fit": "transferable",
        "resume_action": "patch_required",
        "status": "patched_transferable",
        "evidence_refs": ["upstream.mckinsey.bullet.2"],
        "change_ids": ["experience.mckinsey.rewrite-1"],
        "reason": "The replacement surfaces supported release-validation documentation evidence.",
    }]

    def fake_call(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(incomplete if len(calls) == 1 else repaired)

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    generated = resume_app.generate_resume_quality_audit(
        api_key="test-key",
        job_description="Create implementation guides and detailed test-result documentation.",
        analysis_payload=ANALYSIS,
        current_resume=current_resume(),
        active_blueprints=active_blueprints(),
    )

    assert len(calls) == 2
    assert calls[1]["max_output_tokens"] == 12000
    assert "required_patch_diagnostics" in calls[1]["user_prompt"]
    assert generated["decision"] == "changes_suggested"
    assert generated["repair_attempted"] is True
    assert generated["attempt_count"] == 2


def test_generation_does_not_retry_deterministically_withheld_patch(monkeypatch):
    calls = []
    changes = bullet_change(
        bullet=(
            "Built Kubernetes services that improved workflow reliability by 55% across enterprise "
            "delivery teams while strengthening release automation and operational support."
        ),
    )
    unsafe = audit_result("changes_suggested", changes)
    unsafe["requirement_resolutions"] = [{
        "requirement_id": "req.kubernetes",
        "requirement": "Deploy backend services with Kubernetes",
        "priority": "important",
        "claim_type": "named_technology",
        "evidence_fit": "transferable",
        "resume_action": "patch_required",
        "status": "patched_transferable",
        "evidence_refs": ["upstream.mckinsey.bullet.1"],
        "change_ids": ["experience.mckinsey.rewrite-1"],
        "reason": "The proposed rewrite attempted to surface deployment evidence.",
    }]

    def fake_call(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(unsafe)

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    generated = resume_app.generate_resume_quality_audit(
        api_key="test-key",
        job_description="Deploy backend services with Kubernetes.",
        analysis_payload=ANALYSIS,
        current_resume=current_resume(),
        active_blueprints=active_blueprints(),
    )

    assert len(calls) == 1
    assert generated["attempt_count"] == 1
    assert generated["repair_attempted"] is False
    assert generated["decision"] == "approved"


def test_generation_retries_once_after_transient_network_failure(monkeypatch):
    calls = []
    approved = audit_result()

    def fake_call(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError(
                "OpenAI API request failed: remote end closed connection unexpectedly"
            )
        return copy.deepcopy(approved)

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)
    monkeypatch.setattr(resume_app.time, "sleep", lambda _seconds: None)

    generated = resume_app.generate_resume_quality_audit(
        api_key="test-key",
        job_description="Build reliable Python APIs.",
        analysis_payload=ANALYSIS,
        current_resume=current_resume(),
        active_blueprints=active_blueprints(),
    )

    assert len(calls) == 2
    assert generated["attempt_count"] == 2
    assert generated["decision"] == "approved"


def test_generation_does_not_restart_accepted_background_response(monkeypatch):
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        error = RuntimeError("OpenAI API request failed: connection reset")
        error.openai_response_started = True
        error.openai_response_id = "resp_audit_123"
        raise error

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    with pytest.raises(RuntimeError, match="connection reset"):
        resume_app.generate_resume_quality_audit(
            api_key="test-key",
            job_description="Build reliable Python APIs.",
            analysis_payload=ANALYSIS,
            current_resume=current_resume(),
            active_blueprints=active_blueprints(),
        )

    assert len(calls) == 1


def test_background_poll_reuses_response_id_after_transient_failure(monkeypatch):
    response_ids = []
    responses = [
        RuntimeError("OpenAI API request failed: connection reset"),
        {"id": "resp_audit_123", "status": "in_progress"},
        {"id": "resp_audit_123", "status": "completed", "output": []},
    ]

    def fake_get(**kwargs):
        response_ids.append(kwargs["response_id"])
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(resume_app, "_get_openai_response_payload", fake_get)
    monkeypatch.setattr(resume_app.time, "sleep", lambda _seconds: None)

    completed = resume_app._poll_openai_background_response(
        api_key="test-key",
        initial_response={"id": "resp_audit_123", "status": "queued"},
        request_timeout_seconds=60,
        overall_timeout_seconds=10,
        poll_interval_seconds=0.1,
    )

    assert completed["status"] == "completed"
    assert response_ids == ["resp_audit_123"] * 3


def test_non_truncation_failure_is_not_retried(monkeypatch):
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("authentication failed")

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    with pytest.raises(RuntimeError, match="authentication"):
        resume_app.generate_resume_quality_audit(
            api_key="test-key",
            job_description="Build reliable Python APIs.",
            analysis_payload=ANALYSIS,
            current_resume=current_resume(),
            active_blueprints=active_blueprints(),
        )

    assert len(calls) == 1
