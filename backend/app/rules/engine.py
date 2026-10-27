import uuid
from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Application,
    ComplianceRule,
    Document,
    ExtractedFact,
    Finding,
    RegulatoryChunk,
)
from app.models.enums import FindingStatus, RuleStatus, Severity
from app.rag.search import hybrid_search
from app.rules.context import EvalContext, Result
from app.rules.evaluators import EVALUATORS

RULES_FILE = Path(__file__).with_name("rules.yaml")
CITATIONS_PER_FINDING = 2


def sync_rules(db: Session) -> None:
    """Upsert rules.yaml. Definitions come from the file; verification state (status, citation)
    is owned by the database, so re-syncing never un-verifies a rule an admin approved."""
    for spec in yaml.safe_load(RULES_FILE.read_text()):
        if spec["evaluator"] not in EVALUATORS:
            raise ValueError(f"{spec['code']}: unknown evaluator {spec['evaluator']}")
        rule = db.scalar(
            select(ComplianceRule).where(
                ComplianceRule.rule_code == spec["code"], ComplianceRule.version == spec["version"]
            )
        )
        if rule is None:
            rule = ComplianceRule(
                rule_code=spec["code"],
                version=spec["version"],
                status=RuleStatus.APPROVED if spec.get("internal") else RuleStatus.DRAFT,
            )
            db.add(rule)
        rule.title = spec["title"]
        rule.evaluator = spec["evaluator"]
        rule.severity = Severity(spec.get("severity", "medium"))
        rule.internal = spec.get("internal", False)
        rule.applicability = spec.get("applicability", {})
        rule.params = spec.get("params", {})
        rule.required_evidence = spec.get("required_evidence", [])
        rule.citation_query = spec.get("citation_query")
        rule.norm_note = " ".join(spec["norm_note"].split()) if spec.get("norm_note") else None
    db.commit()


def academic_year_start(academic_year: str) -> date:
    return date(int(academic_year[:4]), 7, 1)


def active_rules(db: Session, application: Application) -> list[ComplianceRule]:
    """Latest non-retired version of each rule that applies to this application."""
    latest: dict[str, ComplianceRule] = {}
    for rule in db.scalars(
        select(ComplianceRule)
        .where(ComplianceRule.status != RuleStatus.RETIRED)
        .order_by(ComplianceRule.rule_code, ComplianceRule.version)
    ):
        latest[rule.rule_code] = rule
    return [
        r
        for r in latest.values()
        if application.application_type in r.applicability.get("application_type", [])
        or "application_type" not in r.applicability
    ]


def find_citations(db: Session, rule: ComplianceRule, on_date: date) -> list[uuid.UUID]:
    if rule.source_id:  # verified: cite exactly the clause the admin approved
        q = select(RegulatoryChunk.id).where(RegulatoryChunk.source_id == rule.source_id)
        if rule.source_section:
            q = q.where(RegulatoryChunk.section == rule.source_section)
        else:
            q = q.where(RegulatoryChunk.page == rule.source_page)
        return list(db.scalars(q.limit(CITATIONS_PER_FINDING)))
    if rule.citation_query:  # unverified: offer the best-matching passages as candidates
        hits = hybrid_search(db, rule.citation_query, k=CITATIONS_PER_FINDING, on_date=on_date)
        return [h.chunk.id for h in hits]
    return []


def guard_low_confidence(result: Result, threshold: float) -> Result:
    """A conclusion is only as reliable as its weakest input."""
    decisive = result.evidence if result.decisive is None else result.decisive
    low = [f for f in decisive if f.confidence < threshold]
    if low and result.status in (FindingStatus.PASS, FindingStatus.FAIL):
        result.details["original_status"] = result.status.value
        result.details["low_confidence_fact_ids"] = [str(f.id) for f in low]
        result.status = FindingStatus.NEEDS_REVIEW
        result.reason += (
            f" Depends on {len(low)} low-confidence value(s); verify them before relying on this."
        )
    return result


def evaluate(db: Session, application: Application, today: date | None = None) -> list[Finding]:
    settings = get_settings()
    documents = list(
        db.scalars(
            select(Document).where(Document.application_id == application.id, Document.is_current)
        )
    )
    facts = list(
        db.scalars(
            select(ExtractedFact).where(ExtractedFact.document_id.in_([d.id for d in documents]))
        )
    )
    ctx = EvalContext(
        application, documents, facts, today or date.today(), settings.low_confidence_threshold
    )
    on_date = academic_year_start(application.academic_year)

    db.execute(
        update(Finding)
        .where(Finding.application_id == application.id, Finding.is_current)
        .values(is_current=False)
    )
    findings = []
    for rule in active_rules(db, application):
        result = EVALUATORS[rule.evaluator](ctx, rule.params)
        result = guard_low_confidence(result, settings.low_confidence_threshold)
        finding = Finding(
            application_id=application.id,
            rule_id=rule.id,
            status=result.status,
            severity=rule.severity,
            reason=result.reason,
            evidence_fact_ids=list(dict.fromkeys(f.id for f in result.evidence)),
            source_chunk_ids=find_citations(db, rule, on_date),
            details=result.details | {"provisional": rule.status != RuleStatus.APPROVED},
        )
        db.add(finding)
        findings.append(finding)
    return findings
