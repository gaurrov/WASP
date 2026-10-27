import pytest

from app.config import get_settings
from app.demo import ops, scenario


def test_stages_cover_the_story_in_order():
    assert scenario.STAGES == [
        "draft",
        "submitted",
        "clarification",
        "resubmitted",
        "approved",
        "renewed",
    ]
    assert all(callable(getattr(scenario.Demo, s)) for s in scenario.STAGES)


def test_destructive_demo_commands_refuse_outside_dev(monkeypatch):
    monkeypatch.setattr(get_settings(), "env", "production")
    with pytest.raises(SystemExit):
        ops.reset()
    with pytest.raises(ValueError):
        scenario.run(until="nope")
