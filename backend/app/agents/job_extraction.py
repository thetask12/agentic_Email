"""JobExtraction agent — turns a raw search hit (title+snippet+url) into a
structured job record. Never invents facts not present in the source text;
low-confidence extractions are flagged so the pipeline can down-rank them."""
from app.integrations.openai_client import structured_completion

SCHEMA = {
    "type": "object",
    "properties": {
        "job_title": {"type": "string"},
        "company_name": {"type": ["string", "null"]},
        "city": {"type": ["string", "null"]},
        "state": {"type": ["string", "null"]},
        "experience": {"type": ["string", "null"]},
        "employment_type": {"type": ["string", "null"]},
        "skills": {"type": "array", "items": {"type": "string"}},
        "qualification": {"type": ["string", "null"]},
        "salary": {"type": ["string", "null"]},
        "is_relevant_role": {"type": "boolean"},
        "extraction_confidence": {"type": "number"},
    },
    "required": ["job_title", "company_name", "city", "state", "experience", "employment_type",
                 "skills", "qualification", "salary", "is_relevant_role", "extraction_confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You extract structured job posting facts from a search engine result
snippet (title + snippet + URL). Only use information explicitly present in
the provided text. Never invent a company name, location, or skill that is
not stated or strongly implied by the text. If a field cannot be determined,
return null. Set extraction_confidence between 0 and 1 based on how much of
the record you could actually read versus guess. Set is_relevant_role=false
if the posting is clearly not a job listing (e.g. an article, a listing
aggregator homepage, or unrelated content)."""


def extract_job(title: str, snippet: str, url: str, requested_job_title: str) -> dict | None:
    user_prompt = (
        f"Requested job title search: {requested_job_title}\n"
        f"Search result title: {title}\n"
        f"Search result snippet: {snippet}\n"
        f"URL: {url}\n\n"
        "Extract the job posting fields."
    )
    return structured_completion(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=SCHEMA,
        schema_name="job_extraction",
    )
