"""Synthetic AICTE application documents with ground truth, for development, tests and the demo.

Everything is fictional and deterministic for a given seed. Planted issues (see docs/PLAN.md):
  * faculty list declares 20 members but only 17 qualification certificates exist
  * one certificate spells a faculty name differently from the faculty list
  * the fire NOC expires 30 days after `today`
  * one certificate is a poor-quality scan (OCR confidence should be low)

Usage: python -m app.synthetic [--out /data/synthetic] [--today 2026-10-27] [--seed 7]
"""

import argparse
import io
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image, ImageFilter

INSTITUTION = "ABC Institute of Technology"
TRUST = "ABC Educational Trust"
ADDRESS = "No. 12, OMR Road, Sholinganallur, Chennai - 600119"
PROGRAMME = "B.E. Computer Science and Engineering"
UNIVERSITIES = ["Anna University", "University of Madras", "Bharathiar University"]
DEGREES = {
    "Ph.D.": "Doctor of Philosophy",
    "M.E.": "Master of Engineering",
    "M.Tech.": "Master of Technology",
}
FACULTY_NAMES = [
    "A. Kumar", "S. Priya", "R. Venkatesh", "M. Lakshmi", "K. Arun", "P. Divya", "N. Ramesh",
    "V. Kavitha", "T. Suresh", "G. Meena", "J. Prakash", "L. Anitha", "B. Karthik", "D. Revathi",
    "H. Senthil", "C. Nandhini", "E. Balaji", "F. Sangeetha", "I. Mohan", "Y. Deepa",
]  # fmt: skip
FEMALE = {"S. Priya", "M. Lakshmi", "P. Divya", "V. Kavitha", "G. Meena", "L. Anitha",
          "D. Revathi", "C. Nandhini", "F. Sangeetha", "Y. Deepa"}  # fmt: skip
CERTIFIED_FACULTY = 17
MISSPELLED = {1: "S. Priyaa"}  # faculty index → name as printed on their certificate
POOR_SCAN_INDEX = 8
SCANNED_INDEXES = {4, POOR_SCAN_INDEX}


@dataclass
class Generated:
    file: str
    doc_type: str
    expected: dict[str, Any]
    scanned: str | None = None  # None | "good" | "poor"
    notes: list[str] = field(default_factory=list)


def dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


class Page:
    """Minimal top-down text layout on an A4 page."""

    def __init__(self, doc: pymupdf.Document):
        self.page = doc.new_page(width=595, height=842)
        self.y = 72.0

    def text(self, s: str, size: float = 11, bold: bool = False, x: float = 60, gap: float = 8):
        self.y += size
        font = "hebo" if bold else "helv"
        self.page.insert_text((x, self.y), s, fontsize=size, fontname=font)
        self.y += gap

    def center(self, s: str, size: float = 14, bold: bool = True, gap: float = 10):
        font = "hebo" if bold else "helv"
        width = pymupdf.get_text_length(s, fontname=font, fontsize=size)
        self.text(s, size, bold, x=(595 - width) / 2, gap=gap)

    def row(self, cells: list[tuple[float, str]], size: float = 10, bold: bool = False):
        self.y += size
        for x, s in cells:
            self.page.insert_text(
                (x, self.y), s, fontsize=size, fontname="hebo" if bold else "helv"
            )
        self.y += 7

    def rule(self, gap: float = 10):
        self.page.draw_line((60, self.y + 4), (535, self.y + 4), width=0.6)
        self.y += gap


def scan(pdf_bytes: bytes, rng: random.Random, quality: str) -> bytes:
    """Rasterize like a photocopy: grayscale, slight skew, noise, blur, JPEG artefacts."""
    poor = quality == "poor"
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=100 if poor else 200, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        img = img.rotate(rng.uniform(-1.6, 1.6) if poor else rng.uniform(-0.6, 0.6),
                         fillcolor=255, resample=Image.Resampling.BICUBIC)  # fmt: skip
        noise = Image.effect_noise(img.size, 90 if poor else 25)
        img = Image.blend(img, noise, 0.3 if poor else 0.07)
        img = img.filter(ImageFilter.GaussianBlur(1.2 if poor else 0.4))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=15 if poor else 75)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=buf.getvalue())
    return out.tobytes(deflate=True)


def faculty_roster(rng: random.Random) -> list[dict[str, str]]:
    designations = ["Professor"] * 3 + ["Associate Professor"] * 5 + ["Assistant Professor"] * 12
    roster = []
    for i, name in enumerate(FACULTY_NAMES):
        designation = designations[i]
        qualification = (
            "Ph.D."
            if designation != "Assistant Professor"
            else rng.choice(["M.E.", "M.Tech.", "Ph.D."])
        )
        prefix = "Dr. " if qualification == "Ph.D." else ("Ms. " if name in FEMALE else "Mr. ")
        roster.append({
            "name": prefix + name,
            "designation": designation,
            "qualification": qualification,
            "university": rng.choice(UNIVERSITIES),
            "awarded_on": date(rng.randint(2004, 2021), rng.randint(1, 12), rng.randint(1, 28)),
            "joined_on": date(rng.randint(2012, 2025), rng.choice([6, 7]), rng.randint(1, 28)),
        })  # fmt: skip
    return roster


