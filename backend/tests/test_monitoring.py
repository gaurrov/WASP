from datetime import UTC, date, datetime, timedelta

import pytest

from app import synthetic
from app.config import get_settings
from app.models.enums import UserRole
from tests.conftest import auth_headers
from tests.test_applications import upload
from tests.test_workflow import case, get, post  # noqa: F401  (case is a fixture)

TODAY = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)


@pytest.fixture
def admin(make_user):
    return make_user(UserRole.ADMIN)


def scan(client, admin, days_from_now: int = 0) -> dict:
    as_of = (TODAY + timedelta(days=days_from_now)).isoformat()
    res = post(client, admin, "monitoring/scan", {"as_of": as_of})
    assert res.status_code == 200, res.text
    return res.json()


def alerts(client, user, **params) -> list[dict]:
    res = client.get("/api/alerts", params=params, headers=auth_headers(user))
    assert res.status_code == 200, res.text
    return res.json()


def expiry_alert(client, user) -> dict:
    found = [
        a for a in alerts(client, user, status="all") if a["alert_type"] == "certificate_expiry"
    ]
    assert len(found) == 1, found
    return found[0]


def test_expiring_certificate_raises_one_deduplicated_alert(client, case, admin):  # noqa: F811
    institution, _, app_id = case
    alert = expiry_alert(client, institution)  # raised by the event-driven scan on submit
    assert alert["severity"] == "high"
    assert alert["status"] == "active"
    assert alert["details"]["days_remaining"] == 30
    assert alert["application_id"] == app_id

    first, second = scan(client, admin), scan(client, admin)
    assert first["raised"] == second["raised"] == 0  # same obligation → same alert
    assert expiry_alert(client, institution)["id"] == alert["id"]

    summary = get(client, institution, "alerts/summary")
    assert summary["open"] >= 1 and summary["high"] >= 1


def test_time_passing_makes_alerts_overdue_then_escalated(client, case, admin):  # noqa: F811
    institution, reviewer, app_id = case
    scan(client, admin, days_from_now=31)  # expired yesterday
    alert = expiry_alert(client, institution)
    assert alert["severity"] == "critical"
    assert alert["status"] == "overdue"
    assert "expired" in alert["title"]

    result = scan(client, admin, days_from_now=40)  # > 7 days past due
    assert result["escalated"] >= 1
    assert expiry_alert(client, institution)["status"] == "escalated"
    events = [
        e["event_type"] for e in get(client, reviewer, f"applications/{app_id}/workflow")["events"]
    ]
    assert {"alert_raised", "alert_overdue", "alert_escalated"} <= set(events)


def test_renewed_certificate_resolves_alert_automatically(client, case):  # noqa: F811
    institution, _, app_id = case
    alert = expiry_alert(client, institution)
    # The application is under review, but replacing the alerted document is allowed.
    renewed, _ = synthetic.fire_noc(date.today() + timedelta(days=700))
    res = upload(
        client,
        institution,
        app_id,
        renewed,
        doc_type="fire_noc",
        filename="fire_noc_2028.pdf",
        replaces_id=alert["details"]["document_id"],
    )
    assert res.status_code == 201, res.text

    resolved = expiry_alert(client, institution)
    assert resolved["status"] == "resolved"
    assert "automatically" in resolved["resolution_note"]
    # Other documents still can't be changed while under review.
    other = upload(client, institution, app_id, renewed, doc_type="land_document")
    assert other.status_code == 409


def test_manual_resolution_sticks_unless_things_get_worse(client, case, admin):  # noqa: F811
    institution, reviewer, _ = case
    alert = expiry_alert(client, institution)
    url = f"alerts/{alert['id']}/resolve"
    assert post(client, institution, url, {"note": "We renewed it"}).status_code == 403
    assert (
        post(client, reviewer, url, {"note": "Renewal verified with fire dept."}).status_code == 200
    )

    scan(client, admin)  # same situation: stays resolved
    assert expiry_alert(client, institution)["status"] == "resolved"
    scan(client, admin, days_from_now=31)  # now expired: worse, so it comes back
    reopened = expiry_alert(client, institution)
    assert reopened["status"] in ("reopened", "overdue")
    assert reopened["severity"] == "critical"


def test_clarification_deadline(client, case, admin):  # noqa: F811
    institution, reviewer, app_id = case
    finding = next(
        f for f in get(client, reviewer, f"applications/{app_id}/findings") if f["status"] == "fail"
    )
    ask = {"message": "Upload the building certificate.", "finding_ids": [finding["id"]]}
    post(client, reviewer, f"applications/{app_id}/clarification", ask)

    task = next(
        a for a in alerts(client, institution) if a["alert_type"] == "clarification_response"
    )
    assert task["severity"] == "low"
    days = get_settings().clarification_response_days
    scan(client, admin, days_from_now=days + 1)
    task = next(
        a for a in alerts(client, institution) if a["alert_type"] == "clarification_response"
    )
    assert task["status"] == "overdue"
    assert task["severity"] == "high"

    post(client, institution, f"applications/{app_id}/submit")  # resubmission clears it
    scan(client, admin, days_from_now=days + 1)
    assert not [
        a for a in alerts(client, institution) if a["alert_type"] == "clarification_response"
    ]


def test_review_sla_alerts_reviewers_only(client, case, admin):  # noqa: F811
    institution, reviewer, app_id = case
    scan(client, admin, days_from_now=get_settings().review_sla_days + 1)
    sla = [a for a in alerts(client, reviewer) if a["alert_type"] == "review_sla"]
    assert len(sla) == 1
    assert sla[0]["audience"] == "reviewer"
    assert not [a for a in alerts(client, institution) if a["alert_type"] == "review_sla"]

    post(
        client,
        reviewer,
        f"applications/{app_id}/decision",
        {"decision": "reject", "reason": "Faculty strength below norm."},
    )
    scan(client, admin, days_from_now=get_settings().review_sla_days + 1)
    assert not [a for a in alerts(client, reviewer) if a["alert_type"] == "review_sla"]


def test_alert_visibility_and_acknowledgement(client, case, make_user):  # noqa: F811
    institution, _, _ = case
    alert = expiry_alert(client, institution)
    other = make_user(UserRole.INSTITUTION)
    assert alerts(client, other, status="all") == []
    assert post(client, other, f"alerts/{alert['id']}/acknowledge").status_code == 404

    assert post(client, institution, f"alerts/{alert['id']}/acknowledge").status_code == 200
    assert expiry_alert(client, institution)["status"] == "acknowledged"


def test_simulated_time_is_dev_only(client, admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "env", "production")
    res = post(client, admin, "monitoring/scan", {"as_of": TODAY.isoformat()})
    assert res.status_code == 403
    assert post(client, admin, "monitoring/scan", {}).status_code == 200
