"""
Company research + official-email discovery for the Job Outreach module.
Structured outputs are Pydantic BaseModel classes (see ai_client.py's
client.beta.chat.completions.parse()) rather than raw JSON-schema dicts —
type-checked, auto-validated results instead of a plain dict the caller has
to trust field-by-field.

PRIMARY discovery path is fetch_emails_from_website(): once research_company()
has confidently identified a company's actual official website, this reads
that site's own pages directly (homepage, /contact, /about, /careers — a
plain public GET, never a login/scrape of gated content) and extracts any
visible email addresses with a regex. This is far more reliable than
guessing an email from generic search-result snippets (the previous sole
approach), which was occasionally matching an email from a completely
unrelated page (e.g. a YouTube video that happened to mention the company's
name) to the wrong company. discover_email() (the snippet-based AI
classifier) is kept as a fallback for when the website fetch finds no email
at all.

Same official-email-only filter rule as the main system: only email_type
GENERIC or FOUNDER are ever accepted as an outreach recipient — see
app.job_outreach.models.ACCEPTED_EMAIL_TYPES and service.py, which is where
the actual accept/reject decision is enforced (this module only classifies).
"""
from __future__ import annotations

import logging
import re
from typing import Literal

import httpx
from pydantic import BaseModel

from app.job_outreach.ai_client import structured_completion
from app.integrations.web_search import search

logger = logging.getLogger("job_outreach.email_discovery")

# Common paths, tried in order, most-likely-to-list-a-contact-email first.
# Homepage ("") is included because many sites only put their email in the
# FOOTER, which appears on every page including the homepage.
_CONTACT_PATHS = ["", "/contact", "/contact-us", "/about", "/about-us", "/careers"]

# Standard "name@domain.com" — also matches a mailto: link's target since
# that's plain text too (href="mailto:info@company.com").
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Catches a mailto: link specifically, even one written with HTML entities
# or extra whitespace/query-params inside the href, e.g.
# href="mailto:info@company.com?subject=Hello" — some templating systems
# don't render the address as plain visible text anywhere else on the page,
# only inside the link target, so this is checked in addition to _EMAIL_RE
# (which would already catch a plain mailto: href on its own, but this makes
# the intent explicit and lets us strip a trailing "?..." query string).
_MAILTO_RE = re.compile(r"mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", re.IGNORECASE)

# A handful of common human-readable obfuscations used to dodge scrapers,
# e.g. "info [at] company [dot] com" or "info (at) company (dot) com".
# Normalized to a real "@"/"." before running _EMAIL_RE again.
_OBFUSCATION_SUBS = (
    (re.compile(r"\s*[\[\(]\s*at\s*[\]\)]\s*", re.IGNORECASE), "@"),
    (re.compile(r"\s*[\[\(]\s*dot\s*[\]\)]\s*", re.IGNORECASE), "."),
)

# Emails that are clearly not a real business contact even though they match
# the regex — placeholder/example addresses that show up in boilerplate
# templates, tracking pixels, etc.
_JUNK_EMAIL_PATTERNS = (
    "example.com", "yourdomain", "domain.com", "sentry.io", "wixpress.com",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
)


def _is_junk_email(email: str) -> bool:
    lowered = email.lower()
    return any(p in lowered for p in _JUNK_EMAIL_PATTERNS)


_TAG_STRIP_BLOCKS_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")

# Words that suggest a nearby chunk of text might mention a contact address,
# used to pick out a short, relevant snippet instead of sending an entire
# page's worth of text to the model — keeps the AI call small and cheap
# (fewer tokens) and focuses it on the parts of the page actually worth
# reading, rather than nav menus/legal boilerplate/etc.
_CONTACT_KEYWORDS_RE = re.compile(
    r"\b(contact|email|e-mail|reach us|get in touch|write to us|inquir|enquir|"
    r"careers?|hr\b|recruit)", re.IGNORECASE,
)

