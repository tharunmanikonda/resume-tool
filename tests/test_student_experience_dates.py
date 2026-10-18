import copy

import pytest

import app as resume_app


@pytest.fixture
def profile():
    return {
        "experience_history": [
            {"key": "mckinsey", "company": "Current Client", "location": "CA, USA",
             "title": "Software Engineer", "dates": "May 2025 - Present", "enabled": True},
            {"key": "uber", "company": "Previous Client", "location": "CA, USA",
             "title": "Software Engineer", "dates": "February 2024 - May 2025", "enabled": True},
        ],
        "academic_profile": {"start_date": "August 2026"},
    }


@pytest.mark.parametrize("mode", ["internship", "coop", "new_grad"])
def test_student_snapshot_and_blueprints_end_current_role(profile, mode):
    original = copy.deepcopy(profile)
    snapshot = resume_app.profile_for_resume_mode(profile, mode)
    assert snapshot["experience_history"][0]["dates"] == "May 2025 - September 2026"
    assert snapshot["experience_history"][1]["dates"] == "February 2024 - May 2025"
    assert resume_app.current_experience_blueprints(profile, mode)[0]["dates"] == "May 2025 - September 2026"
    assert profile == original
    assert "September 2026" in "\n".join(resume_app.resume_mode_prompt_lines(mode))


@pytest.mark.parametrize("mode", ["internship", "coop", "new_grad"])
def test_student_overrides_and_final_structure_cannot_restore_present(profile, mode, monkeypatch):
    monkeypatch.setattr(resume_app, "current_profile", lambda: profile)
    resume = {"experience": [{"dates": "May 2025 - Present"}]}
    overridden = resume_app.apply_experience_history_override(copy.deepcopy(resume), profile["experience_history"], mode)
    assert overridden["experience"][0]["dates"] == "May 2025 - September 2026"
    structured = resume_app.apply_resume_mode_structure(copy.deepcopy(resume), profile, mode)
    assert structured["experience"][0]["dates"] == "May 2025 - September 2026"
    assert structured["education"][0]["dates"] == "August 2026 - Present"
    applied = resume_app.apply_profile_overrides(copy.deepcopy(resume), mode)
    assert applied["experience"][0]["dates"] == "May 2025 - September 2026"


def test_professional_dates_and_prompts_are_unchanged(profile, monkeypatch):
    monkeypatch.setattr(resume_app, "current_profile", lambda: profile)
    assert resume_app.profile_for_resume_mode(profile)["experience_history"][0]["dates"] == "May 2025 - Present"
    assert resume_app.current_experience_blueprints(profile)[0]["dates"] == "May 2025 - Present"
    resume = {"experience": [{"dates": "May 2025 - Present"}]}
    assert resume_app.apply_profile_overrides(copy.deepcopy(resume))["experience"][0]["dates"] == "May 2025 - Present"
    assert resume_app.apply_experience_history_override(copy.deepcopy(resume), profile["experience_history"])["experience"][0]["dates"] == "May 2025 - Present"
    assert "September 2026" not in "\n".join(resume_app.resume_mode_prompt_lines("professional"))


@pytest.mark.parametrize("ending", ["Present", "present", "Current", "Now", "Ongoing", "Till date", "To date"])
def test_current_date_aliases(ending):
    assert resume_app.student_experience_dates(f"May 2025 - {ending}") == "May 2025 - September 2026"


def test_completed_dates_and_separator_are_preserved():
    assert resume_app.student_experience_dates("February 2024 - May 2025") == "February 2024 - May 2025"
    assert resume_app.student_experience_dates("May 2025 \u2013 Present") == "May 2025 \u2013 September 2026"
    assert resume_app.student_experience_dates("") == ""