def faculty_list(roster: list[dict]) -> tuple[bytes, dict]:
    doc = pymupdf.open()
    p = Page(doc)
    p.center(INSTITUTION, 16)
    p.center("Faculty List - Academic Year 2026-27", 12, bold=False)
    p.text(f"Programme: {PROGRAMME}", 10)
    p.rule()
    cols = [60, 95, 250, 390, 470]
    p.row(list(zip(cols, ["S.No", "Name", "Designation", "Qualification", "Department"],
                   strict=True)), bold=True)  # fmt: skip
    for i, f in enumerate(roster, 1):
        p.row(list(zip(cols, [str(i), f["name"], f["designation"], f["qualification"], "CSE"],
                       strict=True)))  # fmt: skip
    p.rule()
    p.text("Certified that the above information is true and correct.", 10)
    p.text("Principal", 10, bold=True, x=440)
    expected = {
        "faculty_count": len(roster),
        "faculty_member": [
            {
                "name": f["name"],
                "designation": f["designation"],
                "qualification": f["qualification"],
            }
            for f in roster
        ],
    }
    return doc.tobytes(), expected


def qualification_certificate(f: dict, printed_name: str) -> tuple[bytes, dict]:
    degree = DEGREES[f["qualification"]]
    doc = pymupdf.open()
    p = Page(doc)
    p.y = 120
    p.center(f["university"].upper(), 18)
    p.center("DEGREE CERTIFICATE", 13, gap=30)
    p.text(f"This is to certify that {printed_name}", 12)
    p.text(f"has been awarded the degree of {degree}", 12)
    p.text("in Computer Science and Engineering", 12)
    p.text("having fulfilled all the requirements prescribed for the degree.", 12, gap=30)
    p.text(f"Awarded on {dmy(f['awarded_on'])}", 12)
    p.y = 700
    p.text("Registrar", 12, bold=True, x=440)
    expected = {
        "holder_name": printed_name,
        "degree": degree,
        "university": f["university"],
        "awarded_on": f["awarded_on"].isoformat(),
    }
    return doc.tobytes(), expected


def appointment_letter(f: dict, ref: str) -> tuple[bytes, dict]:
    doc = pymupdf.open()
    p = Page(doc)
    p.center(INSTITUTION, 16)
    p.center(ADDRESS, 9, bold=False, gap=20)
    p.text(f"Ref: {ref}", 10)
    p.text(f"Date: {dmy(f['joined_on'] - timedelta(days=14))}", 10, gap=16)
    p.text(f"Dear {f['name']},", 11, gap=12)
    p.text("Sub: Letter of Appointment", 11, bold=True, gap=12)
    p.text(f"We are pleased to appoint you to the post of {f['designation']} in the", 11)
    p.text("Department of Computer Science and Engineering on a regular basis.", 11, gap=12)
    p.text(f"Date of Joining: {dmy(f['joined_on'])}", 11)
    p.text("Pay Level: as per AICTE norms", 11, gap=40)
    p.text("Principal", 11, bold=True, x=440)
    expected = {
        "employee_name": f["name"],
        "designation": f["designation"],
        "date_of_joining": f["joined_on"].isoformat(),
    }
    return doc.tobytes(), expected


def fire_noc(today: date) -> tuple[bytes, dict]:
    issued, valid = today - timedelta(days=335), today + timedelta(days=30)
    doc = pymupdf.open()
    p = Page(doc)
    p.center("TAMIL NADU FIRE AND RESCUE SERVICES", 15)
    p.center("FIRE NO OBJECTION CERTIFICATE", 13, gap=24)
    p.text("NOC No: TNFRS/CHN/2025/04417", 11)
    p.text(f"Name of the Institution: {INSTITUTION}", 11)
    p.text(f"Address: {ADDRESS}", 11)
    p.text("Occupancy: Educational Building (Ground + 4 floors)", 11, gap=16)
    p.text("Fire safety installations were inspected and found satisfactory.", 11, gap=16)
    p.text(f"Date of Issue: {dmy(issued)}", 11)
    p.text(f"Valid up to: {dmy(valid)}", 11, gap=30)
    p.text("Issued by: Divisional Fire Officer, Chennai South", 11)
    expected = {
        "certificate_number": "TNFRS/CHN/2025/04417",
        "institution_name": INSTITUTION,
        "issued_on": issued.isoformat(),
        "valid_until": valid.isoformat(),
        "issuing_authority": "Divisional Fire Officer, Chennai South",
    }
    return doc.tobytes(), expected


