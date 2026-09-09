"""
Enums mirrored 1:1 from docs/job-outreach-schema.md. Keep in sync.
"""
from enum import Enum


class EmailType(str, Enum):
    GENERIC = "GENERIC"
    FOUNDER = "FOUNDER"
    HR = "HR"
    DEPARTMENT = "DEPARTMENT"
    UNKNOWN = "UNKNOWN"


# Only these two email types are ever accepted as an outreach recipient —
# same official-email-only filter rule as the main system. Anything else
# (HR/DEPARTMENT/UNKNOWN) means the whole company is dropped, same as "no
# email found".
ACCEPTED_EMAIL_TYPES = (EmailType.GENERIC.value, EmailType.FOUNDER.value)


class ResearchStatus(str, Enum):
    PENDING = "PENDING"
    RESEARCHING = "RESEARCHING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NOT_FOUND = "NOT_FOUND"


class QueueStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    RETRY = "RETRY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EmailEventType(str, Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"
    REPLIED = "REPLIED"


class SuppressionReason(str, Enum):
    ALREADY_APPLIED = "ALREADY_APPLIED"
    INVALID_EMAIL = "INVALID_EMAIL"
    MANUAL = "MANUAL"


class SearchRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ---- Fixed role/location lists (docs/job-outreach-schema.md) ----

ROLES = [
    "AI Engineer",
    "Agentic AI Developer",
    "AI Developer",
]

INDIA_LOCATIONS = [
    "Bangalore", "Hyderabad", "Pune", "Chennai", "Gurugram", "Noida",
    "Delhi", "New Delhi", "Mumbai", "Raipur", "Surat", "Ahmedabad", "Jaipur",
    "Remote (India)",
]

# Only postings explicitly open to remote/India candidates are accepted from
# these — see search.py's query construction and qualification filter.
REMOTE_INTERNATIONAL_LOCATIONS = [
    "Singapore", "UAE", "USA", "UK",
]

ALL_LOCATIONS = INDIA_LOCATIONS + REMOTE_INTERNATIONAL_LOCATIONS
