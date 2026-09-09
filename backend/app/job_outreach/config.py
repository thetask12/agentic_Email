"""
Settings for the Job Outreach module — a completely separate personal
job-application system (find companies hiring for AI/Agentic-AI roles,
discover an official contact email, send ONE cold-application email with a
resume attached). Deliberately its OWN pydantic-settings class (not an
extension of app.config.settings.Settings) so:
  - it never collides with the existing system's env var names, and
  - the existing Settings/get_settings() singleton is never touched.

Candidate contact details (name/phone/linkedin/github/resume-file-id) are
public resume information, not secrets — real defaults are fine here and in
.env.example. The Sheet ID and service-account credentials ARE sensitive and
must stay blank in .env.example / be supplied via real environment
variables only.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class JobOutreachSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Google Sheets (this module's OWN sheet + service account — never reuse
    # the main system's GOOGLE_SHEETS_ID / GOOGLE_SERVICE_ACCOUNT_*).
    job_outreach_sheet_id: str = ""
    job_outreach_service_account_email: str = ""
    job_outreach_service_account_private_key: str = ""

    # OpenAI + Tavily are shared integrations (same API keys as the main
    # system work fine here — these are generic AI/search providers, not
    # Botivate-specific config), read via app.config.settings.get_settings()
    # in the modules that need them rather than duplicated here.

    # Sender identity — a personal Gmail account, NOT a company inbox. Apps
    # Script triggers for this module's project must be authorized under
    # this exact account (GmailApp always sends as whichever account
    # installed the triggers, regardless of this config value — see the
    # analogous gotcha documented in root CLAUDE.md for the main system).
    job_outreach_sender_email: str = "prabhatkumarsictc12@gmail.com"

    # Resume PDF, read by Apps Script via DriveApp.getFileById(...).getBlob()
    # and attached to every outgoing application email. Drive file id
    # extracted from https://drive.google.com/file/d/<id>/view.
    job_outreach_resume_drive_file_id: str = "1CijF9kbtlaTuay4iVsguC12Dnkc9lCc-"

    # Candidate identity used in generated email bodies/signatures. No
    # employer/company name is ever disclosed in the email body (see
    # docs/job-outreach-schema.md "Email content rules").
    job_outreach_candidate_name: str = "Prabhat Kumar Singh"
    job_outreach_candidate_phone: str = "+91 9801675811"
    job_outreach_candidate_linkedin: str = "https://www.linkedin.com/in/prabhat-singh-3a4ab3303/"
    job_outreach_candidate_github: str = "https://github.com/Prabhat9801"

    # Safety — mirrors the main system's EMAIL_TEST_MODE rule: while true,
    # every outgoing application email is redirected to
    # JOB_OUTREACH_TEST_EMAIL and every EMAIL_QUEUE/EMAIL_EVENTS row this
    # module writes records test_mode=true. Defaults true/safe.
    job_outreach_email_test_mode: bool = True
    job_outreach_test_email: str = ""

    # One shared daily cap across every (role, city) search cycle — see
    # scheduler.py / SETTINGS tab keys daily_email_cap / emails_sent_today /
    # emails_sent_date (docs/job-outreach-schema.md).
    job_outreach_daily_email_cap: int = 100

    @property
    def sheets_configured(self) -> bool:
        return bool(
            self.job_outreach_sheet_id
            and self.job_outreach_service_account_email
            and self.job_outreach_service_account_private_key
        )


@lru_cache
def get_job_outreach_settings() -> JobOutreachSettings:
    return JobOutreachSettings()