def building_certificate() -> tuple[bytes, dict]:
    doc = pymupdf.open()
    p = Page(doc)
    p.center("GREATER CHENNAI CORPORATION", 15)
    p.center("BUILDING COMPLETION CERTIFICATE", 13, gap=24)
    p.text("Certificate No: GCC/BP/2019/1182", 11)
    p.text(f"Name of the Owner: {TRUST}", 11)
    p.text(f"Site Address: {ADDRESS}", 11)
    p.text("Built-up Area: 12,450 sq.m", 11)
    p.text("Use: Educational Institution", 11, gap=16)
    p.text("Date of Issue: 03/06/2019", 11, gap=30)
    p.text("Executive Engineer (Building Plans)", 11, bold=True, x=330)
    expected = {
        "certificate_number": "GCC/BP/2019/1182",
        "institution_name": TRUST,
        "built_up_area_sqm": 12450,
        "issued_on": "2019-06-03",
    }
    return doc.tobytes(), expected


def land_document() -> tuple[bytes, dict]:
    doc = pymupdf.open()
    p = Page(doc)
    p.center("SALE DEED", 16, gap=20)
    p.text("Registered at Sub-Registrar Office, Sholinganallur", 11)
    p.text("Date of Registration: 17 March 2008", 11)
    p.text("Document No: 2214/2008", 11, gap=16)
    p.text(f"In favour of: {TRUST}", 11)
    p.text("Survey No: 214/3B, Sholinganallur Village", 11)
    p.text("Total Land Area: 12.5 acres", 11, gap=16)
    p.text("The vendor hereby conveys the said land absolutely to the purchaser.", 11)
    expected = {
        "document_date": "2008-03-17",
        "owner_name": TRUST,
        "survey_number": "214/3B",
        "area_acres": 12.5,
    }
    return doc.tobytes(), expected


def lab_inventory(rng: random.Random) -> tuple[bytes, dict]:
    items = [
        ("Desktop Computer (i7, 16 GB)", 30), ("Managed Network Switch", 4),
        ("Wireless Access Point", 6), ("Router", 4), ("Network Analyzer", 2),
        ("UPS 10 kVA", 2), ("Projector", 1), ("Crimping Tool Kit", 15),
    ]  # fmt: skip
    total = sum(q for _, q in items)
    doc = pymupdf.open()
    p = Page(doc)
    p.center(INSTITUTION, 16)
    p.center("Laboratory Equipment Inventory", 12, bold=False, gap=16)
    p.text("Laboratory Name: Computer Networks Lab", 11)
    p.text("Department: Computer Science and Engineering", 11)
    p.rule()
    p.row([(60, "S.No"), (100, "Equipment"), (430, "Quantity")], bold=True)
    for i, (name, qty) in enumerate(items, 1):
        p.row([(60, str(i)), (100, name), (430, str(qty))])
    p.rule()
    p.text(f"Total Items: {total}", 11, bold=True)
    expected = {"lab_name": "Computer Networks Lab", "total_items": total}
    return doc.tobytes(), expected


def generate(out: Path, today: date, seed: int = 7) -> list[Generated]:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    manifest: list[Generated] = []

    def write(name: str, data: bytes, item: Generated) -> None:
        (out / name).write_bytes(data)
        manifest.append(item)

    roster = faculty_roster(rng)
    data, expected = faculty_list(roster)
    write("faculty_list.pdf", data, Generated("faculty_list.pdf", "faculty_list", expected))

    for i, f in enumerate(roster[:CERTIFIED_FACULTY]):
        printed = MISSPELLED.get(i, f["name"])
        data, expected = qualification_certificate(f, printed)
        item = Generated(f"certificate_{i + 1:02d}.pdf", "qualification_certificate", expected)
        if printed != f["name"]:
            item.notes.append(f"name differs from faculty list ({f['name']})")
        if i in SCANNED_INDEXES:
            item.scanned = "poor" if i == POOR_SCAN_INDEX else "good"
            data = scan(data, rng, item.scanned)
        write(item.file, data, item)

    for i, f in enumerate(roster):
        data, expected = appointment_letter(f, f"ABCIT/HR/APT/{f['joined_on'].year}/{i + 101}")
        name = f"appointment_{i + 1:02d}.pdf"
        write(name, data, Generated(name, "appointment_letter", expected))

    data, expected = fire_noc(today)
    item = Generated("fire_noc.pdf", "fire_noc", expected, notes=["expires in 30 days"])
    write(item.file, data, item)
    scanned = Generated("fire_noc_scanned.pdf", "fire_noc", expected, scanned="good")
    write(scanned.file, scan(data, rng, "good"), scanned)

    for name, (data, expected), doc_type in [
        ("building_certificate.pdf", building_certificate(), "building_certificate"),
        ("land_document.pdf", land_document(), "land_document"),
        ("lab_inventory.pdf", lab_inventory(rng), "lab_inventory"),
    ]:
        write(name, data, Generated(name, doc_type, expected))

    (out / "manifest.json").write_text(
        json.dumps(
            {"today": today.isoformat(), "seed": seed, "documents": [vars(m) for m in manifest]},
            indent=2,
        )
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("/data/synthetic/abc_institute"))
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    manifest = generate(args.out, args.today, args.seed)
    print(f"Wrote {len(manifest)} documents + manifest.json to {args.out}")


if __name__ == "__main__":
    main()
