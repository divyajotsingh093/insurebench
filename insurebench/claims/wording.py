"""Render synthetic policy wordings (markdown) from policies.py so wording and engine never drift."""
from __future__ import annotations

from .. import CANARY, CARRIER
from . import policies as P


def sections(code: str) -> list[tuple[str, str, str]]:
    pol = P.POLICIES[code]
    c = lambda n: P.clause_id(code, n)  # noqa: E731
    subl = "\n".join(f"| {k.replace('_', ' ')} | {v:,} |" for k, v in pol["sublimits"].items()) or "| (none) | - |"
    np_ = "\n".join(f"- `{k}`: {v}" for k, v in P.NON_PAYABLE.items())
    ref = "\n".join(f"| {k} | {v:,} |" for k, v in P.REFERENCE_CHARGES.items())
    cond = "\n".join(f"- {k}: required when {v}" for k, v in P.REQUIRED_DOCS_CONDITIONAL.items())
    flags = "\n".join(f"- {k}: {v}" for k, v in P.FRAUD_FLAGS.items())
    spec = ", ".join(sorted(P.SPECIFIC_WAIT_CONDITIONS))
    s = [
        (c("1.1"), "Policy period", f"Cover applies only to hospitalisations with an admission date on or after the start and on or before the end of the current policy period shown in the schedule. Claims for admissions outside the policy period are rejected under {c('1.1')}."),
        (c("2.1"), "Initial waiting period", f"Waiting periods run from the FIRST inception date shown in the schedule (continuous renewals preserve it). No claim is payable for an admission within the first {pol['initial_wait_days']} days (days in force = admission date minus first inception date, so an admission on day {pol['initial_wait_days']} or later is covered), except hospitalisation due to an accident. Accidents are exempt from ALL waiting periods (2.1, 2.2, 2.3)."),
        (c("2.2"), "Specific disease waiting period", f"Treatment for the following conditions is not payable until {pol['specific_wait_days']} days in force: {spec}."),
        (c("2.3"), "Pre-existing disease waiting period", f"A condition diagnosed before inception is a pre-existing disease (PED). Hospitalisation related to a PED is not payable until {pol['ped_wait_days']} days in force."),
        (c("3.1"), "Non-payable items", f"The following item categories (Annex A) are not payable and are deducted in full:\n{np_}"),
        (c("4.1"), "Room rent limit", f"Eligible room rent is up to {pol['room_limit_per_day']:,} per day. Room charges above the limit are deducted: (billed daily rate - limit) x days."),
        (c("4.2"), "Proportionate deduction", f"If the billed daily room rate exceeds the {c('4.1')} limit, the associated medical expenses ({', '.join(sorted(P.ASSOCIATED_CATEGORIES))}) are paid in the proportion limit / billed daily rate; the remainder is deducted under {c('4.2')}. Medicines, consumables, implants and ICU charges are not subject to proportionate deduction."),
        (c("4.3"), "ICU limit", f"Eligible ICU charges are up to {pol['icu_limit_per_day']:,} per day; the excess is deducted. No proportionate deduction applies to ICU."),
        (c("4.4"), "Disease sublimits", f"For the conditions below the admissible amount (after {c('3.1')}-{c('4.3')}) is capped at the sublimit per hospitalisation; the excess is deducted.\n\n| Condition | Sublimit |\n|---|---|\n{subl}"),
        (c("5.1"), "Deductible", f"A deductible of {pol['deductible']:,} per claim is applied after sublimits." if pol["deductible"] else "No deductible applies to this plan."),
        (c("5.2"), "Co-payment", f"The insured bears {pol['copay_pct']}% of the admissible amount remaining after the deductible." if pol["copay_pct"] else "No co-payment applies to this plan."),
        (c("5.3"), "Sum insured (annual limit)", f"The sum insured is {pol['sum_insured']:,} per policy year, reduced by claims already paid for admissions in the same policy period (see the claims history lookup). Any amount above the remaining sum insured is deducted."),
        (c("6.1"), "Claim documentation", f"Always required: {', '.join(P.REQUIRED_DOCS_BASE)}.\nAdditionally:\n{cond}\nIf any required document is missing and no rejection ground applies, the claim is pended for documents (decision pend_for_documents) and no amount is paid yet."),
        (c("6.2"), "Duplicate and fraudulent claims", f"A claim with the same insured, hospital, admission date and billed total as a previously submitted claim is a duplicate and is rejected under {c('6.2')}."),
        (c("6.3"), "Order of application", f"Adjudicate in this order: (1) policy period {c('1.1')}; (2) duplicate {c('6.2')}; (3) waiting periods {c('2.1')}, {c('2.2')}, {c('2.3')}; (4) documents {c('6.1')}; (5) non-payable items {c('3.1')}; (6) room rent {c('4.1')}, proportionate deduction {c('4.2')} and ICU {c('4.3')}; (7) sublimit {c('4.4')}; (8) deductible {c('5.1')}; (9) co-payment {c('5.2')}; (10) remaining sum insured {c('5.3')}. Round each deduction to 2 decimals (half up). Hospital records (discharge summary, itemised bill) are authoritative for dates. Decision: pay if payable equals the billed total; partial if 0 < payable < billed; reject if a rejection ground applies or payable is 0."),
        (c("6.4"), "Special investigation referral", f"Raise the following red flags where found. Red flags do NOT change the amount calculated (other than rejection grounds above) but the claim is referred to the special investigations unit.\n{flags}\n\nAnnex C reference unit charges:\n\n| Item ref | Reference unit charge |\n|---|---|\n{ref}"),
    ]
    return s


def render_wording(code: str) -> str:
    pol = P.POLICIES[code]
    parts = [f"<!-- {CANARY} -->", f"# {CARRIER} - {pol['name']} ({code}) policy wording (synthetic, v0)", "",
             "> Synthetic policy wording for the InsureBench benchmark. Not a real insurance contract.", "",
             f"Schedule summary: sum insured {pol['sum_insured']:,}; deductible {pol['deductible']:,}; co-pay {pol['copay_pct']}%; "
             f"room limit {pol['room_limit_per_day']:,}/day; ICU limit {pol['icu_limit_per_day']:,}/day.", ""]
    for cid, title, body in sections(code):
        parts += [f"## [{cid}] {title}", "", body, ""]
    return "\n".join(parts)
