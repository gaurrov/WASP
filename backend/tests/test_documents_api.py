from datetime import date, timedelta

import pytest

from app import synthetic
from app.models.enums import UserRole
from tests.conftest import auth_headers
from tests.test_applications import NEW_APP, upload


@pytest.fixture
def institution_user(make_user):
    return make_user(UserRole.INSTITUTION)


@pytest.fixture
def app_id(client, institution_user):
    res = client.post("/api/applications", json=NEW_APP, headers=auth_headers(institution_user))
    return res.json()["id"]


def test_upload_extracts_facts_with_provenance(client, institution_user, app_id):
    pdf, _ = synthetic.fire_noc(date.today())
    doc = upload(client, institution_user, app_id, pdf, doc_type="fire_noc").json()

    detail = client.get(f"/api/documents/{doc['id']}", headers=auth_headers(institution_user))
    assert detail.status_code == 200
    body = detail.json()
    assert body["processing_status"] == "done"
    assert body["detected_doc_type"] == "fire_noc"
    assert body["type_mismatch"] is False
    assert body["ocr_used"] is False
    assert body["pages"][0]["width"] == pytest.approx(595)

    facts = {f["field_name"]: f for f in body["facts"]}
    valid = facts["valid_until"]
    assert valid["value"] == (date.today() + timedelta(days=30)).isoformat()
    assert valid["page"] == 1
    assert valid["low_confidence"] is False
    x0, y0, x1, y1 = valid["bbox"]
    assert 0 < x0 < x1 < 595 and 0 < y0 < y1 < 842

    app_detail = client.get(f"/api/applications/{app_id}", headers=auth_headers(institution_user))
    listed = app_detail.json()["documents"][0]
    assert listed["fact_count"] == len(body["facts"])
    assert listed["low_confidence_count"] == 0


def test_declared_type_mismatch_is_flagged(client, institution_user, app_id):
    pdf, _ = synthetic.fire_noc(date.today())
    doc = upload(client, institution_user, app_id, pdf, doc_type="lab_inventory").json()
    body = client.get(f"/api/documents/{doc['id']}", headers=auth_headers(institution_user)).json()
    assert body["detected_doc_type"] == "fire_noc"
    assert body["type_mismatch"] is True


def test_page_render(client, institution_user, app_id):
    pdf, _ = synthetic.land_document()
    doc = upload(client, institution_user, app_id, pdf, doc_type="land_document").json()
    headers = auth_headers(institution_user)

    page = client.get(f"/api/documents/{doc['id']}/pages/1.png", headers=headers)
    assert page.status_code == 200
    assert page.content.startswith(b"\x89PNG")
    assert client.get(f"/api/documents/{doc['id']}/pages/2.png", headers=headers).status_code == 404


def test_reprocess_is_reviewer_only_and_idempotent(client, make_user, institution_user, app_id):
    pdf, _ = synthetic.building_certificate()
    doc = upload(client, institution_user, app_id, pdf, doc_type="building_certificate").json()
    client.post(f"/api/applications/{app_id}/submit", headers=auth_headers(institution_user))
    reviewer = make_user(UserRole.REVIEWER)
    url = f"/api/documents/{doc['id']}"

    before = client.get(url, headers=auth_headers(reviewer)).json()["facts"]
    assert (
        client.post(f"{url}/reprocess", headers=auth_headers(institution_user)).status_code == 403
    )
    assert client.post(f"{url}/reprocess", headers=auth_headers(reviewer)).status_code == 202
    after = client.get(url, headers=auth_headers(reviewer)).json()["facts"]

    assert len(after) == len(before)  # replaced, not duplicated
    assert {f["field_name"]: f["value"] for f in after} == {
        f["field_name"]: f["value"] for f in before
    }


def test_documents_respect_tenant_isolation(client, make_user, institution_user, app_id):
    pdf, _ = synthetic.land_document()
    doc = upload(client, institution_user, app_id, pdf, doc_type="land_document").json()
    other = auth_headers(make_user(UserRole.INSTITUTION))
    for path in ["", "/content", "/pages/1.png"]:
        assert client.get(f"/api/documents/{doc['id']}{path}", headers=other).status_code == 404
