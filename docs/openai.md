# OpenAI Setup

Used for: job extraction, company research, email discovery, opportunity
scoring, email personalization, and reply analysis — all via structured
outputs (`response_format: json_schema`), never free-form JSON parsing
(`backend/app/integrations/openai_client.py`).

## Get an API key
1. Go to https://platform.openai.com and sign in.
2. Left sidebar → **API keys** → **Create new secret key**.
3. Copy the key (starts with `sk-...`) into `OPENAI_API_KEY` in `.env`.
4. Set `OPENAI_MODEL` (default `gpt-4o-mini`) — any model that supports
   `response_format: json_schema` with `strict: true` works.

## Behavior when not configured
If `OPENAI_API_KEY` is empty, every agent call in
`backend/app/integrations/openai_client.py::structured_completion` returns
`None`. Callers never fabricate a result in that case:
- Job extraction: the job is skipped (not created) rather than guessed.
- Company research / email discovery: fields stay blank/low-confidence.
- Opportunity analysis: falls back to `MANUAL_REVIEW` / score 0.
- Email generation: falls back to a deterministic, fact-only template
  (`backend/app/agents/email_generation.py`) so outreach can still be
  drafted, just without AI-personalized language.
- Reply analysis: reply is stored with `reply_type=UNKNOWN` for manual
  review, never a fabricated classification (except unsubscribe detection,
  which is keyword-based and always active regardless of OpenAI).

## Cost control
- `gpt-4o-mini` is intentionally the default — cheap enough for per-job/
  per-company/per-reply calls at typical outreach volumes.
- Each agent call is a single request with a small, focused prompt — no
  chained multi-turn agent loops.
