from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Preferences(Strict):
    cloud: Literal['AWS', 'Azure', 'GCP', 'Hybrid', 'On-premises', 'No preference'] = 'No preference'
    technologies: str = Field(default='', max_length=2000)
    domain: str = Field(default='', max_length=500)
    scale: str = Field(default='', max_length=1500)
    constraints: str = Field(default='', max_length=2000)
    detail: Literal['Concise', 'Standard', 'Detailed'] = 'Detailed'
    outputs: list[Literal['solution', 'diagrams', 'estimates', 'plan', 'presentation', 'custom']] = Field(default_factory=lambda: ['solution', 'diagrams', 'estimates', 'plan'], max_length=6)
    custom_deliverables: str = Field(default='', max_length=1500)


class Generate(Strict):
    prompt: str = Field(min_length=8, max_length=16000)
    preferences: Preferences = Field(default_factory=Preferences)


class Section(Strict):
    title: str = Field(max_length=150)
    content: str = Field(max_length=16000)
    classification: Literal['supplied fact', 'assumption', 'recommendation', 'requires validation']
    sources: list[str] = Field(default_factory=list, max_length=30)


class Diagram(Strict):
    title: str = Field(max_length=150)
    kind: Literal['conceptual', 'logical', 'deployment', 'integration', 'workflow', 'sequence']
    source: str = Field(max_length=20000)


class Estimate(Strict):
    activity: str = Field(min_length=1, max_length=200)
    role: str = Field(max_length=150)
    low: float = Field(ge=0, le=100000)
    expected: float = Field(ge=0, le=100000)
    high: float = Field(ge=0, le=100000)
    rate: float | None = Field(default=None, ge=0, le=1000000)
    dependency: str = Field(default='', max_length=400)
    confidence: Literal['low', 'medium', 'high'] = 'low'

    @model_validator(mode='after')
    def ordered(self):
        if not self.low <= self.expected <= self.high:
            raise ValueError('Effort must satisfy low <= expected <= high')
        return self


class Phase(Strict):
    name: str = Field(max_length=150)
    duration: str = Field(max_length=150)
    activities: list[str] = Field(max_length=20)
    dependencies: str = Field(max_length=1000)


class Solution(Strict):
    title: str = Field(max_length=150)
    summary: str = Field(max_length=8000)
    sections: list[Section] = Field(max_length=30)
    assumptions: list[str] = Field(max_length=30)
    questions: list[str] = Field(max_length=15)
    diagrams: list[Diagram] = Field(max_length=5)
    estimates: list[Estimate] = Field(max_length=100)
    effort_unit: Literal['person-days'] = 'person-days'
    currency: str = Field(default='USD', pattern='^[A-Z]{3}$')
    contingency_percent: float = Field(default=15, ge=0, le=100)
    staffing_fte: float = Field(default=3, gt=0, le=10000)
    duration_note: str = Field(max_length=2000)
    operating_cost_note: str = Field(max_length=2000)
    exclusions: list[str] = Field(max_length=30)
    phases: list[Phase] = Field(max_length=20)
    artifact_requests: list[Literal['docx', 'pdf', 'xlsx', 'pptx', 'zip']] = Field(max_length=5)


class EstimateUpdate(Strict):
    estimates: list[Estimate] = Field(max_length=100)
    currency: str = Field(pattern='^[A-Z]{3}$')
    contingency_percent: float = Field(ge=0, le=100)
    staffing_fte: float = Field(gt=0, le=10000)


def calculate(solution: Solution):
    def money(value):
        return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    sums = {key: sum(Decimal(str(getattr(row, key))) for row in solution.estimates) for key in ['low', 'expected', 'high']}
    multiplier = 1 + Decimal(str(solution.contingency_percent)) / 100
    rated = bool(solution.estimates) and all(row.rate is not None for row in solution.estimates)
    return {
        'effort': {k: money(v) for k, v in sums.items()},
        'with_contingency': {k: money(v * multiplier) for k, v in sums.items()},
        'implementation_cost': {k: money(sum(Decimal(str(getattr(r, k))) * Decimal(str(r.rate)) for r in solution.estimates) * multiplier) for k in sums} if rated else None,
        'capacity_floor_weeks': money(sums['expected'] * multiplier / Decimal(str(solution.staffing_fte)) / 5),
        'duration_basis': 'Capacity lower bound at 5 working days/week; dependencies, specialist capacity and approvals may extend elapsed delivery.',
    }
