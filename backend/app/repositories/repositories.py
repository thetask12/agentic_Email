"""One repository class per Google Sheet tab. Headers must match docs/sheet-schema.md exactly."""
from app.repositories.base import BaseRepository


class SearchRunRepository(BaseRepository):
    SHEET_NAME = "SEARCH_RUNS"
    ID_FIELD = "run_id"
    HEADERS = ["run_id", "query", "job_title", "state", "city", "sources", "date_filter",
               "experience", "result_limit", "results", "qualified", "companies", "emails",
               "leads", "status", "started_at", "completed_at", "error_message"]


class JobRepository(BaseRepository):
    SHEET_NAME = "JOBS"
    ID_FIELD = "job_id"
    HEADERS = ["job_id", "source", "source_job_id", "job_title", "company_id", "company_name",
               "location", "city", "state", "country", "description", "experience", "salary",
               "employment_type", "posted_date", "skills", "qualification", "job_url",
               "application_url", "source_url", "extraction_confidence", "run_id",
               "is_qualified", "created_at", "updated_at"]


class CompanyRepository(BaseRepository):
    SHEET_NAME = "COMPANIES"
    ID_FIELD = "company_id"
    HEADERS = ["company_id", "company_name", "normalized_name", "official_website", "domain",
               "industry", "city", "state", "country", "phone", "linkedin_url",
               "company_description", "website_confidence", "research_status", "created_at",
               "updated_at"]


class ContactRepository(BaseRepository):
    SHEET_NAME = "CONTACTS"
    ID_FIELD = "contact_id"
    HEADERS = ["contact_id", "company_id", "contact_name", "designation", "email", "email_type",
               "email_source_url", "email_confidence", "phone", "linkedin_url",
               "verification_status", "created_at", "updated_at"]


class LeadRepository(BaseRepository):
    SHEET_NAME = "LEADS"
    ID_FIELD = "lead_id"
    HEADERS = ["lead_id", "company_id", "job_id", "contact_id", "lead_score",
               "botivate_opportunity_score", "automation_signals", "pain_points",
               "recommended_solution", "priority", "status", "owner", "next_action",
               "next_action_date", "notes", "created_at", "updated_at", "last_activity_at"]


class EmailTemplateRepository(BaseRepository):
    SHEET_NAME = "EMAIL_TEMPLATES"
    ID_FIELD = "template_id"
    HEADERS = ["template_id", "name", "category", "subject", "plain_text_body", "html_body",
               "is_active", "is_default", "created_at", "updated_at"]


class EmailDraftRepository(BaseRepository):
    SHEET_NAME = "EMAIL_DRAFTS"
    ID_FIELD = "email_id"
    HEADERS = ["email_id", "lead_id", "company_id", "template_id", "recipient_email",
               "sender_email", "subject", "plain_text_body", "html_body",
               "personalization_points", "facts_used", "confidence", "status", "created_at",
               "updated_at"]


class EmailQueueRepository(BaseRepository):
    SHEET_NAME = "EMAIL_QUEUE"
    ID_FIELD = "queue_id"
    HEADERS = ["queue_id", "email_id", "lead_id", "recipient_email", "sender_email", "subject",
               "body", "html_body", "kind", "priority", "scheduled_at", "status", "attempts",
               "max_attempts", "last_attempt_at", "sent_at", "message_id", "thread_id",
               "error_message", "test_mode", "created_at", "updated_at"]


class EmailEventRepository(BaseRepository):
    SHEET_NAME = "EMAIL_EVENTS"
    ID_FIELD = "event_id"
    HEADERS = ["event_id", "email_id", "lead_id", "company_id", "event_type", "timestamp",
               "message_id", "provider", "metadata", "created_at"]


