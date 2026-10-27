from datetime import date

import pytest

from app.docintel.text import extract_text
from app.models.enums import UserRole
from app.rag.chunk import chunk_document
from tests.conftest import auth_headers
from tests.fixtures import regulation_pdf
from tests.test_rules import evaluated  # noqa: F401  (fixture)


def test_chunks_follow_clause_numbering():
    chunks = chunk_document(extract_text(regulation_pdf(), "application/pdf"))
    by_section = {c.section: c for c in chunks}
    assert {"Chapter I", "1.1", "1.2", "2.1", "2.2", "Appendix 3"} <= set(by_section)
    assert by_section["2.1"].heading == "Faculty norms"
    assert by_section["2.1"].page == 2
    assert "1:20" in by_section["2.1"].text


@pytest.fixture
def source(client, make_user):
    admin = make_user(UserRole.ADMIN)
    res = client.post(
        "/api/regulatory/sources",
        files={"file": ("fixture.pdf", regulation_pdf(), "application/pdf")},
        data={
            "title": "Test Fixture Handbook",
            "version": "T1",
            "effective_from": "2024-07-01",
            "effective_to": "2027-06-30",
        },
        headers=auth_headers(admin),
    )
    assert res.status_code == 201, res.text
    return admin, res.json()


def test_upload_ingests_source(client, source):
    admin, created = source
    sources = client.get("/api/regulatory/sources", headers=auth_headers(admin)).json()
    assert sources[0]["ingest_status"] == "done"
    assert sources[0]["chunk_count"] >= 6


def test_only_admins_upload_sources(client, make_user):
    reviewer = make_user(UserRole.REVIEWER)
    res = client.post(
        "/api/regulatory/sources",
        files={"file": ("x.pdf", regulation_pdf(), "application/pdf")},
        data={"title": "Nope", "version": "1"},
        headers=auth_headers(reviewer),
    )
    assert res.status_code == 403


@pytest.mark.parametrize(
    ("query", "section"),
    [
        ("student faculty ratio", "2.1"),  # keyword
        ("how many teachers per student", "2.1"),  # paraphrase: semantic
        ("fire NOC", "2.2"),
    ],
)
def test_hybrid_search(client, make_user, source, query, section):
    reviewer = make_user(UserRole.REVIEWER)
    hits = client.get(
        "/api/regulatory/search", params={"q": query}, headers=auth_headers(reviewer)
    ).json()
    assert hits[0]["section"] == section


def test_search_respects_effective_dates(client, make_user, source):
    reviewer = auth_headers(make_user(UserRole.REVIEWER))
    params = {"q": "student faculty ratio", "on_date": "2030-01-01"}
    assert client.get("/api/regulatory/search", params=params, headers=reviewer).json() == []


def test_verifying_a_rule_makes_citations_exact(client, make_user, source, evaluated):  # noqa: F811
    admin, _ = source
    _, app, _ = evaluated
    rules = client.get("/api/rules", headers=auth_headers(admin)).json()
    ratio = next(r for r in rules if r["rule_code"] == "FAC-RATIO-001")
    assert ratio["status"] == "draft"

    candidates = client.get(f"/api/rules/{ratio['id']}/candidates", headers=auth_headers(admin))
    clause = next(c for c in candidates.json() if c["section"] == "2.1")
    verified = client.post(
        f"/api/rules/{ratio['id']}/verify",
        json={"chunk_id": clause["chunk_id"]},
        headers=auth_headers(admin),
    ).json()
    assert verified["status"] == "approved"
    assert (verified["source_section"], verified["source_page"]) == ("2.1", 2)

    url = f"/api/applications/{app['id']}"
    client.post(f"{url}/evaluate", headers=auth_headers(admin))
    finding = next(
        f
        for f in client.get(f"{url}/findings", headers=auth_headers(admin)).json()
        if f["rule"]["code"] == "FAC-RATIO-001"
    )
    assert finding["provisional"] is False
    assert finding["citations"][0]["verified"] is True
    assert finding["citations"][0]["section"] == "2.1"


def test_internal_rules_cannot_be_given_citations(client, source):
    admin, _ = source
    rules = client.get("/api/rules", headers=auth_headers(admin)).json()
    internal = next(r for r in rules if r["internal"])
    hit = client.get(
        "/api/regulatory/search", params={"q": "faculty"}, headers=auth_headers(admin)
    ).json()[0]
    res = client.post(
        f"/api/rules/{internal['id']}/verify",
        json={"chunk_id": hit["chunk_id"]},
        headers=auth_headers(admin),
    )
    assert res.status_code == 409


def test_unrelated_date_is_used_for_academic_year():
    from app.rules.engine import academic_year_start

    assert academic_year_start("2026-27") == date(2026, 7, 1)
