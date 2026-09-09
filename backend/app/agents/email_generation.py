"""EmailGeneration agent (System.txt sections 15-16, 40).

generate_initial_email() sends the fixed Botivate/AutoRocket pitch supplied
verbatim by the user (see email_master_template.py) identically to every
company — no AI personalization line is inserted, per explicit instruction.
Only the sender name and the two website links are substituted.
"""
from app.prompts.email_master_template import (
    MASTER_SUBJECT, MASTER_PLAIN_TEMPLATE, MASTER_HTML_TEMPLATE,
    DEFAULT_FOLLOW_UP_1_SUBJECT, DEFAULT_FOLLOW_UP_1_BODY,
)
from app.integrations.openai_client import structured_completion

FOLLOWUP_SCHEMA = {
    "type": "object",
    "properties": {
        "body": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["body", "confidence"],
    "additionalProperties": False,
}

FOLLOWUP_SYSTEM_PROMPT = """You write a short, polite follow-up email (shorter than the original cold
email, 3-5 sentences max) referencing that a previous email was already
sent about a specific job/automation opportunity. Use only the verified
facts provided. Do not repeat the entire pitch — just a brief nudge. Do not
fabricate any prior conversation content beyond what is given."""


def _render(template: str, **kwargs) -> str:
    out = template
    for k, v in kwargs.items():
        out = out.replace("{{" + k + "}}", v or "")
    return out


def generate_initial_email(*, company_name: str, job_title: str, city: str | None,
                            contact_name: str | None, automation_signals: list[str],
                            pain_points: list[str], sender_name: str, botivate_website: str,
                            autorocket_website: str = "") -> dict:
    render_kwargs = dict(
        sender_name=sender_name,
        botivate_website=botivate_website,
        autorocket_website=autorocket_website or botivate_website,
        # Left as a literal marker div for EmailSender.gs to string-replace
        # with an <img cid="..."> tag right before sending — the actual
        # image blob only exists in Apps Script (fetched from Drive), so
        # the backend can't render the final <img> tag itself. Placing the
        # marker HERE (inside the template, between the AutoRocket and
        # Botivate sections) is what controls the banner's position in the
        # email; EmailSender.gs never decides placement, only substitutes.
        autorocket_banner='<div id="autorocket-banner-placeholder"></div>',
        # Same pattern for the Botivate profile image — inline in the body,
        # further down the pitch (no longer an attachment).
        botivate_profile_image='<div id="botivate-profile-placeholder"></div>',
        # Same pattern again for the signature poster — this image REPLACES
        # the text signature block ("Regards, Satyendra Kumar Tandan...")
        # entirely; there is no separate text signature anymore, per
        # explicit user instruction. It is the last thing in the email.
        signature_poster='<div id="signature-poster-placeholder"></div>',
    )
    plain_body = _render(MASTER_PLAIN_TEMPLATE, **render_kwargs)
    html_body = _render(MASTER_HTML_TEMPLATE, **render_kwargs)
    return {
        "subject": MASTER_SUBJECT,
        "plain_text_body": plain_body,
        "html_body": html_body,
        "personalization_points": [],
        "facts_used": ["fixed_template_sent_verbatim"],
        "confidence": 1.0,
    }


def generate_follow_up_email(*, company_name: str, job_title: str, contact_name: str | None,
                              sequence_number: int, previous_subject: str, sender_name: str) -> dict:
    user_prompt = (
        f"Company: {company_name}\nJob title: {job_title}\n"
        f"This is follow-up #{sequence_number}. Previous email subject: {previous_subject}\n\n"
        "Write the follow-up body."
    )
    result = structured_completion(
        system_prompt=FOLLOWUP_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=FOLLOWUP_SCHEMA,
        schema_name="follow_up_generation",
    )
    contact_name_or_team = contact_name or "there"
    if result is None:
        body = _render(DEFAULT_FOLLOW_UP_1_BODY, contact_name_or_team=contact_name_or_team,
                        company_name=company_name, job_title=job_title, sender_name=sender_name)
        confidence = 0.4
    else:
        body = result["body"]
        confidence = result["confidence"]
    subject = f"Re: {previous_subject}" if not previous_subject.startswith("Re:") else previous_subject
    return {"subject": subject, "body": body, "confidence": confidence}
