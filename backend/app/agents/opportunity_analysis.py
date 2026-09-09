"""OpportunityAnalysis + LeadScore agents (System.txt sections 13, 442).

Analyzes the job title/description/skills for Botivate automation signals
(Excel-heavy reporting, daily MIS, dashboards, manual workflows, etc.) and
produces automation_opportunity_score (0-100), automation_signals[],
pain_points[], and a recommended_solution. Also computes an overall
lead_score combining opportunity score with data completeness/confidence.
"""
from app.integrations.openai_client import structured_completion

SCHEMA = {
    "type": "object",
    "properties": {
        "automation_opportunity_score": {"type": "integer"},
        "automation_signals": {"type": "array", "items": {"type": "string"}},
        "pain_points": {"type": "array", "items": {"type": "string"}},
        "recommended_solution": {
            "type": "string",
            "enum": ["AUTOROCKET", "CUSTOM_AUTOMATION", "BOTH", "MANUAL_REVIEW"],
        },
        "reasoning": {"type": "string"},
    },
    "required": ["automation_opportunity_score", "automation_signals", "pain_points",
                 "recommended_solution", "reasoning"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are Botivate's business-automation opportunity analyst. Botivate builds
automation for MIS, reporting, dashboards, and business operations (product:
AutoRocket) plus custom automation projects.

Given a job posting (title, description, skills, responsibilities), decide
how strongly it signals that the HIRING COMPANY currently relies on manual,
repetitive, spreadsheet-driven processes that Botivate could automate.

Look for signals such as: Excel-heavy reporting, daily MIS, dashboarding,
data consolidation across departments, manual ERP data pulls, sales/purchase/
inventory/dispatch/outstanding reporting, repetitive manual workflows, data
entry, business reporting, follow-up tracking.

automation_opportunity_score: integer 0-100, how strong the automation
signal is (0 = no signal, 100 = extremely strong / multiple explicit signals).

automation_signals: short phrases quoting or closely paraphrasing signals
actually present in the text — do not invent signals not supported by the
job description.

pain_points: concrete, plausible business pain points implied by the role
(e.g. "Manual daily sales reporting across branches"), grounded in the
provided text — do not fabricate specifics about the company that aren't
implied by the posting.

recommended_solution: AUTOROCKET (best fit for MIS/reporting/dashboard
automation), CUSTOM_AUTOMATION (broader/complex workflow automation needed),
BOTH, or MANUAL_REVIEW (signal too weak/ambiguous for the AI to be
confident)."""


def analyze_opportunity(job_title: str, description: str, skills: list[str]) -> dict | None:
    user_prompt = (
        f"Job title: {job_title}\n"
        f"Skills: {', '.join(skills) if skills else '(none listed)'}\n"
        f"Description:\n{description or '(no description available)'}\n\n"
        "Analyze the Botivate automation opportunity."
    )
    return structured_completion(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=SCHEMA,
        schema_name="opportunity_analysis",
    )


def compute_lead_score(opportunity_score: int, has_email: bool, email_confidence: float,
                        website_confidence: float, extraction_confidence: float) -> int:
    """Deterministic (non-AI) composite score so scoring stays auditable/reproducible.
    Weighted: 60% opportunity signal, 40% data-quality confidence."""
    data_quality = (
        (1.0 if has_email else 0.0) * 0.4
        + email_confidence * 0.25
        + website_confidence * 0.2
        + extraction_confidence * 0.15
    )
    score = (opportunity_score * 0.6) + (data_quality * 100 * 0.4)
    return max(0, min(100, round(score)))


def compute_priority(lead_score: int, opportunity_score: int) -> str:
    combined = (lead_score + opportunity_score) / 2
    if combined >= 80:
        return "URGENT"
    if combined >= 60:
        return "HIGH"
    if combined >= 35:
        return "MEDIUM"
    return "LOW"
