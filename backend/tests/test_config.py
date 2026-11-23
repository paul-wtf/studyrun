from studyrun.config import Settings


def test_settings_defaults():
    s = Settings()
    assert s.daily_ai_cap_usd == 0.50
    assert s.timezone == "Europe/Berlin"
    assert s.run_review_cap == 8
    assert s.model_grade == "claude-opus-5-5"
    assert s.model_verify == "claude-sonnet-5-5"
