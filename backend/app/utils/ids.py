"""UUID generation with entity-type prefixes. Never use sheet row numbers as IDs."""
import uuid

_PREFIXES = {
    "job": "job",
    "company": "cmp",
    "contact": "ctc",
    "lead": "lead",
    "template": "tpl",
    "email": "eml",
    "queue": "q",
    "event": "evt",
    "followup": "fu",
    "reply": "rpl",
    "conversation": "conv",
    "campaign": "camp",
    "suppression": "sup",
    "activity": "act",
    "note": "note",
    "run": "run",
}


def new_id(entity: str) -> str:
    prefix = _PREFIXES.get(entity, entity[:4])
    return f"{prefix}_{uuid.uuid4().hex[:20]}"
