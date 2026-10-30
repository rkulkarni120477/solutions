import json
from types import SimpleNamespace
import pytest
from app.config import settings
from app.context import build_context
from app import providers
from app.schemas import Preferences, ProposalPlan
from test_workspace import sample_solution


def rfp_attachment():
    return SimpleNamespace(id='reference-id', filename='RFP "requirements" résumé.pdf', warning=None,
        passages=[{'reference': f'page {i+1}', 'text': 'Enterprise SSO, private search and security. "Validate" \\ requirements. ' * 25} for i in range(63)])


def test_full_solution_request_and_retry_fit_with_large_rfp(monkeypatch):
    monkeypatch.setattr(settings, 'max_input_tokens', 24000)
    context = build_context('Design enterprise SSO and private search', Preferences().model_dump(), [rfp_attachment()], [], ['Use OIDC'])
    assert 0 < len(context['reference_passages']) < 63
    assert context['approved_decisions'] == ['Use OIDC']
    for repair in [None, providers.SOLUTION_REPAIR]:
        text = providers.solution_payload(context, repair)
        assert providers.request_size(providers.SYSTEM, text) <= 24000
    assert f"Included {len(context['reference_passages'])} of 63" in context['retrieval_note']


def test_unicode_history_and_json_escaping_are_budgeted(monkeypatch):
    monkeypatch.setattr(settings, 'max_input_tokens', 24000)
    history = [SimpleNamespace(prompt='Historical requirement ' * 200, response={'summary': 'Historical context ' * 200}) for _ in range(4)]
    context = build_context('Design enterprise SSO for multilingual users: café, 東京, 🏢', Preferences().model_dump(), [rfp_attachment()], history, ['Retain audit records'])
    assert context['current_prompt'].endswith('café, 東京, 🏢')
    assert context['approved_decisions'] == ['Retain audit records']
    assert len(context['history']) < len(history)
    assert providers.solution_context_fits(context)


def test_provider_retry_uses_the_same_bounded_serialization(monkeypatch):
    monkeypatch.setattr(settings, 'max_input_tokens', 24000)
    monkeypatch.setattr(settings, 'llm_provider', 'openai')
    monkeypatch.setattr(settings, 'llm_model', 'test-model')
    context = build_context('Design enterprise SSO and private search', Preferences().model_dump(), [rfp_attachment()], [], [])
    calls = []
    solution = sample_solution()
    solution.sections[0].sources = [context['reference_passages'][0]['id']]
    def complete(system, text):
        assert providers.request_size(system, text) <= settings.max_input_tokens
        calls.append(json.loads(text))
        return 'invalid JSON' if len(calls) == 1 else solution.model_dump_json()
    monkeypatch.setattr(providers, '_complete', complete)
    result = providers.generate(context)
    assert result.sections[0].sources == solution.sections[0].sources
    assert len(calls) == 2 and calls[1]['repair'].startswith(providers.SOLUTION_REPAIR)
    assert 'json_invalid' in calls[1]['repair']
    assert calls[0]['context'] == calls[1]['context']


def test_agent_references_fit_without_modifying_the_original_payload(monkeypatch):
    monkeypatch.setattr(settings, 'max_input_tokens', 8000)
    monkeypatch.setattr(settings, 'llm_provider', 'openai')
    monkeypatch.setattr(settings, 'llm_model', 'test-model')
    payload = {'request':'RFP requirements ' * 100, 'reference_passages': rfp_attachment().passages}
    expected = ProposalPlan(response_type='Technical response', formats=['docx'], outline=['Solution'], win_themes=[], tone='Clear')
    def complete(system, text):
        assert providers.request_size(system, text) <= settings.max_input_tokens
        supplied = json.loads(text)['input']
        assert 0 < len(supplied['reference_passages']) < 63
        assert supplied['request'] == payload['request']
        assert 'Excluded passages have not been reviewed.' in supplied['retrieval_note']
        return expected.model_dump_json()
    monkeypatch.setattr(providers, '_complete', complete)
    assert providers.structured(ProposalPlan, 'Return a proposal plan.', payload) == expected
    assert len(payload['reference_passages']) == 63 and 'retrieval_note' not in payload


def test_oversized_prompt_is_rejected_without_silently_truncating_it(monkeypatch):
    monkeypatch.setattr(settings, 'max_input_tokens', 24000)
    with pytest.raises(ValueError, match='input budget'):
        build_context('Important requirement 🏢' * 2000, Preferences().model_dump(), [], [], [])


def test_diagram_repair_reduces_optional_references_without_changing_saved_context(monkeypatch):
    monkeypatch.setattr(settings, 'max_input_tokens', 24000)
    monkeypatch.setattr(settings, 'llm_provider', 'openai')
    monkeypatch.setattr(settings, 'llm_model', 'test-model')
    context = build_context('Design enterprise SSO', Preferences().model_dump(), [rfp_attachment()], [], [])
    original = json.dumps(context)
    repair = {'instruction':'Repair Mermaid syntax', 'source':'flowchart LR\n' + ' A --> B\n' * 300}
    assert providers.request_size(providers.SYSTEM, providers.solution_payload(context, repair)) > 24000
    def complete(system, text):
        assert providers.request_size(system, text) <= 24000
        payload = json.loads(text)
        assert payload['repair'] == repair
        assert len(payload['context']['reference_passages']) < len(context['reference_passages'])
        return sample_solution().model_dump_json()
    monkeypatch.setattr(providers, '_complete', complete)
    providers.generate(context, repair)
    assert json.dumps(context) == original
