"""
Builds the short cold-application email for the Job Outreach module — NOT a
sales pitch, NOT personalized per-company beyond the job title (per
docs/job-outreach-schema.md "Email content rules": no employer/company name
is ever disclosed in the body). The resume PDF itself is attached by Apps
Script (EmailSender.gs, via RESUME_DRIVE_FILE_ID), not by this backend.

Mirrors the app/agents/email_generation.py pattern (a fixed template
rendered with a small set of substitutions) rather than an AI-personalized
pitch — there is deliberately nothing here to personalize: the whole point
is one short, honest, generic application email sent to many companies.
"""
from __future__ import annotations

from app.job_outreach.config import get_job_outreach_settings

SUBJECT_TEMPLATE = "Application: {job_title}"

# Short, plain-text application email. No inline images, no banners, no
# signature GIF (see "Email content rules"). Bullet highlights are
# deliberately generic/skills-and-experience-shaped rather than tied to any
# specific employer, since no employer name may be disclosed.
BODY_TEMPLATE = """Hello,

I'm writing to express interest in the {job_title} role at your company.

I have hands-on experience building AI and agentic AI systems — including
LLM-powered automation pipelines, retrieval-augmented applications, and
production backend services — with a progression from individual
contributor work into designing and owning end-to-end AI features.

A few highlights:
- Built and shipped agentic AI workflows integrating LLMs with real
  business systems (search, data pipelines, and automated decisioning).
- Designed backend services (Python/FastAPI) powering AI-driven products,
  including integrations with vector search, structured-output LLM calls,
  and third-party APIs.
- Comfortable owning a feature end-to-end: architecture, implementation,
  and iterating based on real usage.

I've attached my resume for more detail. I'd welcome the chance to talk
about how I could contribute to your team.

Thank you for your time and consideration.

Best regards,
{candidate_name}
{candidate_phone}
{candidate_email}
LinkedIn: {candidate_linkedin}
GitHub: {candidate_github}
"""


def generate_application_email(*, job_title: str, sender_email: str) -> dict:
    """Returns {subject, body} for one application email. `sender_email` is
    this module's own sender identity (JOB_OUTREACH_SENDER_EMAIL) used only
    in the signature line — Apps Script decides the actual Gmail From
    address (always whichever account authorized its triggers)."""
    settings = get_job_outreach_settings()
    subject = SUBJECT_TEMPLATE.format(job_title=job_title)
    body = BODY_TEMPLATE.format(
        job_title=job_title,
        candidate_name=settings.job_outreach_candidate_name,
        candidate_phone=settings.job_outreach_candidate_phone,
        candidate_email=sender_email,
        candidate_linkedin=settings.job_outreach_candidate_linkedin,
        candidate_github=settings.job_outreach_candidate_github,
    )
    return {"subject": subject, "body": body}
