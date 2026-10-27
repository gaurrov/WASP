"""The demo story as executable, asserted steps (see docs/DEMO.md for the spoken script).

Each stage leaves the system exactly where that part of the live demo starts, so `load --stage`
can recover from a failed live step, and `rehearse` proves the whole story end to end.
"""

import json
import random
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app import synthetic
from app.demo.client import Client, DemoError, wait_until

STAGES = ["draft", "submitted", "clarification", "resubmitted", "approved", "renewed"]
NOT_UPLOADED = {"building_certificate.pdf", "fire_noc_scanned.pdf"}  # planted missing document
DECLARED = {
    "programme": "B.E. Computer Science and Engineering",
    "sanctioned_intake": 120,
    "faculty_count": 20,
}


@dataclass
class Demo:
    inst: Client = field(default_factory=lambda: Client("institution"))
    reviewer: Client = field(default_factory=lambda: Client("reviewer"))
    admin: Client = field(default_factory=lambda: Client("admin"))
    files: dict[str, tuple[str, bytes]] = field(default_factory=dict)  # name → (doc_type, pdf)
    app_id: str = ""
    timings: dict[str, float] = field(default_factory=dict)
    detected: dict[str, bool] = field(default_factory=dict)  # planted issue → caught?

    # --- helpers -------------------------------------------------------------------------

    def detail(self, client: Client | None = None) -> dict:
        return (client or self.inst).get(f"/applications/{self.app_id}")

    def findings(self) -> dict[str, dict]:
        return {
            f["rule"]["code"]: f for f in self.reviewer.get(f"/applications/{self.app_id}/findings")
        }

    def workflow(self) -> dict:
        return self.reviewer.get(f"/applications/{self.app_id}/workflow")

    def wait_extracted(self) -> dict:
        def done():
            d = self.detail()
            states = {doc["processing_status"] for doc in d["documents"]}
            if "failed" in states:
                failed = [
                    x["filename"] for x in d["documents"] if x["processing_status"] == "failed"
                ]
                raise DemoError(f"extraction failed: {failed}")
            return d if states <= {"done"} else None

        return wait_until("document extraction", done)

    def wait_status(self, *statuses: str) -> dict:
        def reached():
            d = self.detail()
            return d if d["status"] in statuses else None

        return wait_until(f"status in {statuses}", reached)

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            raise DemoError(f"{label} {detail}".strip())

    # --- stages --------------------------------------------------------------------------

    def draft(self) -> None:
        """Institution creates the application and uploads everything except the building
        certificate. Extraction runs on the worker (OCR for the two scans)."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            synthetic.generate(folder, date.today())
            manifest = json.loads((folder / "manifest.json").read_text())
            for item in manifest["documents"]:
                self.files[item["file"]] = (item["doc_type"], (folder / item["file"]).read_bytes())
        roster = synthetic.faculty_roster(random.Random(7))
        self.files["certificate_02_corrected.pdf"] = (
            "qualification_certificate",
            synthetic.qualification_certificate(roster[1], roster[1]["name"])[0],
        )
        self.files["fire_noc_renewed.pdf"] = (
            "fire_noc",
            synthetic.fire_noc(date.today() + timedelta(days=700))[0],
        )

        app = self.inst.post(
            "/applications",
            {
                "application_type": "extension_of_approval",
                "academic_year": "2026-27",
                "declared": DECLARED,
            },
        )
        self.app_id = app["id"]
        for name, (doc_type, pdf) in self.files.items():
            if (
                name.startswith("certificate_02_")
                or name == "fire_noc_renewed.pdf"
                or name in NOT_UPLOADED
            ):
                continue
            self.inst.upload(self.app_id, name, pdf, doc_type)
        d = self.wait_extracted()
        poor = next(x for x in d["documents"] if x["filename"] == "certificate_09.pdf")
        self.detected["Poor scan flagged for verification"] = poor["low_confidence_count"] > 0
        self.check(
            "draft is missing the building certificate",
            "building_certificate" in d["missing_required"],
        )

    def submitted(self) -> None:
        """Submission starts the case workflow; rules run and the case waits for a reviewer."""
        self.inst.post(f"/applications/{self.app_id}/submit")
        self.wait_status("needs_review")
        f = self.findings()
        self.detected["Missing building certificate"] = (
            f["DOC-REQ-001"]["status"] == "fail"
            and "Building completion certificate" in f["DOC-REQ-001"]["details"]["missing"]
        )
        qual = f["FAC-QUAL-001"]
        self.detected["3 faculty without certificates"] = (
            len(qual["details"]["without_certificate"]) == 3
        )
        self.detected["Name mismatch (S. Priya / S. Priyaa)"] = any(
            m["certificate"] == "S. Priyaa" for m in qual["details"]["name_mismatches"]
        )
        self.detected["Faculty shortfall vs 1:20 (provisional rule)"] = (
            f["FAC-RATIO-001"]["status"] == "fail" and f["FAC-RATIO-001"]["provisional"]
        )
        self.detected["Fire NOC expiring in 30 days"] = (
            f["FIRE-NOC-001"]["details"].get("expiring_soon") is True
        )
        missed = [k for k, v in self.detected.items() if not v]
        self.check("all planted issues detected", not missed, f"— missed: {missed}")
        self.check("case waits for reviewer", self.workflow()["waiting_for"] == "reviewer")

    def clarification(self) -> None:
        """Reviewer asks the institution to fix the open findings."""
        open_ids = [
            f["id"] for f in self.findings().values() if f["status"] in ("fail", "needs_review")
        ]
        self.reviewer.post(
            f"/applications/{self.app_id}/clarification",
            {
                "message": "Please upload the building completion certificate and a corrected "
                "degree certificate for Dr. S. Priya (printed as S. Priyaa).",
                "finding_ids": open_ids,
            },
        )
        self.wait_status("clarification_requested")
        alerts = self.inst.get("/alerts")
        self.check(
            "institution got a response-deadline alert",
            any(a["alert_type"] == "clarification_response" for a in alerts),
        )

    def resubmitted(self) -> None:
        """Institution fixes two documents and resubmits; only affected rules re-run."""
        before = self.findings()
        docs = {d["filename"]: d for d in self.detail()["documents"]}
        doc_type, pdf = self.files["certificate_02_corrected.pdf"]
        self.inst.upload(
            self.app_id,
            "certificate_02_corrected.pdf",
            pdf,
            doc_type,
            replaces_id=docs["certificate_02.pdf"]["id"],
        )
        doc_type, pdf = self.files["building_certificate.pdf"]
        self.inst.upload(self.app_id, "building_certificate.pdf", pdf, doc_type)
        self.wait_extracted()
        self.inst.post(f"/applications/{self.app_id}/submit")
        wait_until("round 2 evaluation", lambda: self.workflow()["round"] >= 2)
        self.wait_status("needs_review", "ready_for_decision")

        wf, after = self.workflow(), self.findings()
        rechecked = set(wf["rechecked"])
        self.check(
            "only affected rules re-checked",
            rechecked == {"DOC-REQ-001", "DOC-TYPE-001", "FAC-QUAL-001"},
            str(rechecked),
        )
        for code in ("FIRE-NOC-001", "FAC-RATIO-001", "FAC-DECL-001", "FAC-CADRE-001"):
            self.check(f"{code} carried over", after[code]["id"] == before[code]["id"])
        self.check("building certificate now present", after["DOC-REQ-001"]["status"] == "pass")
        self.check(
            "Priya mismatch resolved",
            not any(
                m["certificate"] == "S. Priyaa"
                for m in after["FAC-QUAL-001"]["details"]["name_mismatches"]
            ),
        )

    def approved(self) -> None:
        """Reviewer justifies overrides for what's left and approves."""
        for f in self.findings().values():
            if f["status"] in ("fail", "needs_review", "unable_to_determine"):
                self.reviewer.post(
                    f"/findings/{f['id']}/review",
                    {
                        "outcome": "override",
                        "comment": f"Verified offline for the demo ({f['rule']['code']}).",
                    },
                )
        self.reviewer.post(
            f"/applications/{self.app_id}/decision",
            {
                "decision": "approve",
                "reason": "Deficiencies resolved or verified. Fire NOC renewal to be monitored.",
            },
        )
        self.wait_status("approved")
        alert = wait_until(
            "fire NOC expiry alert",
            lambda: next(
                (
                    a
                    for a in self.inst.get("/alerts", application_id=self.app_id)
                    if a["alert_type"] == "certificate_expiry"
                ),
                None,
            ),
        )
        self.check("expiry alert is high severity", alert["severity"] == "high")

    def renewed(self) -> None:
        """Time passes (simulated scan), the alert escalates; a renewal clears it automatically."""
        as_of = (datetime.now(UTC) + timedelta(days=40)).isoformat()
        self.admin.post("/monitoring/scan", {"as_of": as_of})
        alert = next(
            a
            for a in self.inst.get("/alerts", application_id=self.app_id)
            if a["alert_type"] == "certificate_expiry"
        )
        self.check(
            "expiry alert escalated after 40 days", alert["status"] == "escalated", alert["status"]
        )

        doc_type, pdf = self.files["fire_noc_renewed.pdf"]
        self.inst.upload(
            self.app_id,
            "fire_noc_renewed.pdf",
            pdf,
            doc_type,
            replaces_id=alert["details"]["document_id"],
        )
        wait_until(
            "expiry alert auto-resolved",
            lambda: next(
                (
                    a
                    for a in self.inst.get("/alerts", status="resolved", application_id=self.app_id)
                    if a["alert_type"] == "certificate_expiry"
                ),
                None,
            ),
        )


def run(until: str = STAGES[-1], demo: Demo | None = None) -> Demo:
    if until not in STAGES:
        raise ValueError(f"unknown stage {until!r}; choose from {STAGES}")
    demo = demo or Demo()
    for stage in STAGES[: STAGES.index(until) + 1]:
        start = time.perf_counter()
        getattr(demo, stage)()
        demo.timings[stage] = time.perf_counter() - start
    return demo


def summary(demo: Demo) -> dict[str, Any]:
    return {"application_id": demo.app_id, "timings": demo.timings, "detected": demo.detected}
