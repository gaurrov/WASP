"""Test-only documents. The "regulation" below is invented filler for exercising chunking and
retrieval; it is not AICTE text and must never be loaded into a real deployment."""

from datetime import date

import pymupdf

from app import synthetic

TEST_REGULATION = [
    (1, "TEST FIXTURE - NOT REGULATORY TEXT"),
    (1, "Chapter I General Provisions"),
    (1, "1.1 Scope"),
    (1, "These provisions describe how institutions apply for approval of programmes."),
    (1, "1.2 Documents to be uploaded"),
    (1, "Institutions shall upload the faculty list, certificates and building documents."),
    (2, "2.1 Faculty norms"),
    (2, "The student faculty ratio for undergraduate engineering programmes is 1:20."),
    (2, "Faculty shall be appointed in the cadre ratio of 1:2:6 for Professor, Associate"),
    (2, "Professor and Assistant Professor."),
    (2, "2.2 Fire safety"),
    (2, "A valid fire safety no objection certificate issued by the fire and rescue service"),
    (2, "shall be maintained for all buildings."),
    (3, "Appendix 3 Land requirements"),
    (3, "Land area requirements depend on the location category of the institution."),
]


def regulation_pdf() -> bytes:
    doc = pymupdf.open()
    pages: dict[int, tuple[pymupdf.Page, list[float]]] = {}
    for page_no, line in TEST_REGULATION:
        if page_no not in pages:
            pages[page_no] = (doc.new_page(width=595, height=842), [72.0])
        page, y = pages[page_no]
        y[0] += 18
        page.insert_text((60, y[0]), line, fontsize=11)
    return doc.tobytes()


def demo_documents(today: date) -> list[tuple[str, str, bytes]]:
    """(filename, doc_type, pdf) for an application mirroring the demo script: no building
    certificate, 17 certificates for 20 faculty, one misspelled name, NOC expiring in 30 days."""
    import random

    rng = random.Random(7)
    roster = synthetic.faculty_roster(rng)
    docs = [("faculty_list.pdf", "faculty_list", synthetic.faculty_list(roster)[0])]
    for i, f in enumerate(roster[: synthetic.CERTIFIED_FACULTY]):
        printed = synthetic.MISSPELLED.get(i, f["name"])
        pdf = synthetic.qualification_certificate(f, printed)[0]
        docs.append((f"certificate_{i + 1:02d}.pdf", "qualification_certificate", pdf))
    docs.append(("appointment_01.pdf", "appointment_letter",
                 synthetic.appointment_letter(roster[0], "REF/1")[0]))  # fmt: skip
    docs.append(("fire_noc.pdf", "fire_noc", synthetic.fire_noc(today)[0]))
    docs.append(("land_document.pdf", "land_document", synthetic.land_document()[0]))
    docs.append(("lab_inventory.pdf", "lab_inventory", synthetic.lab_inventory(rng)[0]))
    return docs
