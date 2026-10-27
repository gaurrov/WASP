import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.models.enums import FindingStatus, UserRole
from app.rules.context import Result
from app.rules.engine import guard_low_confidence
from app.rules.evaluators import normalize_name
from tests.conftest import auth_headers
from tests.fixtures import demo_documents
from tests.test_applications import NEW_APP, upload


def fact(confidence: float):
    return SimpleNamespace(id=uuid.uuid4(), confidence=confidence)


def test_normalize_name():
    assert normalize_name("Dr. S. Priya") == "s priya"
    assert normalize_name("Mr. T.  Suresh") == "t suresh"


def test_low_confidence_evidence_downgrades_to_review():
    result = guard_low_confidence(Result(FindingStatus.PASS, "ok.", [fact(0.5), fact(0.99)]), 0.8)
    assert result.status == FindingStatus.NEEDS_REVIEW
    assert result.details["original_status"] == "pass"


def test_only_decisive_evidence_can_downgrade():
    shaky, solid = fact(0.5), fact(0.99)
    result = Result(FindingStatus.FAIL, "bad.", [shaky, solid], decisive=[solid])
    assert guard_low_confidence(result, 0.8).status == FindingStatus.FAIL


@pytest.fixture
def evaluated(client, make_user):
    """Upload the demo bundle, submit, and return (application, findings by rule code)."""
    user = make_user(UserRole.INSTITUTION)
    app = client.post("/api/applications", json=NEW_APP, headers=auth_headers(user)).json()
    for filename, doc_type, pdf in demo_documents(date.today()):
        res = upload(client, user, app["id"], pdf, doc_type=doc_type, filename=filename)
        assert res.status_code == 201, res.text
    submitted = client.post(f"/api/applications/{app['id']}/submit", headers=auth_headers(user))
    findings = client.get(f"/api/applications/{app['id']}/findings", headers=auth_headers(user))
    assert findings.status_code == 200
    return user, submitted.json(), {f["rule"]["code"]: f for f in findings.json()}


def test_demo_application_findings(evaluated):
    _, app, findings = evaluated
    assert app["status"] == "needs_review"

    req = findings["DOC-REQ-001"]
    assert req["status"] == "fail"
    assert "Building completion certificate" in req["details"]["missing"]

    qual = findings["FAC-QUAL-001"]
    assert qual["status"] == "fail"
    assert len(qual["details"]["without_certificate"]) == 3
    assert {"listed": "Dr. S. Priya", "certificate": "S. Priyaa"} in [
        {k: m[k] for k in ("listed", "certificate")} for m in qual["details"]["name_mismatches"]
    ]
    assert all(e["filename"] for e in qual["evidence"])

    assert findings["FAC-DECL-001"]["status"] == "pass"
    assert findings["FAC-CADRE-001"]["status"] == "pass"

    ratio = findings["FAC-RATIO-001"]
    assert ratio["status"] == "fail"
    assert ratio["provisional"] is True  # rule not yet verified against the handbook
    assert ratio["details"]["required_faculty"] == 24

    fire = findings["FIRE-NOC-001"]
    assert fire["status"] == "pass"
    assert fire["details"]["expiring_soon"] is True
    assert fire["details"]["valid_until"] == (date.today() + timedelta(days=30)).isoformat()
    assert fire["evidence"][0]["field_name"] == "valid_until"


def test_reevaluation_replaces_findings(client, make_user, evaluated):
    user, app, findings = evaluated
    reviewer = make_user(UserRole.REVIEWER)
    url = f"/api/applications/{app['id']}"
    assert client.post(f"{url}/evaluate", headers=auth_headers(user)).status_code == 403
    assert client.post(f"{url}/evaluate", headers=auth_headers(reviewer)).status_code == 202

    again = client.get(f"{url}/findings", headers=auth_headers(reviewer)).json()
    assert len(again) == len(findings)
    assert not {f["id"] for f in again} & {f["id"] for f in findings.values()}


def test_findings_respect_tenant_isolation(client, make_user, evaluated):
    _, app, _ = evaluated
    other = auth_headers(make_user(UserRole.INSTITUTION))
    assert client.get(f"/api/applications/{app['id']}/findings", headers=other).status_code == 404
