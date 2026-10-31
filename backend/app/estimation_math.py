"""Commercial arithmetic from validated effort and supplied rates; no model arithmetic."""
from decimal import Decimal, ROUND_HALF_UP

MODELS = {'effort_only':'Effort only','fixed_price':'Fixed price','time_and_materials':'Time & materials',
          'capped_time_and_materials':'Capped time & materials','milestone':'Milestone based',
          'retainer':'Retainer','hybrid':'Hybrid','other':'Other project model'}


def dec(value):
    return Decimal(str(value))


def money(value):
    return float(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def commercial_totals(solution, totals):
    s = solution
    complete = bool(s.estimates) and all(e.rate is not None for e in s.estimates)
    base = {key:money(sum((dec(getattr(e,key))*dec(e.rate) for e in s.estimates), Decimal(0))) for key in ['low','expected','high']} if complete else None
    role_rates = {r.role.strip().casefold():r.rate for r in s.pricing.role_rates}
    # Revised estimate rows take precedence over the original rate inputs.
    for role in {e.role.strip().casefold() for e in s.estimates}:
        rates = {e.rate for e in s.estimates if e.role.strip().casefold() == role}
        role_rates[role] = next(iter(rates)) if len(rates) == 1 else None
    variations = []
    for item in s.pricing.variations:
        rate = item.rate if item.rate is not None else role_rates.get(item.role.strip().casefold())
        variations.append({'name':item.name,'role':item.role,'effort_days':item.effort_days,'rate':rate,
                           'amount':money(dec(item.effort_days)*dec(rate)) if rate is not None else None})
    variation_cost = money(sum((dec(v['amount']) for v in variations), Decimal(0))) if all(v['amount'] is not None for v in variations) else None
    variation_effort = money(sum((dec(v.effort_days) for v in s.pricing.variations), Decimal(0)))
    fixed = totals['implementation_cost']['expected'] if totals['implementation_cost'] else None
    baseline = fixed if s.commercial_model == 'fixed_price' else base['expected'] if base else None
    revised = money(dec(baseline)+dec(variation_cost)) if baseline is not None and variation_cost is not None else None
    missing = []
    if not complete:
        missing.append('A supplied daily rate is required for every workstream; effort is available but the total is unpriced.')
    if variation_cost is None:
        missing.append('Supply daily rates for all variation roles.')
    if s.commercial_model == 'capped_time_and_materials' and s.pricing.budget_cap is None:
        missing.append('Supply the agreed T&M budget cap.')
    if s.commercial_model in ['milestone','hybrid','retainer','other']:
        missing.append('Agree the billing schedule, payment units and commercial terms; effort cost alone does not define this contract price.')
    if revised is not None and revised < 0 or totals['effort']['expected'] + variation_effort < 0:
        missing.append('The proposed reduction exceeds the baseline. Review the variation before pricing.')
        revised = None
    cap = s.pricing.budget_cap
    return {'model':s.commercial_model,'label':MODELS[s.commercial_model],'basis':s.commercial_basis,
            'currency':s.currency,'base_cost':base,'risk_adjusted_cost':totals['implementation_cost'],
            'indicative_fixed_price':fixed if s.commercial_model == 'fixed_price' else None,
            'variations':variations,'variation_effort_days':variation_effort,'variation_cost':variation_cost,
            'expected_with_variations':revised,'budget_cap':cap,
            'exceeds_cap':revised > cap if revised is not None and cap is not None else None,
            'missing_inputs':missing,
            'note':'Indicative planning estimate; not an approved quote. Fixed price uses expected effort plus contingency for the baseline scope. T&M uses actual approved time at agreed rates; projected base cost excludes contingency. Variations are separate proposed scope changes, priced at supplied rates without additional contingency. Tax, margin and recurring operating costs are not added.'}
