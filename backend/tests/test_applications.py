import pymupdf
import pytest

from app.models.enums import UserRole
from tests.conftest import auth_headers

NEW_APP = {
    "application_type": "extension_of_approval",
    "academic_year": "2026-27",
    "declared": {
        "programme": "B.E. Computer Science",
        "sanctioned_intake": 120,
        "faculty_count": 20,
    },
}


def make_pdf(text: str = "hello", pages: int = 1) -> bytes:
    pdf = pymupdf.open()
    for i in range(pages):
        pdf.new_page().insert_text((72, 72), f"{text} page {i + 1}")
    return pdf.tobytes()


@pytest.fixture
def institution_user(make_user):
    return make_user(UserRole.INSTITUTION)


@pytest.fixture
def application(client, institution_user):
    res = client.post("/api/applications", json=NEW_APP, headers=auth_headers(institution_user))
    assert res.status_code == 201, res.text
    return res.json()


def upload(client, user, app_id, data, doc_type="fire_noc", filename="doc.pdf", **form):
    return client.post(
        f"/api/applications/{app_id}/documents",
        files={"file": (filename, data, "application/pdf")},
        data={"doc_type": doc_type, **form},
        headers=auth_headers(user),
    )


def test_create_application_starts_as_draft_with_full_checklist(application):
    assert application["status"] == "draft"
    assert application["institution_name"] == "Test Institute"
    assert application["application_type_label"] == "Extension of Approval"
    assert application["declared"]["faculty_count"] == 20
    assert "fire_noc" in application["missing_required"]
    assert "other" not in application["missing_required"]  # optional item


@pytest.mark.parametrize(
    "patch",
    [
        {"academic_year": "2026-28"},
        {"academic_year": "26-27"},
        {"application_type": "nope"},
        {"declared": {"programme": "", "sanctioned_intake": 1, "faculty_count": 1}},
    ],
)
def test_create_application_validates_input(client, institution_user, patch):
    res = client.post(
        "/api/applications", json=NEW_APP | patch, headers=auth_headers(institution_user)
    )
    assert res.status_code == 422


def test_only_institution_users_create_applications(client, make_user):
    reviewer = make_user(UserRole.REVIEWER)
    res = client.post("/api/applications", json=NEW_APP, headers=auth_headers(reviewer))
    assert res.status_code == 403


def test_upload_updates_checklist_and_stores_file(client, institution_user, application):
    res = upload(client, institution_user, application["id"], make_pdf(pages=3))
    assert res.status_code == 201, res.text
    doc = res.json()
    assert doc["page_count"] == 3
    assert doc["mime_type"] == "application/pdf"

    detail = client.get(
        f"/api/applications/{application['id']}", headers=auth_headers(institution_user)
    ).json()
    fire = next(c for c in detail["checklist"] if c["doc_type"] == "fire_noc")
    assert fire == fire | {"document_count": 1, "satisfied": True}
    assert "fire_noc" not in detail["missing_required"]

    content = client.get(
        f"/api/documents/{doc['id']}/content", headers=auth_headers(institution_user)
    )
    assert content.status_code == 200
    assert content.content.startswith(b"%PDF-")


def test_upload_rejects_non_document_files(client, institution_user, application):
    res = upload(
        client, institution_user, application["id"], b"MZ\x90\x00not a pdf", filename="x.pdf"
    )
    assert res.status_code == 415


def test_upload_rejects_exact_duplicates(client, institution_user, application):
    data = make_pdf("same")
    assert upload(client, institution_user, application["id"], data).status_code == 201
    assert upload(client, institution_user, application["id"], data).status_code == 409


def test_replacing_a_document_creates_a_new_version(client, institution_user, application):
    first = upload(client, institution_user, application["id"], make_pdf("v1")).json()
    second = upload(
        client, institution_user, application["id"], make_pdf("v2"), replaces_id=first["id"]
    ).json()

    assert second["version"] == 2
    # A replacement can't change the document's type.
    mismatched = upload(
        client,
        institution_user,
        application["id"],
        make_pdf("v3"),
        doc_type="land_document",
        replaces_id=second["id"],
    )
    assert mismatched.status_code == 422
    assert second["supersedes_id"] == first["id"]
    detail = client.get(
        f"/api/applications/{application['id']}", headers=auth_headers(institution_user)
    ).json()
    assert [d["id"] for d in detail["documents"]] == [second["id"]]


def test_institutions_cannot_see_each_others_applications(client, make_user, application):
    other = make_user(UserRole.INSTITUTION)
    headers = auth_headers(other)
    assert client.get(f"/api/applications/{application['id']}", headers=headers).status_code == 404
    assert client.get("/api/applications", headers=headers).json() == []
    assert upload(client, other, application["id"], make_pdf()).status_code == 404


def test_reviewers_see_submitted_applications_but_not_drafts(
    client, make_user, institution_user, application
):
    reviewer = make_user(UserRole.REVIEWER)
    doc = upload(client, institution_user, application["id"], make_pdf()).json()
    url = f"/api/applications/{application['id']}"

    assert client.get(url, headers=auth_headers(reviewer)).status_code == 404
    assert client.get("/api/applications", headers=auth_headers(reviewer)).json() == []

    submitted = client.post(f"{url}/submit", headers=auth_headers(institution_user))
    # Submission triggers rule evaluation; one document is far from compliant.
    assert submitted.json()["status"] == "needs_review"
    assert submitted.json()["submitted_at"] is not None

    queue = client.get("/api/applications", headers=auth_headers(reviewer)).json()
    assert [a["id"] for a in queue] == [application["id"]]
    assert queue[0]["document_count"] == 1
    assert client.get(url, headers=auth_headers(reviewer)).status_code == 200
    content = client.get(f"/api/documents/{doc['id']}/content", headers=auth_headers(reviewer))
    assert content.status_code == 200


def test_submitted_applications_are_locked(client, institution_user, application):
    url = f"/api/applications/{application['id']}"
    doc = upload(client, institution_user, application["id"], make_pdf()).json()
    client.post(f"{url}/submit", headers=auth_headers(institution_user))

    headers = auth_headers(institution_user)
    assert upload(client, institution_user, application["id"], make_pdf("late")).status_code == 409
    assert client.delete(f"{url}/documents/{doc['id']}", headers=headers).status_code == 409
    assert client.post(f"{url}/submit", headers=headers).status_code == 409


def test_draft_documents_can_be_deleted(client, institution_user, application):
    doc = upload(client, institution_user, application["id"], make_pdf()).json()
    url = f"/api/applications/{application['id']}"
    res = client.delete(f"{url}/documents/{doc['id']}", headers=auth_headers(institution_user))
    assert res.status_code == 204
    detail = client.get(url, headers=auth_headers(institution_user)).json()
    assert detail["documents"] == []
