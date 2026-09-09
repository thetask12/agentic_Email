from __future__ import annotations
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    job_title: str
    state: str | None = None
    city: str | None = None
    date_filter: str = "last_30_days"
    experience: str | None = None
    sources: list[str] = Field(default_factory=lambda: [
        "naukri", "indeed", "linkedin", "apna", "foundit", "google_search",
    ])
    result_limit: int = 10


class LeadPatchRequest(BaseModel):
    status: str | None = None
    next_action: str | None = None
    next_action_date: str | None = None
    owner: str | None = None
    priority: str | None = None


class NoteRequest(BaseModel):
    note: str
    created_by: str = "user"


class EmailRejectRequest(BaseModel):
    reason: str | None = None


class EmailEditRequest(BaseModel):
    recipient_email: str | None = None
    sender_email: str | None = None
    subject: str | None = None
    plain_text_body: str | None = None
    html_body: str | None = None


class QueueRequest(BaseModel):
    scheduled_at: str | None = None
    priority: str = "NORMAL"


class FollowUpCreateRequest(BaseModel):
    lead_id: str
    original_email_id: str = ""
    sequence_number: int
    subject: str
    body: str
    html_body: str = ""
    scheduled_at: str  # user-supplied — required, never auto-picked
    template_id: str = ""
    notes: str = ""


class FollowUpPatchRequest(BaseModel):
    subject: str | None = None
    body: str | None = None
    scheduled_at: str | None = None
    notes: str | None = None


class TemplateCreateRequest(BaseModel):
    name: str
    category: str = "INITIAL"
    subject: str
    plain_text_body: str
    html_body: str = ""
    is_active: bool = True
    is_default: bool = False


class TemplateUpdateRequest(BaseModel):
    name: str | None = None
    subject: str | None = None
    plain_text_body: str | None = None
    html_body: str | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class ManualEmailRequest(BaseModel):
    lead_id: str
    subject: str
    plain_text_body: str
    html_body: str = ""
    scheduled_at: str | None = None


class ReplyWebhookRequest(BaseModel):
    lead_id: str = ""
    company_id: str = ""
    email_id: str = ""
    thread_id: str = ""
    message_id: str
    in_reply_to: str = ""
    from_email: str
    from_name: str = ""
    to_email: str = ""
    subject: str = ""
    body_text: str = ""
    body_html: str = ""
    received_at: str = ""


class SettingsPatchRequest(BaseModel):
    values: dict[str, str]
