from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


CommercialModel = Literal['effort_only', 'fixed_price', 'time_and_materials', 'capped_time_and_materials', 'milestone', 'retainer', 'hybrid', 'other']


class RoleRate(Strict):
    role: str = Field(min_length=1, max_length=150)
    rate: float | None = Field(default=None, ge=0, le=1000000)


class EstimateVariation(Strict):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=150)
    effort_days: float = Field(ge=-100000, le=100000)
    rate: float | None = Field(default=None, ge=0, le=1000000)


class PricingInputs(Strict):
    model: Literal['auto', 'effort_only', 'fixed_price', 'time_and_materials', 'capped_time_and_materials', 'milestone', 'retainer', 'hybrid', 'other'] = 'auto'
    currency: str | None = Field(default=None, pattern='^[A-Z]{3}$')
    role_rates: list[RoleRate] = Field(default_factory=list, max_length=40)
    budget_cap: float | None = Field(default=None, ge=0, le=1000000000000)
    variations: list[EstimateVariation] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def unique_roles(self):
        roles = [row.role.strip().casefold() for row in self.role_rates]
        if len(roles) != len(set(roles)):
            raise ValueError('Supply one daily rate per role.')
        return self


class Preferences(Strict):
    pricing: PricingInputs = Field(default_factory=PricingInputs)
    word_template_id: str | None = Field(default=None, max_length=36)
    powerpoint_template_id: str | None = Field(default=None, max_length=36)
    cloud: Literal['AWS', 'Azure', 'GCP', 'Hybrid', 'On-premises', 'No preference'] = 'No preference'
    technologies: str = Field(default='', max_length=2000)
    domain: str = Field(default='', max_length=500)
    scale: str = Field(default='', max_length=1500)
    constraints: str = Field(default='', max_length=2000)
    detail: Literal['Concise', 'Standard', 'Detailed'] = 'Detailed'
    outputs: list[Literal['solution', 'diagrams', 'estimates', 'plan', 'presentation', 'custom']] = Field(default_factory=lambda: ['solution', 'diagrams', 'estimates', 'plan', 'presentation'], max_length=6)
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
    kind: Literal['network', 'conceptual', 'technical', 'logical', 'deployment', 'integration', 'workflow', 'sequence', 'resource_management', 'racii', 'estimations', 'development_plan', 'methodology']
    source: str = Field(max_length=20000)
    description: str = Field(default='', max_length=6000)


class ResponsibilityRow(Strict):
    activity: str = Field(min_length=1, max_length=200)
    responsible: str = Field(min_length=1, max_length=150)
    accountable: str = Field(min_length=1, max_length=150)
    consulted: str = Field(default='', max_length=150)
    informed: str = Field(default='', max_length=150)
    involved: str = Field(default='', max_length=150)


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


class ResourceRole(Strict):
    role: str = Field(min_length=1, max_length=150)
    count: float = Field(ge=0, le=1000)
    allocation: str = Field(default='', max_length=200)
    responsibilities: str = Field(default='', max_length=1000)
    effort_days: float = Field(default=0, ge=0, le=100000)


class Methodology(Strict):
    name: str = Field(max_length=150)
    overview: str = Field(max_length=4000)
    ceremonies: list[str] = Field(default_factory=list, max_length=20)
    governance: list[str] = Field(default_factory=list, max_length=20)
    quality_gates: list[str] = Field(default_factory=list, max_length=20)


class Solution(Strict):
    commercial_model: CommercialModel = 'effort_only'
    commercial_basis: str = Field(default='', max_length=2000)
    pricing: PricingInputs = Field(default_factory=PricingInputs)
    title: str = Field(max_length=150)
    summary: str = Field(max_length=8000)
    sections: list[Section] = Field(max_length=30)
    assumptions: list[str] = Field(max_length=30)
    questions: list[str] = Field(max_length=15)
    diagrams: list[Diagram] = Field(max_length=12)
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
    # Populated by the presales Resources and DeliveryMethodology agents.
    resources: list[ResourceRole] = Field(default_factory=list, max_length=40)
    methodology: Methodology | None = None
    racii: list[ResponsibilityRow] = Field(default_factory=list, max_length=20)


