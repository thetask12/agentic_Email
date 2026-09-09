"""Seeds default EMAIL_TEMPLATES, FOLLOW_UP_TEMPLATES and SETTINGS rows on
startup if they don't already exist. Idempotent — safe to call every boot."""
import logging

from app.repositories.repositories import (
    email_template_repo, follow_up_template_repo, settings_repo, source_status_repo,
)
from app.models.enums import TemplateCategory, JobSource
from app.sources.source_manager import DISPLAY_NAMES
from app.prompts.email_master_template import (
    MASTER_SUBJECT, MASTER_PLAIN_TEMPLATE, MASTER_HTML_TEMPLATE,
    DEFAULT_FOLLOW_UP_1_SUBJECT, DEFAULT_FOLLOW_UP_1_BODY,
    DEFAULT_FOLLOW_UP_FINAL_SUBJECT, DEFAULT_FOLLOW_UP_FINAL_BODY,
)
from app.utils.ids import new_id

logger = logging.getLogger("bootstrap")


async def seed_defaults() -> None:
    try:
        templates = await email_template_repo.list_all()
        default_row = next((t for t in templates if str(t.get("is_default", "")).strip().lower() in ("true", "1")), None)
        if default_row is None:
            await email_template_repo.create({
                "template_id": new_id("template"),
                "name": "MIS Job — Business Automation Outreach",
                "category": TemplateCategory.INITIAL.value,
                "subject": MASTER_SUBJECT,
                "plain_text_body": MASTER_PLAIN_TEMPLATE,
                "html_body": MASTER_HTML_TEMPLATE,
                "is_active": True,
                "is_default": True,
            })
        else:
            # Keep the deployed default template's content in sync with the
            # code (email_master_template.py). Without this, a content
            # change here would only apply to spreadsheets that don't
            # already have a default row - every already-deployed sheet
            # would keep sending whatever text was seeded on its very first
            # boot forever.
            await email_template_repo.update(default_row["template_id"], {
                "subject": MASTER_SUBJECT,
                "plain_text_body": MASTER_PLAIN_TEMPLATE,
                "html_body": MASTER_HTML_TEMPLATE,
            })

        fu_templates = await follow_up_template_repo.list_all()
        if not fu_templates:
            await follow_up_template_repo.create({
                "template_id": new_id("template"), "name": "MIS Follow-up #1",
                "sequence_number": 1, "subject": DEFAULT_FOLLOW_UP_1_SUBJECT,
                "body": DEFAULT_FOLLOW_UP_1_BODY, "is_active": True,
            })
            await follow_up_template_repo.create({
                "template_id": new_id("template"), "name": "Final Follow-up",
                "sequence_number": 4, "subject": DEFAULT_FOLLOW_UP_FINAL_SUBJECT,
                "body": DEFAULT_FOLLOW_UP_FINAL_BODY, "is_active": True,
            })

        existing_settings = await settings_repo.list_all()
        keys = {s.get("key") for s in existing_settings}
        defaults = {
            "AUTO_SEND": "false",
            "AUTO_REPLY": "false",
            "AUTO_FOLLOWUP_AUTOMATION": "false",
        }
        for k, v in defaults.items():
            if k not in keys:
                await settings_repo.create({"key": k, "value": v, "description": ""})

        existing_sources = await source_status_repo.list_all()
        source_keys = {s.get("source") for s in existing_sources}
        for src in JobSource:
            if src.value not in source_keys:
                await source_status_repo.create({
                    "source": src.value, "display_name": DISPLAY_NAMES.get(src, src.value),
                    "enabled": True, "last_status": "", "last_checked_at": "", "notes": "Not yet run",
                })
    except Exception as exc:  # pragma: no cover - depends on Sheets availability
        logger.warning("Bootstrap seeding skipped/partial: %s", exc)
