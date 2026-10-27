"""Deterministic rule evaluators: (context, params) -> Result.

Missing evidence is `unable_to_determine`, never `pass`. The engine downgrades any pass/fail
that rests on a low-confidence fact to `needs_review`.
"""

import math
import re
from collections import Counter
from collections.abc import Callable
from datetime import date
from difflib import SequenceMatcher

from app.models.enums import DocumentType, FindingStatus
from app.rules.context import EvalContext, Result

Evaluator = Callable[[EvalContext, dict], Result]
EVALUATORS: dict[str, Evaluator] = {}

PASS, FAIL = FindingStatus.PASS, FindingStatus.FAIL
REVIEW, UNKNOWN = FindingStatus.NEEDS_REVIEW, FindingStatus.UNABLE_TO_DETERMINE

TITLES = re.compile(r"\b(dr|mr|ms|mrs|prof|shri|smt)\b\.?", re.IGNORECASE)
QUALIFICATION_DEGREES = {
    "ph.d.": "doctor of philosophy",
    "m.e.": "master of engineering",
    "m.tech.": "master of technology",
}


def evaluator(fn: Evaluator) -> Evaluator:
    EVALUATORS[fn.__name__] = fn
    return fn


def normalize_name(name: str) -> str:
    name = TITLES.sub(" ", name)
    return " ".join(re.sub(r"[^a-z ]", " ", name.lower()).split())


def sentence(text: str) -> str:
    return text[:1].upper() + text[1:] + "."


@evaluator
def required_documents(ctx: EvalContext, params: dict) -> Result:
    missing = [
        item.label
        for item in ctx.checklist
        if item.required and not ctx.documents_of(item.doc_type)
    ]
    if missing:
        return Result(
            FAIL, f"Missing required documents: {', '.join(missing)}.", details={"missing": missing}
        )
    return Result(PASS, "All required document types are present.")


@evaluator
def document_types(ctx: EvalContext, params: dict) -> Result:
    mismatched = [
        {
            "document_id": str(d.id),
            "filename": d.filename,
            "declared": d.doc_type.value,
            "detected": d.detected_doc_type.value,
        }
        for d in ctx.documents
        if d.detected_doc_type
        and d.detected_doc_type not in (d.doc_type, DocumentType.UNCLASSIFIED)
        and (d.detection_confidence or 0) >= 0.6
    ]
    if mismatched:
        names = ", ".join(m["filename"] for m in mismatched)
        return Result(
            REVIEW,
            f"{len(mismatched)} document(s) may be uploaded under the wrong type: {names}.",
            details={"mismatched": mismatched},
        )
    return Result(PASS, "Every document's content matches its declared type.")


@evaluator
def declared_faculty_count(ctx: EvalContext, params: dict) -> Result:
    count = ctx.fact("faculty_count", DocumentType.FACULTY_LIST)
    declared = ctx.application.declared.get("faculty_count")
    if count is None:
        return Result(UNKNOWN, "No readable faculty list, so the declared count can't be checked.")
    details = {"declared": declared, "in_faculty_list": count.value}
    if count.value != declared:
        return Result(
            FAIL,
            f"Application declares {declared} faculty but the faculty list has {count.value}.",
            [count],
            details,
        )
    return Result(PASS, f"Faculty list matches the declared {declared} faculty.", [count], details)


@evaluator
def faculty_certificates(ctx: EvalContext, params: dict) -> Result:
    members = ctx.facts_named("faculty_member", DocumentType.FACULTY_LIST)
    if not members:
        return Result(UNKNOWN, "No readable faculty list to check certificates against.")
    holders = ctx.facts_named("holder_name", DocumentType.QUALIFICATION_CERTIFICATE)
    degrees = {f.document_id: f for f in ctx.facts_named("degree")}
    threshold = params.get("near_match_threshold", 0.8)

    unused = list(holders)
    matched, near, missing, wrong_degree = [], [], [], []
    evidence, missing_facts = [], []
    for member in members:
        name = member.value["name"]
        target = normalize_name(name)
        scored = [
            (SequenceMatcher(None, target, normalize_name(h.value)).ratio(), h) for h in unused
        ]
        best_score, best = max(scored, key=lambda s: s[0], default=(0.0, None))
        if best is not None and best_score == 1.0:
            unused.remove(best)
            matched.append(name)
            degree = degrees.get(best.document_id)
            expected = QUALIFICATION_DEGREES.get(member.value["qualification"].lower())
            if degree and expected and normalize_name(degree.value) != expected:
                wrong_degree.append(
                    {
                        "name": name,
                        "listed": member.value["qualification"],
                        "certificate": degree.value,
                    }
                )
                evidence += [member, degree]
        elif best is not None and best_score >= threshold:
            unused.remove(best)
            near.append(
                {"listed": name, "certificate": best.value, "similarity": round(best_score, 2)}
            )
            evidence += [member, best]
        else:
            missing.append(name)
            evidence.append(member)
            missing_facts.append(member)

    details = {
        "faculty_listed": len(members),
        "certificates": len(holders),
        "matched": len(matched),
        "without_certificate": missing,
        "name_mismatches": near,
        "qualification_mismatches": wrong_degree,
    }
    problems = []
    if missing:
        problems.append(
            f"{len(missing)} of {len(members)} listed faculty have no qualification certificate"
        )
    if near:
        pairs = "; ".join(f"“{n['listed']}” vs “{n['certificate']}”" for n in near)
        problems.append(f"names differ between faculty list and certificate ({pairs})")
    if wrong_degree:
        problems.append(
            f"{len(wrong_degree)} certificate(s) show a different qualification than listed"
        )
    reason = sentence("; ".join(problems))
    if missing:  # definite regardless of how well near-matched names were read
        return Result(FAIL, reason, evidence, details, decisive=missing_facts)
    if near or wrong_degree:
        return Result(REVIEW, reason, evidence, details)
    return Result(
        PASS, f"All {len(members)} listed faculty have a matching certificate.", details=details
    )


