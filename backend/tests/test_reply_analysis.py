from app.agents.reply_analysis import detect_unsubscribe, analyze_reply


def test_detect_unsubscribe_keywords():
    assert detect_unsubscribe("Please unsubscribe me from this list") is True
    assert detect_unsubscribe("Do not contact me again") is True
    assert detect_unsubscribe("stop emailing us please") is True
    assert detect_unsubscribe("Thanks, please share your pricing") is False


def test_analyze_reply_unsubscribe_short_circuits_without_openai():
    # OPENAI_API_KEY is unset in test env (conftest.py) — analyze_reply must
    # still deterministically classify an unsubscribe request without
    # calling OpenAI at all, and must never fabricate an intent otherwise.
    result = analyze_reply(
        original_subject="A Complete Business Automation Team Beyond a Single MIS Hire",
        original_body_excerpt="Hi there, ...",
        reply_body="Please remove me from your mailing list, not interested in further emails.",
    )
    assert result["reply_type"] == "UNSUBSCRIBE"
    assert result["lead_status"] == "SUPPRESSED"


def test_analyze_reply_falls_back_to_unknown_without_openai():
    result = analyze_reply(
        original_subject="A Complete Business Automation Team Beyond a Single MIS Hire",
        original_body_excerpt="Hi there, ...",
        reply_body="Thanks, can you tell me more?",
    )
    # No OpenAI configured -> must not fabricate a specific classification.
    assert result["reply_type"] == "UNKNOWN"
    assert result["lead_status"] == "REPLIED"
