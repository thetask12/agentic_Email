"""
AI-based fallback company-name extraction for the Job Outreach module.

guess_company_name_from_title() (search.py) is a cheap, free heuristic that
works for a well-formed result title like "AI Engineer - Acme Labs -
LinkedIn". It fails for a listing/aggregator page whose TITLE is generic
(e.g. "AI Engineer Jobs In Bangalore - Naukri.com") even though the page's
actual body text may still name a specific employer for a specific posting.
extract_company_name() is the fallback for exactly that case: it reads the
page's real content (via search.fetch_raw_page_content, a single extra
Tavily call) and asks the model to find a genuine, specific company name —
returning None (never a guess) if the page is itself just a category/search
listing with no single named employer.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.job_outreach.ai_client import structured_completion


class CompanyNameExtraction(BaseModel):
    company_name: str | None
    is_generic_listing_page: bool


EXTRACTION_SYSTEM_PROMPT = """You read the raw text of one job-related web page and identify
whether it is a SPECIFIC job posting from a named, real employer, or a
generic listing/search-results/category page that aggregates many jobs
without being tied to one company (e.g. a "browse all AI Engineer jobs in
Bangalore" page).

Rules:
- If the page clearly names one specific hiring company (e.g. in a "Company:"
  field, an "About <Company>" section, or a clearly attributed job posting),
  return that company_name and is_generic_listing_page=false.
- If the page is a category/search/listing page with no single named
  employer, or you cannot confidently identify one specific real company,
  return company_name=null and is_generic_listing_page=true.
- Never invent or guess a company name that isn't actually present in the
  text. Never return a job board's own name (LinkedIn, Naukri, Indeed,
  Apna, Foundit, TimesJobs, WorkIndia, Shine, Internshala, Glassdoor, etc.)
  as the company_name."""


def extract_company_name(page_url: str, page_content: str) -> CompanyNameExtraction | None:
    if not page_content.strip():
        return None
    user_prompt = f"Page URL: {page_url}\n\nPage content:\n{page_content}\n\nIdentify the hiring company, if any."
    return structured_completion(
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_model=CompanyNameExtraction,
    )
