import random
from datetime import date

import pytest

from app import synthetic
from app.models.enums import UserRole
from tests.conftest import auth_headers
from tests.fixtures import demo_documents
from tests.test_applications import NEW_APP, upload

APPROVE = {"decision": "approve", "reason": "Looks fine overall"}


@pytest.fixture
def case(client, make_user):
    """A submitted demo application: (institution user, reviewer, application id)."""
    institution = make_user(UserRole.INSTITUTION)
    reviewer = make_user(UserRole.REVIEWER)
    app = client.post("/api/applications", json=NEW_APP, headers=auth_headers(institution)).json()
    for filename, doc_type, pdf in demo_documents(date.today()):
        upload(client, institution, app["id"], pdf, doc_type=doc_type, filename=filename)
    client.post(f"/api/applications/{app['id']}/submit", headers=auth_headers(institution))
    return institution, reviewer, app["id"]


def get(client, user, path):
    res = client.get(f"/api/{path}", headers=auth_headers(user))
    assert res.status_code == 200, res.text
    return res.json()


def post(client, user, path, body=None):
    return client.post(f"/api/{path}", json=body, headers=auth_headers(user))


def findings_by_code(client, user, app_id):
    return {f["rule"]["code"]: f for f in get(client, user, f"applications/{app_id}/findings")}


def test_full_review_cycle_with_incremental_revalidation(client, case):
    institution, reviewer, app_id = case

    wf = get(client, reviewer, f"applications/{app_id}/workflow")
    assert wf["waiting_for"] == "reviewer"
    assert wf["round"] == 1
    assert len(wf["rechecked"]) == wf["total_rules"]  # first evaluation checks everything
    before = findings_by_code(client, reviewer, app_id)

    # Approval needs every open finding reviewed first.
    assert post(client, reviewer, f"applications/{app_id}/decision", APPROVE).status_code == 409

    ask = {
        "message": "Upload the building completion certificate and correct S. Priya's certificate.",
        "finding_ids": [before["DOC-REQ-001"]["id"], before["FAC-QUAL-001"]["id"]],
    }
    assert post(client, reviewer, f"applications/{app_id}/clarification", ask).status_code == 202
    wf = get(client, institution, f"applications/{app_id}/workflow")
    assert wf["waiting_for"] == "institution"
    assert wf["clarification"]["message"] == ask["message"]
    detail = get(client, institution, f"applications/{app_id}")
    assert detail["status"] == "clarification_requested"

    # The institution fixes the misspelled certificate and adds the missing document. Uploads
    # while waiting don't resume the case; only resubmission does.
    roster = synthetic.faculty_roster(random.Random(7))
    old_cert = next(d for d in detail["documents"] if d["filename"] == "certificate_02.pdf")
    fixed, _ = synthetic.qualification_certificate(roster[1], roster[1]["name"])
    res = upload(
        client,
        institution,
        app_id,
        fixed,
        doc_type="qualification_certificate",
        filename="certificate_02_v2.pdf",
        replaces_id=old_cert["id"],
    )
    assert res.status_code == 201
    building, _ = synthetic.building_certificate()
    upload(client, institution, app_id, building, doc_type="building_certificate")
    assert (
        get(client, institution, f"applications/{app_id}/workflow")["waiting_for"] == "institution"
    )

    resubmitted = post(client, institution, f"applications/{app_id}/submit").json()
    assert resubmitted["status"] == "needs_review"

    wf = get(client, reviewer, f"applications/{app_id}/workflow")
    assert wf["round"] == 2
    # Only rules that can depend on the changed documents were re-checked ...
    assert set(wf["rechecked"]) == {"DOC-REQ-001", "DOC-TYPE-001", "FAC-QUAL-001"}
    after = findings_by_code(client, reviewer, app_id)
    # ... and the others are the very same finding records, carried over.
    for code in ["FIRE-NOC-001", "FAC-RATIO-001", "FAC-DECL-001", "FAC-CADRE-001"]:
        assert after[code]["id"] == before[code]["id"]
    assert after["DOC-REQ-001"]["status"] == "pass"
    assert after["FAC-QUAL-001"]["details"]["name_mismatches"] == []
    assert len(after["FAC-QUAL-001"]["details"]["without_certificate"]) == 3

    # A confirmed deficiency blocks approval; an override needs a justification.
    qual, ratio = after["FAC-QUAL-001"]["id"], after["FAC-RATIO-001"]["id"]
    override = {"outcome": "override"}
    assert post(client, reviewer, f"findings/{qual}/review", override).status_code == 422
    post(client, reviewer, f"findings/{qual}/review", {"outcome": "confirm"})
    post(
        client,
        reviewer,
        f"findings/{ratio}/review",
        {"outcome": "override", "comment": "Provisional rule; ratio norm not yet verified."},
    )
    res = post(client, reviewer, f"applications/{app_id}/decision", APPROVE)
    assert res.status_code == 409
    assert "confirmed" in res.json()["detail"]

    post(
        client,
        reviewer,
        f"findings/{qual}/review",
        {"outcome": "override", "comment": "Three certificates verified with the university."},
    )
    review = findings_by_code(client, reviewer, app_id)["FAC-QUAL-001"]["review"]
    assert review["outcome"] == "override"
    assert post(client, reviewer, f"applications/{app_id}/decision", APPROVE).status_code == 202

    wf = get(client, reviewer, f"applications/{app_id}/workflow")
    assert wf["finished"] is True
    assert wf["waiting_for"] is None
    assert wf["decision"]["decision"] == "approve"
    assert get(client, institution, f"applications/{app_id}")["status"] == "approved"
    events = {e["event_type"] for e in wf["events"]}
    assert {
        "application_submitted",
        "application_evaluated",
        "clarification_requested",
        "application_resubmitted",
        "finding_reviewed",
        "application_decided",
    } <= events

    # A finished case accepts no further decisions.
    assert post(client, reviewer, f"applications/{app_id}/decision", APPROVE).status_code == 409


def test_reject(client, case):
    _, reviewer, app_id = case
    reject = {"decision": "reject", "reason": "Faculty strength is below the norm."}
    assert post(client, reviewer, f"applications/{app_id}/decision", reject).status_code == 202
    assert get(client, reviewer, f"applications/{app_id}")["status"] == "rejected"


def test_review_permissions(client, case):
    institution, reviewer, app_id = case
    findings = get(client, reviewer, f"applications/{app_id}/findings")
    failed = next(f for f in findings if f["status"] == "fail")
    passed = next(f for f in findings if f["status"] == "pass")
    confirm = {"outcome": "confirm"}

    assert post(client, institution, f"findings/{failed['id']}/review", confirm).status_code == 403
    ask = {"message": "Please clarify.", "finding_ids": [failed["id"]]}
    assert post(client, institution, f"applications/{app_id}/clarification", ask).status_code == 403
    assert post(client, reviewer, f"findings/{passed['id']}/review", confirm).status_code == 409


def test_reviewer_document_reprocess_reevaluates(client, case):
    _, reviewer, app_id = case
    detail = get(client, reviewer, f"applications/{app_id}")
    doc = next(d for d in detail["documents"] if d["doc_type"] == "fire_noc")
    assert post(client, reviewer, f"documents/{doc['id']}/reprocess").status_code == 202
    wf = get(client, reviewer, f"applications/{app_id}/workflow")
    # Same document set, so only the document-set rules re-run; the case keeps waiting.
    assert wf["round"] == 2
    assert wf["waiting_for"] == "reviewer"
