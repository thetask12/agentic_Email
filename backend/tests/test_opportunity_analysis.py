from app.agents.opportunity_analysis import compute_lead_score, compute_priority


def test_lead_score_rewards_high_opportunity_and_data_quality():
    score = compute_lead_score(
        opportunity_score=90, has_email=True, email_confidence=0.9,
        website_confidence=0.9, extraction_confidence=0.9,
    )
    assert score > 80


def test_lead_score_penalizes_missing_email():
    with_email = compute_lead_score(80, True, 0.8, 0.8, 0.8)
    without_email = compute_lead_score(80, False, 0.0, 0.8, 0.8)
    assert without_email < with_email


def test_lead_score_bounded_0_100():
    assert compute_lead_score(100, True, 1.0, 1.0, 1.0) <= 100
    assert compute_lead_score(0, False, 0.0, 0.0, 0.0) >= 0


def test_priority_thresholds():
    assert compute_priority(90, 90) == "URGENT"
    assert compute_priority(65, 65) == "HIGH"
    assert compute_priority(40, 40) == "MEDIUM"
    assert compute_priority(10, 10) == "LOW"