_MAX_SNIPPET_CHARS = 1500  # per page, keeps the combined AI prompt small even across several pages
_SNIPPET_CONTEXT_CHARS = 200  # characters of context kept on each side of a keyword hit


def _html_to_visible_text(html: str) -> str:
    """Strips <script>/<style> blocks and all remaining HTML tags, leaving
    just the page's visible text, collapsed to single spaces/blank lines.
    Deliberately simple (no HTML parser dependency) — good enough to turn
    markup into readable text for an AI prompt, not meant to be a general
    HTML-to-text converter."""
    no_blocks = _TAG_STRIP_BLOCKS_RE.sub(" ", html)
    no_tags = _TAG_RE.sub(" ", no_blocks)
    collapsed = _WHITESPACE_RE.sub(" ", no_tags)
    return _BLANK_LINES_RE.sub("\n", collapsed).strip()


def _focused_contact_snippet(html: str) -> str:
    """Reduces a page's HTML down to a short, token-cheap snippet worth
    showing an AI model: strips markup to visible text, then keeps only the
    text around any contact-relevant keyword hits (see _CONTACT_KEYWORDS_RE),
    up to _MAX_SNIPPET_CHARS total. Falls back to the first _MAX_SNIPPET_CHARS
    of the visible text if no keyword hits at all (some pages genuinely just
    list an address without any of those words nearby, e.g. a bare footer
    line), so a real contact still has a chance of being included."""
    text = _html_to_visible_text(html)
    if not text:
        return ""
    matches = list(_CONTACT_KEYWORDS_RE.finditer(text))
    if not matches:
        return text[:_MAX_SNIPPET_CHARS]
    pieces: list[str] = []
    used_ranges: list[tuple[int, int]] = []
    for m in matches:
        start = max(0, m.start() - _SNIPPET_CONTEXT_CHARS)
        end = min(len(text), m.end() + _SNIPPET_CONTEXT_CHARS)
        if used_ranges and start <= used_ranges[-1][1]:
            # Overlaps/adjacent to the previous chunk — extend it instead of
            # duplicating overlapping text.
            prev_start, _ = used_ranges[-1]
            used_ranges[-1] = (prev_start, end)
            pieces[-1] = text[prev_start:end]
        else:
            used_ranges.append((start, end))
            pieces.append(text[start:end])
        if sum(len(p) for p in pieces) >= _MAX_SNIPPET_CHARS:
            break
    snippet = "\n...\n".join(pieces)
    return snippet[:_MAX_SNIPPET_CHARS]


def _extract_emails_from_html(html: str) -> list[str]:
    """Finds every plausible email address in a page's HTML, trying (in
    order) a plain regex match, mailto: link targets, and a de-obfuscated
    pass for common human-readable dodges ("name [at] domain [dot] com").
    Order doesn't matter for correctness (duplicates are deduped by the
    caller) — this just maximizes the chance of catching an address
    regardless of how the page author chose to publish it."""
    found: list[str] = []
    found.extend(_EMAIL_RE.findall(html))
    found.extend(_MAILTO_RE.findall(html))
    de_obfuscated = html
    for pattern, replacement in _OBFUSCATION_SUBS:
        de_obfuscated = pattern.sub(replacement, de_obfuscated)
    if de_obfuscated != html:
        found.extend(_EMAIL_RE.findall(de_obfuscated))
    return found


class CompanyResearch(BaseModel):
    official_website: str | None
    domain: str | None
    website_confidence: float


class EmailDiscovery(BaseModel):
    email: str | None
    email_type: Literal["GENERIC", "HR", "FOUNDER", "DEPARTMENT", "UNKNOWN"]
    email_source_url: str | None
    email_confidence: float


COMPANY_SYSTEM_PROMPT = """You research a company using ONLY the provided search result
snippets (title, link, snippet for several web search hits about the
company). Identify which result (if any) is the company's own official
website versus a directory/aggregator/unrelated company with a similar
name. Do not fabricate a website or domain that isn't supported by the
snippets. If uncertain, set the field to null and lower
website_confidence. website_confidence is 0-1."""

