"""ReplyAnalysis agent (System.txt sections 27, 59-60, 84).

Classifies an inbound reply and suggests next steps. Unsubscribe/stop
requests are detected deterministically first (keyword match) since that
must reliably trigger suppression regardless of AI availability.
"""
import re

from app.integrations.openai_client import structured_completion

SCHEMA = {
    "type": "object",
    "properties": {
        "reply_type": {
            "type": "string",
            "enum": ["INTERESTED", "REQUEST_FOR_DETAILS", "MEETING_REQUEST", "POSITIVE",
                     "NEUTRAL", "NOT_INTERESTED", "ASK_LATER", "OUT_OF_OFFICE", "BOUNCE",
                     "UNSUBSCRIBE", "UNKNOWN"],
        },
        "sentiment": {"type": "string", "enum": ["POSITIVE", "NEUTRAL", "NEGATIVE"]},
        "summary": {"type": "string"},
        "lead_status": {"type": "string"},
        "recommended_next_action": {"type": "string"},
        "suggested_response": {"type": "string"},
        "priority": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "URGENT"]},
    },
    "required": ["reply_type", "sentiment", "summary", "lead_status", "recommended_next_action",
                 "suggested_response", "priority"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You analyze an inbound email reply to a Botivate cold outreach email about
business automation (AutoRocket). Given the original outreach context and
the reply body, classify it.

reply_type: choose the single best-fitting category.
sentiment: overall tone toward Botivate's outreach.
summary: one or two sentence factual summary of what the reply says — do
not add opinions or claims not present in the text.
lead_status: one of NEW, QUALIFIED, CONTACTED, REPLIED, IN_CONVERSATION,
MEETING_REQUESTED, INTERESTED, NOT_INTERESTED, SUPPRESSED, NO_RESPONSE —
pick the status that best reflects this reply.
recommended_next_action: one of CALL, SEND_PROFILE, SEND_PRICING,
SCHEDULE_MEETING, FOLLOW_UP, WAIT_FOR_REPLY, SEND_DEMO, SEND_PROPOSAL,
NO_ACTION, CLOSE.
suggested_response: a short, polite draft reply Botivate's team could send
(the user reviews/edits before ever sending it — never claim it was sent).
priority: urgency of following up, based on intent (meeting requests and
explicit interest are HIGH/URGENT)."""

UNSUBSCRIBE_PATTERNS = [
    r"\bunsubscribe\b", r"\bremove me\b", r"\bdo not contact\b", r"\bstop emailing\b",
    r"\bnot interested in further emails\b", r"\bplease remove\b", r"\btake me off\b",
]


def detect_unsubscribe(body_text: str) -> bool:
    text = (body_text or "").lower()
    return any(re.search(p, text) for p in UNSUBSCRIBE_PATTERNS)


def analyze_reply(*, original_subject: str, original_body_excerpt: str, reply_body: str) -> dict:
    if detect_unsubscribe(reply_body):
        return {
            "reply_type": "UNSUBSCRIBE",
            "sentiment": "NEGATIVE",
            "summary": "Recipient asked to stop receiving emails / unsubscribe.",
            "lead_status": "SUPPRESSED",
            "recommended_next_action": "CLOSE",
            "suggested_response": "",
            "priority": "HIGH",
        }

    user_prompt = (
        f"Original outreach subject: {original_subject}\n"
        f"Original outreach excerpt: {original_body_excerpt[:800]}\n\n"
        f"Reply body:\n{reply_body}\n\nAnalyze this reply."
    )
    result = structured_completion(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=SCHEMA,
        schema_name="reply_analysis",
    )
    if result is None:
        # OpenAI unavailable: leave as UNKNOWN/UNANALYZED rather than fabricate intent.
        return {
            "reply_type": "UNKNOWN",
            "sentiment": "NEUTRAL",
            "summary": "AI analysis unavailable — review manually.",
            "lead_status": "REPLIED",
            "recommended_next_action": "WAIT_FOR_REPLY",
            "suggested_response": "",
            "priority": "MEDIUM",
        }
    return result
