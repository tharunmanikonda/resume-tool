import copy

from manual_resume_parser import COMPANIES, parse_updated_content_to_resume


def test_removed_middle_role_does_not_shift_later_experience():
    base_resume = {
        "title": "Base title",
        "summary": "Base summary",
        "technical_skills": [],
        "experience": [
            {
                "company": item["company"],
                "location": item["location"],
                "dates": item["dates"],
                "title": "Old title",
                "bullets": ["Old bullet"],
            }
            for item in COMPANIES
        ],
    }
    content = """Updated Title
Playwright Automation Engineer

Updated Summary
Automation engineer summary.

Updated Skills
Testing & Quality: Playwright, TypeScript.

Professional Experience

McKinsey & Company | CA, USA
Senior Test Automation Engineer | February 2024 - Present
• Built a Playwright framework.

KPMG | India
Software Engineer | September 2021 - July 2022
• Built integration tests.

Trigent Software | India
Frontend Engineer | March 2020 - August 2021
• Built browser automation.
"""

    parsed = parse_updated_content_to_resume(
        content,
        copy.deepcopy(base_resume),
        ["mckinsey", "kpmg", "trigent"],
    )

    assert parsed["experience"][0]["title"] == "Senior Test Automation Engineer"
    assert parsed["experience"][1]["title"] == ""
    assert parsed["experience"][1]["bullets"] == []
    assert parsed["experience"][2]["title"] == "Software Engineer"
    assert parsed["experience"][2]["bullets"] == ["Built integration tests."]
    assert parsed["experience"][3]["title"] == "Frontend Engineer"
    assert parsed["experience"][3]["bullets"] == ["Built browser automation."]


def test_full_content_is_stable_when_middle_role_is_disabled_at_export_time():
    base_resume = {
        "title": "Base title",
        "summary": "Base summary",
        "technical_skills": [],
        "experience": [
            {
                "company": item["company"],
                "location": item["location"],
                "dates": item["dates"],
                "title": "Old title",
                "bullets": ["Old bullet"],
            }
            for item in COMPANIES
        ],
    }
    titles = {
        "mckinsey": "Applied AI Engineer",
        "uber": "Platform Engineer",
        "kpmg": "Java Engineer",
        "trigent": "Frontend Engineer",
    }
    blocks = []
    for item in COMPANIES:
        blocks.append(
            f"{item['company']} | {item['location']}\n"
            f"{titles[item['key']]} | {item['dates']}\n"
            f"• Built reliable systems for {item['company']}."
        )
    content = """Updated Title
Automation Engineer

Updated Summary
Automation engineering summary.

Updated Skills
Testing & Quality: Playwright.

Professional Experience

""" + "\n\n".join(blocks)

    parsed = parse_updated_content_to_resume(
        content,
        copy.deepcopy(base_resume),
        ["mckinsey", "kpmg", "trigent"],
    )

    assert parsed["experience"][0]["title"] == "Applied AI Engineer"
    assert parsed["experience"][1]["title"] == "Platform Engineer"
    assert parsed["experience"][2]["title"] == "Java Engineer"
    assert parsed["experience"][2]["bullets"] == ["Built reliable systems for KPMG."]
    assert parsed["experience"][3]["title"] == "Frontend Engineer"
    assert parsed["experience"][3]["bullets"] == ["Built reliable systems for Trigent Software."]


def test_python_style_skill_lists_are_normalized_for_editor_preview():
    base_resume = {
        "title": "Base title",
        "summary": "Base summary",
        "technical_skills": [],
        "experience": [],
    }
    content = """Updated Title
Backend Engineer

Updated Summary
Backend engineering summary.

Updated Skills
Programming Languages: ['Java 11', 'Java 17', 'Python', 'TypeScript']
Data & Storage: [\"PostgreSQL\", \"MongoDB\", \"Redis\"]

Professional Experience
"""

    parsed = parse_updated_content_to_resume(content, base_resume, [])

    assert parsed["technical_skills"] == [
        {
            "category": "Programming Languages",
            "items": "Java 11, Java 17, Python, TypeScript",
        },
        {
            "category": "Data & Storage",
            "items": "PostgreSQL, MongoDB, Redis",
        },
    ]