ProposalFormat = Literal['docx', 'pptx']


class ProposalCreate(Strict):
    request: str = Field(min_length=20, max_length=16000)
    formats: list[ProposalFormat] = Field(default_factory=list, max_length=2)
    preferences: Preferences = Field(default_factory=Preferences)


class ProposalAnswers(Strict):
    answers: dict[str, str] = Field(default_factory=dict, max_length=30)
    proceed_with_assumptions: bool = False

    @model_validator(mode='after')
    def bounded(self):
        if any(len(k) > 60 or len(v) > 4000 for k, v in self.answers.items()):
            raise ValueError('Answer keys are limited to 60 characters and answers to 4000 characters.')
        if not self.proceed_with_assumptions and not any(v.strip() for v in self.answers.values()):
            raise ValueError('Provide at least one answer or proceed with assumptions.')
        return self


class ProposalReview(Strict):
    decision: Literal['approve', 'request_changes']
    comments: str = Field(default='', max_length=4000)

    @model_validator(mode='after')
    def explain_changes(self):
        if self.decision == 'request_changes' and len(self.comments.strip()) < 5:
            raise ValueError('Describe the changes required for the next draft.')
        return self


class OrchestratorRequest(Strict):
    """Free-text request to the Orchestrator, which routes it by proposal state."""
    message: str = Field(min_length=2, max_length=16000)
    formats: list[ProposalFormat] = Field(default_factory=list, max_length=2)
    preferences: Preferences = Field(default_factory=Preferences)


class RequirementItem(Strict):
    id: str = Field(max_length=60)
    category: str = Field(max_length=80)
    statement: str = Field(max_length=1500)
    status: Literal['clear', 'ambiguous', 'answered', 'assumed']
    source: str = Field(default='', max_length=300)


class MissingInformation(Strict):
    id: str = Field(max_length=60)
    question: str = Field(max_length=600)
    reason: str = Field(max_length=600)
    required: bool = True


class RequirementsAssessment(Strict):
    summary: str = Field(max_length=4000)
    requirements: list[RequirementItem] = Field(max_length=60)
    missing: list[MissingInformation] = Field(max_length=20)
    ready: bool


class ProposalPlan(Strict):
    response_type: str = Field(max_length=150)
    formats: list[ProposalFormat] = Field(min_length=1, max_length=2)
    outline: list[str] = Field(min_length=1, max_length=25)
    win_themes: list[str] = Field(max_length=10)
    tone: str = Field(max_length=300)


class EstimationResult(Strict):
    commercial_model: CommercialModel = 'effort_only'
    commercial_basis: str = Field(default='', max_length=2000)
    estimates: list[Estimate] = Field(min_length=1, max_length=100)
    contingency_percent: float = Field(ge=0, le=100)
    notes: str = Field(default='', max_length=2000)


class ResourcePlan(Strict):
    resources: list[ResourceRole] = Field(min_length=1, max_length=40)
    staffing_fte: float = Field(gt=0, le=10000)
    notes: str = Field(default='', max_length=2000)


class MethodologyPlan(Strict):
    methodology: Methodology
    phases: list[Phase] = Field(min_length=1, max_length=20)


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
    result = {
        'effort': {k: money(v) for k, v in sums.items()},
        'with_contingency': {k: money(v * multiplier) for k, v in sums.items()},
        'implementation_cost': {k: money(sum(Decimal(str(getattr(r, k))) * Decimal(str(r.rate)) for r in solution.estimates) * multiplier) for k in sums} if rated else None,
        'capacity_floor_weeks': money(sums['expected'] * multiplier / Decimal(str(solution.staffing_fte)) / 5),
        'duration_basis': 'Capacity lower bound at 5 working days/week; dependencies, specialist capacity and approvals may extend elapsed delivery.',
    }
    from .estimation_math import commercial_totals
    result['commercial'] = commercial_totals(solution, result)
    return result
