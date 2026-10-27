"""Score the extraction pipeline against a synthetic set's ground truth.

Usage: python -m app.docintel.evaluate [/data/synthetic/abc_institute]

A field counts as correct when the normalized value equals the expected value. A wrong value
that was flagged low-confidence is reported separately: it would reach a human, not slip through.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.docintel.pipeline import process
from app.models.enums import DocumentType


def _norm(v: Any) -> Any:
    if isinstance(v, str):
        return " ".join(v.lower().split())
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    return v


def evaluate(folder: Path) -> dict:
    threshold = get_settings().low_confidence_threshold
    manifest = json.loads((folder / "manifest.json").read_text())
    # key → [correct, flagged_wrong, silent_wrong, missing]
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    classified = 0
    failures: list[str] = []

    for item in manifest["documents"]:
        doc_type = DocumentType(item["doc_type"])
        result = process((folder / item["file"]).read_bytes(), "application/pdf", doc_type)
        classified += result.detected_type == doc_type
        mode = f"scanned-{item['scanned']}" if item["scanned"] else "native"

        got: dict[str, list] = defaultdict(list)
        for f in result.fields:
            got[f.name].append(f)

        for name, expected in item["expected"].items():
            key = f"{doc_type.value}.{name} [{mode}]"
            expected_items = expected if isinstance(expected, list) else [expected]
            actual = got.get(name, [])
            for i, exp in enumerate(expected_items):
                if i >= len(actual):
                    stats[key][3] += 1
                    failures.append(f"{item['file']}: {name} missing (expected {exp!r})")
                elif _norm(actual[i].value) == _norm(exp):
                    stats[key][0] += 1
                elif actual[i].confidence < threshold:
                    stats[key][1] += 1
                else:
                    stats[key][2] += 1
                    failures.append(
                        f"{item['file']}: {name} = {actual[i].value!r} "
                        f"(conf {actual[i].confidence}), expected {exp!r}"
                    )

    totals = [sum(s[i] for s in stats.values()) for i in range(4)]
    return {
        "documents": len(manifest["documents"]),
        "classification_accuracy": classified / len(manifest["documents"]),
        "fields": dict(sorted(stats.items())),
        "totals": totals,
        "failures": failures,
    }


def main() -> None:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/synthetic/abc_institute")
    r = evaluate(folder)
    print(f"{'field':58} {'ok':>4} {'flag':>4} {'WRONG':>5} {'miss':>4}")
    for key, (ok, flagged, wrong, missing) in r["fields"].items():
        print(f"{key:58} {ok:>4} {flagged:>4} {wrong:>5} {missing:>4}")
    ok, flagged, wrong, missing = r["totals"]
    total = ok + flagged + wrong + missing
    accuracy = r["classification_accuracy"]
    print(f"\nDocuments: {r['documents']}  Classification accuracy: {accuracy:.0%}")
    print(
        f"Fields: {total}  correct {ok / total:.1%}  flagged-for-review {flagged / total:.1%}  "
        f"silently wrong {wrong / total:.1%}  missing {missing / total:.1%}"
    )
    if r["failures"]:
        print("\nProblems:")
        print("\n".join(f"  {f}" for f in r["failures"]))


if __name__ == "__main__":
    main()
