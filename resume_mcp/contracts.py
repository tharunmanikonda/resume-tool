"""Strict public contracts for Poke MCP resume tools."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReplaceResumeTitle(StrictModel):
    operation: Literal["replace_resume_title"]
    new_text: str = Field(min_length=1)


class ReplaceSummary(StrictModel):
    operation: Literal["replace_summary"]
    new_text: str = Field(min_length=1)


class ReplaceExperienceTitle(StrictModel):
    operation: Literal["replace_experience_title"]
    role_key: str = Field(min_length=1)
    new_text: str = Field(min_length=1)


class ReplaceBullet(StrictModel):
    operation: Literal["replace_bullet"]
    role_key: str = Field(min_length=1)
    bullet_number: int = Field(ge=1)
    expected_text: str = Field(min_length=1)
    new_text: str = Field(min_length=1)


class AddBullet(StrictModel):
    operation: Literal["add_bullet"]
    role_key: str = Field(min_length=1)
    position: int = Field(ge=1)
    new_text: str = Field(min_length=1)


class RemoveBullet(StrictModel):
    operation: Literal["remove_bullet"]
    role_key: str = Field(min_length=1)
    bullet_number: int = Field(ge=1)
    expected_text: str = Field(min_length=1)


class MoveBullet(StrictModel):
    operation: Literal["move_bullet"]
    role_key: str = Field(min_length=1)
    bullet_number: int = Field(ge=1)
    new_position: int = Field(ge=1)


class AddSkill(StrictModel):
    operation: Literal["add_skill"]
    category: str = Field(min_length=1)
    skill: str = Field(min_length=1)


class RemoveSkill(StrictModel):
    operation: Literal["remove_skill"]
    category: str = Field(min_length=1)
    skill: str = Field(min_length=1)


class ReplaceSkillCategory(StrictModel):
    operation: Literal["replace_skill_category"]
    category: str = Field(min_length=1)
    new_category: str = Field(min_length=1)


class SetExperienceEnabled(StrictModel):
    operation: Literal["set_experience_enabled"]
    role_key: str = Field(min_length=1)
    enabled: bool


ResumeChange = Annotated[
    Union[
        ReplaceResumeTitle,
        ReplaceSummary,
        ReplaceExperienceTitle,
        ReplaceBullet,
        AddBullet,
        RemoveBullet,
        MoveBullet,
        AddSkill,
        RemoveSkill,
        ReplaceSkillCategory,
        SetExperienceEnabled,
    ],
    Field(discriminator="operation"),
]


class StartResumeGenerationInput(StrictModel):
    job_description: str = Field(min_length=120)
    identity_id: str | None = None
    company_name: str | None = None
    role_title: str | None = None
    source_url: str | None = None


class GetResumeStatusInput(StrictModel):
    draft_id: str = Field(min_length=1)
    include_review: bool = False
    wait_seconds: int = Field(default=0, ge=0, le=20)


class ContinueResumeActionInput(StrictModel):
    draft_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    selection: str | dict


class UpdateResumeDraftInput(StrictModel):
    draft_id: str = Field(min_length=1)
    base_revision: int = Field(ge=1)
    changes: list[ResumeChange] = Field(min_length=1)


class FinalizeResumeInput(StrictModel):
    draft_id: str = Field(min_length=1)
    base_revision: int = Field(ge=1)
    confirmed: bool