EMAIL_SYSTEM_PROMPT = """You extract a genuinely publicly-visible official business email address
for a company from the provided text only (either search snippets, or real
email addresses actually found on the company's own website).
Rules:
- NEVER invent or guess an email address (e.g. never construct
  info@<domain> unless that literal string appears in the source text).
- Classify the email_type strictly:
  - GENERIC: a general company inbox (info@, contact@, hello@, etc.)
  - FOUNDER: a named founder/owner/CEO's own email, explicitly identified
    as such in the source text
  - HR: a recruiting/HR/careers/jobs inbox
  - DEPARTMENT: any other specific department (sales@, support@, etc.)
  - UNKNOWN: cannot tell, or no email found
- If no email is visible in the provided text, return email=null,
  email_type="UNKNOWN", email_confidence=0.
- Never return a personal/private email not clearly published as a
  business contact."""


def research_company(company_name: str, city: str | None, search_snippets: list[dict]) -> CompanyResearch | None:
    context = "\n".join(
        f"- Title: {s['title']}\n  URL: {s['link']}\n  Snippet: {s['snippet']}" for s in search_snippets
    ) or "(no search results found)"
    user_prompt = (
        f"Company name: {company_name}\nLocation: {city or ''}\n\n"
        f"Search results:\n{context}\n\nIdentify the official website and domain."
    )
    return structured_completion(
        system_prompt=COMPANY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_model=CompanyResearch,
    )


def discover_email(company_name: str, domain: str | None, search_snippets: list[dict]) -> EmailDiscovery | None:
    context = "\n".join(
        f"- Title: {s['title']}\n  URL: {s['link']}\n  Snippet: {s['snippet']}" for s in search_snippets
    ) or "(no search results found)"
    user_prompt = (
        f"Company name: {company_name}\nDomain: {domain or 'unknown'}\n\n"
        f"Search results (contact/about pages):\n{context}\n\nExtract and classify a public official email if present."
    )
    return structured_completion(
        system_prompt=EMAIL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_model=EmailDiscovery,
    )


class WebsiteFetchResult(BaseModel):
    """Not an AI output — a plain container for fetch_emails_from_website()'s
    two kinds of findings: emails a regex could confidently extract, and a
    short, keyword-focused text snippet per page (see
    _focused_contact_snippet — NOT the raw HTML, and not the whole page's
    text either) for a page where the regex found nothing, e.g. a large
    corporate site that only exposes a contact form, an obfuscated address
    like "info [at] company [dot] com", or an email embedded in a way the
    regex doesn't match. Keeping both lets classify_emails() fall back to
    reading that focused snippet with an AI model instead of giving up the
    moment the regex comes back empty — while keeping the AI prompt small
    and cheap rather than pasting an entire page in."""
    model_config = {"arbitrary_types_allowed": True}
    emails: list[str]
    page_texts: dict[str, str]


