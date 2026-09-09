"""
Builds the short cold-application email for the Job Outreach module — NOT a
sales pitch. The body is a fixed template, not AI-generated per company;
the only thing that varies is the job title being applied for. The resume
PDF itself is attached by Apps Script (EmailSender.gs, via
RESUME_DRIVE_FILE_ID), not by this backend.

The greeting is always the generic "Dear Hiring Team," — deliberately NEVER
the discovered company name. That name is extracted from a search-result
title heuristically (guess_company_name_from_title in search.py) and is
unreliable enough (e.g. an aggregator page title like "AI Engineer Jobs In
Bangalore" being mistaken for a real company name) that using it in the
email itself risks an obviously wrong/odd greeting going out. The name is
still used for internal tracking (COMPANIES sheet, dedup) — just not here.
"""
from __future__ import annotations

from app.job_outreach.config import get_job_outreach_settings

SUBJECT_TEMPLATE = "Application for {job_title}"

# Short, plain-text application email. No inline images, no banners, no
# signature GIF (see "Email content rules"). This is the exact copy agreed
# with the candidate.
BODY_TEMPLATE = """Dear Hiring Team,

I'm an Agentic AI Developer with close to a year of hands-on experience
building production multi-agent LLM systems — LangChain, LangGraph, RAG
pipelines, and FastAPI, deployed end-to-end on Docker. I started as an
AI intern and was promoted to a full-time Agentic AI Developer and AI
Department Head within a year.

I'm looking for a {job_title} role at your company. Here's why I could
be a good fit:

- Design and ship production agentic AI systems — multi-agent
  orchestration, tool/function-calling, RAG with vector search (Qdrant,
  pgvector) — not just prototypes.
- Currently leading AI development as Department Head, including owning
  AI hiring and technical evaluation.
- Comfortable across the full stack — FastAPI/Pydantic backends, React
  frontends, and MLOps (Docker, CI/CD, model serving).

I've attached my resume with full experience and project details. Would
love to connect and discuss how I could contribute to your team.

Best regards,
{candidate_name}
{candidate_phone} | {candidate_email}
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