class FollowUpRepository(BaseRepository):
    SHEET_NAME = "FOLLOW_UPS"
    ID_FIELD = "follow_up_id"
    HEADERS = ["follow_up_id", "lead_id", "company_id", "original_email_id", "sequence_number",
               "template_id", "subject", "body", "html_body", "scheduled_at", "status",
               "sent_at", "message_id", "reply_received", "cancelled_at", "cancel_reason",
               "notes", "created_at", "updated_at"]


class FollowUpTemplateRepository(BaseRepository):
    SHEET_NAME = "FOLLOW_UP_TEMPLATES"
    ID_FIELD = "template_id"
    HEADERS = ["template_id", "name", "sequence_number", "subject", "body", "is_active",
               "created_at", "updated_at"]


class ReplyRepository(BaseRepository):
    SHEET_NAME = "REPLIES"
    ID_FIELD = "reply_id"
    HEADERS = ["reply_id", "lead_id", "company_id", "email_id", "thread_id", "message_id",
               "in_reply_to", "from_email", "from_name", "to_email", "subject", "body_text",
               "body_html", "received_at", "reply_type", "sentiment", "intent", "ai_summary",
               "requires_action", "action_type", "priority", "suggested_response", "created_at"]


class ConversationRepository(BaseRepository):
    SHEET_NAME = "CONVERSATIONS"
    ID_FIELD = "conversation_id"
    HEADERS = ["conversation_id", "lead_id", "company_id", "thread_id", "status",
               "last_message_at", "last_message_direction", "message_count", "created_at",
               "updated_at"]


class CampaignRepository(BaseRepository):
    SHEET_NAME = "CAMPAIGNS"
    ID_FIELD = "campaign_id"
    HEADERS = ["campaign_id", "name", "description", "job_title", "state", "city", "sources",
               "template_id", "status", "created_at", "updated_at"]


class SuppressionRepository(BaseRepository):
    SHEET_NAME = "SUPPRESSION_LIST"
    ID_FIELD = "suppression_id"
    HEADERS = ["suppression_id", "email", "company_id", "reason", "source", "created_at"]


class SourceStatusRepository(BaseRepository):
    SHEET_NAME = "SOURCE_STATUS"
    ID_FIELD = "source"
    HEADERS = ["source", "display_name", "enabled", "last_status", "last_checked_at", "notes"]


class ActivityLogRepository(BaseRepository):
    SHEET_NAME = "ACTIVITY_LOG"
    ID_FIELD = "activity_id"
    HEADERS = ["activity_id", "lead_id", "company_id", "activity_type", "description",
               "metadata", "created_at", "created_by"]


class LeadNoteRepository(BaseRepository):
    SHEET_NAME = "LEAD_NOTES"
    ID_FIELD = "note_id"
    HEADERS = ["note_id", "lead_id", "note", "created_by", "created_at"]


class SettingsRepository(BaseRepository):
    SHEET_NAME = "SETTINGS"
    ID_FIELD = "key"
    HEADERS = ["key", "value", "description", "updated_at"]


class ConfigRepository(BaseRepository):
    SHEET_NAME = "CONFIG"
    ID_FIELD = "key"
    HEADERS = ["key", "value", "description", "updated_at"]


# Singletons — cheap objects, one gspread worksheet handle each.
search_run_repo = SearchRunRepository()
job_repo = JobRepository()
company_repo = CompanyRepository()
contact_repo = ContactRepository()
lead_repo = LeadRepository()
email_template_repo = EmailTemplateRepository()
email_draft_repo = EmailDraftRepository()
email_queue_repo = EmailQueueRepository()
email_event_repo = EmailEventRepository()
follow_up_repo = FollowUpRepository()
follow_up_template_repo = FollowUpTemplateRepository()
reply_repo = ReplyRepository()
conversation_repo = ConversationRepository()
campaign_repo = CampaignRepository()
suppression_repo = SuppressionRepository()
source_status_repo = SourceStatusRepository()
activity_log_repo = ActivityLogRepository()
lead_note_repo = LeadNoteRepository()
settings_repo = SettingsRepository()
config_repo = ConfigRepository()