async def fetch_emails_from_website(domain: str) -> WebsiteFetchResult:
    """Fetches the company's own homepage plus a few common pages
    (/contact, /about, /careers), extracts any visible email addresses via
    regex, and also keeps a short contact-focused text snippet (see
    _focused_contact_snippet) for each successfully-fetched page — used as a
    fallback input to classify_emails() when the regex finds nothing (many
    larger corporate sites only expose a contact form or an obfuscated
    address that a plain regex won't catch, but an AI reading a short,
    relevant excerpt of the page text often still can). Plain public GET
    requests only — no login, no scraping behind auth/CAPTCHA, same rule as
    everywhere else in this system. Never raises; a single company's site
    being unreachable just means empty results, not a crashed search
    cycle."""
    if not domain:
        return WebsiteFetchResult(emails=[], page_texts={})
    found: list[str] = []
    seen: set[str] = set()
    page_texts: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                  headers={"User-Agent": "Mozilla/5.0 (compatible; JobOutreachBot/1.0)"}) as client:
        for path in _CONTACT_PATHS:
            for scheme in ("https://", "http://"):
                url = f"{scheme}{domain}{path}"
                try:
                    resp = await client.get(url)
                except httpx.HTTPError:
                    continue
                if resp.status_code >= 400:
                    continue
                # Stored as a small, keyword-focused text snippet (not the
                # raw HTML) — this is what gets sent to the AI later if the
                # regex below finds nothing, so keeping it short matters for
                # token cost. See _focused_contact_snippet().
                snippet = _focused_contact_snippet(resp.text)
                if snippet:
                    page_texts[url] = snippet
                for match in _extract_emails_from_html(resp.text):
                    if _is_junk_email(match) or match.lower() in seen:
                        continue
                    seen.add(match.lower())
                    found.append(match)
                break  # https worked (or returned a real response) — skip http fallback for this path
            if len(found) >= 5:
                break  # enough candidates gathered — no need to keep crawling more pages
    logger.info("JOB_OUTREACH_WEBSITE_FETCH domain=%r emails_found=%d pages_fetched=%d",
                domain, len(found), len(page_texts))
    return WebsiteFetchResult(emails=found, page_texts=page_texts)


def classify_emails(company_name: str, domain: str | None, fetch_result: WebsiteFetchResult) -> EmailDiscovery | None:
    """AI-classifies the results of fetch_emails_from_website() into a
    single EmailDiscovery — the best email to use as the outreach recipient.

    If the regex found candidate emails, those are listed as the primary
    input (every candidate is a real address that was actually present on
    the company's own site, not inferred from a search snippet — far more
    reliable than discover_email()).

    If the regex found nothing at all but pages were still fetched, a short
    keyword-focused excerpt of each page (see _focused_contact_snippet —
    deliberately NOT the whole page, to keep the prompt small/cheap) is
    given to the model instead — many larger corporate sites only expose a
    contact form or an obfuscated address ("info [at] company [dot] com")
    that a plain regex won't catch, but a model reading that excerpt can
    often still recognize one. Returns None only if no pages were fetched at
    all (site unreachable/no domain)."""
    if not fetch_result.page_texts:
        return None
    if fetch_result.emails:
        listing = "\n".join(f"- {e}" for e in fetch_result.emails)
        source_block = f"Email addresses found on this company's own website:\n{listing}"
    else:
        pages = "\n\n".join(f"--- {url} ---\n{text}" for url, text in fetch_result.page_texts.items())
        source_block = (
            "No email address was found by a plain pattern match, but here is the raw "
            f"text of this company's own contact/about/careers pages — look carefully for "
            f"an email that may be obfuscated or written unusually (e.g. 'name [at] domain "
            f"[dot] com'):\n\n{pages}"
        )
    user_prompt = (
        f"Company name: {company_name}\nDomain: {domain or 'unknown'}\n\n"
        f"{source_block}\n\nPick the single best email to use as an outreach contact and classify it. "
        f"If genuinely no email is present anywhere in this text, return email=null, "
        f"email_type=\"UNKNOWN\", email_confidence=0."
    )
    return structured_completion(
        system_prompt=EMAIL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_model=EmailDiscovery,
    )


async def gather_company_snippets(company_name: str, city: str | None) -> list[dict]:
    location = city or ""
    results = await search(f'"{company_name}" {location} official website', num=6)
    return [r.to_dict() for r in results]


async def gather_contact_snippets(company_name: str, domain: str | None) -> list[dict]:
    if domain:
        results = await search(f'site:{domain} contact OR email OR "reach us"', num=6)
        if results:
            return [r.to_dict() for r in results]
    results = await search(f'"{company_name}" contact email', num=6)
    return [r.to_dict() for r in results]
