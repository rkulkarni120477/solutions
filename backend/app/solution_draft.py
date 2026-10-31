"""Bounded solution generation contracts; specialist artifacts are created later."""
from typing import Annotated
from pydantic import Field
from .schemas import Strict, Section, Estimate, Phase, Solution

ShortNote = Annotated[str, Field(max_length=350)]


class DraftSection(Section):
    content: str = Field(max_length=2600, description='Complete focused section, about 150-250 words. No repeated reference text or raw JSON.')
    sources: list[str] = Field(default_factory=list, max_length=10)


class SolutionDraft(Strict):
    title: str = Field(max_length=150)
    summary: str = Field(max_length=1600)
    sections: list[DraftSection] = Field(min_length=1, max_length=8)
    assumptions: list[ShortNote] = Field(max_length=10)
    questions: list[ShortNote] = Field(max_length=6)
    estimates: list[Estimate] = Field(max_length=12, description='Compact effort seed for Estimations Agent, not commercial totals.')
    phases: list[Phase] = Field(max_length=6)
    currency: str = Field(default='USD', pattern='^[A-Z]{3}$')
    contingency_percent: float = Field(default=15, ge=0, le=100)
    staffing_fte: float = Field(default=3, gt=0, le=10000)
    duration_note: str = Field(max_length=700)
    operating_cost_note: str = Field(max_length=700)
    exclusions: list[ShortNote] = Field(max_length=10)

    def solution(self):
        return Solution.model_validate({**self.model_dump(), 'diagrams':[], 'artifact_requests':[]})


class SectionTopic(Strict):
    title: str = Field(max_length=150)
    classification: Section.model_fields['classification'].annotation


class SolutionOutline(Strict):
    title: str = Field(max_length=150)
    summary: str = Field(max_length=1600)
    section_topics: list[SectionTopic] = Field(min_length=1, max_length=8)
    assumptions: list[ShortNote] = Field(max_length=10)
    questions: list[ShortNote] = Field(max_length=6)
    currency: str = Field(default='USD', pattern='^[A-Z]{3}$')
    contingency_percent: float = Field(default=15, ge=0, le=100)
    staffing_fte: float = Field(default=3, gt=0, le=10000)
    duration_note: str = Field(max_length=700)
    operating_cost_note: str = Field(max_length=700)
    exclusions: list[ShortNote] = Field(max_length=10)


class DetailedSection(Section):
    content: str = Field(max_length=5200, description='One complete solution section, about 300-650 words, within the token budget.')
    sources: list[str] = Field(default_factory=list, max_length=12)


class DeliverySeed(Strict):
    estimates: list[Estimate] = Field(max_length=12)
    phases: list[Phase] = Field(max_length=6)