@evaluator
def student_faculty_ratio(ctx: EvalContext, params: dict) -> Result:
    count = ctx.fact("faculty_count", DocumentType.FACULTY_LIST)
    if count is None:
        return Result(UNKNOWN, "No readable faculty list, so faculty strength can't be checked.")
    intake = ctx.application.declared.get("sanctioned_intake", 0)
    per_faculty, years = params["max_students_per_faculty"], params["programme_years"]
    students = intake * years
    required = math.ceil(students / per_faculty)
    details = {
        "sanctioned_intake": intake,
        "programme_years": years,
        "students": students,
        "ratio": f"1:{per_faculty}",
        "required_faculty": required,
        "faculty": count.value,
    }
    if count.value < required:
        return Result(
            FAIL,
            f"{count.value} faculty for {students} students ({intake} × {years} years); "
            f"1:{per_faculty} requires at least {required}.",
            [count],
            details,
        )
    return Result(
        PASS,
        f"{count.value} faculty meets the 1:{per_faculty} requirement of {required}.",
        [count],
        details,
    )


@evaluator
def cadre_ratio(ctx: EvalContext, params: dict) -> Result:
    members = ctx.facts_named("faculty_member", DocumentType.FACULTY_LIST)
    if not members:
        return Result(UNKNOWN, "No readable faculty list, so the cadre ratio can't be checked.")
    counts = Counter(m.value["designation"] for m in members)
    prof_r, assoc_r, asst_r = params["ratio"]
    total_r, n = prof_r + assoc_r + asst_r, len(members)
    need_prof, need_assoc = math.floor(n * prof_r / total_r), math.floor(n * assoc_r / total_r)
    have_prof, have_assoc = counts["Professor"], counts["Associate Professor"]
    details = {
        "faculty": n,
        "professors": have_prof,
        "associate_professors": have_assoc,
        "assistant_professors": counts["Assistant Professor"],
        "required_professors": need_prof,
        "required_associate_professors": need_assoc,
        "ratio": ":".join(map(str, params["ratio"])),
    }
    short = []
    if have_prof < need_prof:
        short.append(f"{have_prof} Professors (need {need_prof})")
    if have_assoc < need_assoc:
        short.append(f"{have_assoc} Associate Professors (need {need_assoc})")
    if short:
        return Result(FAIL, f"Cadre ratio not met: {', '.join(short)}.", members, details)
    return Result(
        PASS,
        f"{have_prof} Professors and {have_assoc} Associate Professors meet "
        f"{details['ratio']} for {n} faculty.",
        details=details,
    )


@evaluator
def certificate_validity(ctx: EvalContext, params: dict) -> Result:
    doc_type = DocumentType(params["doc_type"])
    label = params.get("label", doc_type.value.replace("_", " "))
    if not ctx.documents_of(doc_type):
        return Result(UNKNOWN, f"No {label} submitted.")
    fact = ctx.fact(params["field"], doc_type)
    if fact is None:
        return Result(UNKNOWN, f"Couldn't find a validity date on the {label}.")
    try:
        valid_until = date.fromisoformat(fact.value)
    except (TypeError, ValueError):
        return Result(REVIEW, f"{label} validity date “{fact.raw_text}” couldn't be read.", [fact])
    days = (valid_until - ctx.today).days
    details = {
        "valid_until": fact.value,
        "days_remaining": days,
        "expiring_soon": 0 <= days <= params.get("warn_within_days", 90),
    }
    if days < 0:
        return Result(FAIL, f"{label} expired on {valid_until:%d %b %Y}.", [fact], details)
    if details["expiring_soon"]:
        return Result(
            PASS,
            f"{label} is valid until {valid_until:%d %b %Y} but expires in {days} days.",
            [fact],
            details,
        )
    return Result(PASS, f"{label} is valid until {valid_until:%d %b %Y}.", [fact], details)
