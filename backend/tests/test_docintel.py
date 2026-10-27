from datetime import date

import pytest

from app import synthetic
from app.docintel.dates import parse_date
from app.docintel.evaluate import evaluate

TODAY = date(2026, 10, 27)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("25/07/2021", date(2021, 7, 25)),
        ("5-3-2019", date(2019, 3, 5)),
        ("03.06.2019", date(2019, 6, 3)),
        ("17 March 2008", date(2008, 3, 17)),
        ("1st Sept, 2024", date(2024, 9, 1)),
        ("March 17, 2008", date(2008, 3, 17)),
        ("2026-10-27", date(2026, 10, 27)),
        ("31/02/2026", None),
        ("25°07 /2021", None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.fixture(scope="module")
def evaluation(tmp_path_factory):
    folder = tmp_path_factory.mktemp("synthetic")
    synthetic.generate(folder, TODAY)
    return evaluate(folder)


def test_extraction_quality_gate(evaluation):
    """Regression gate over the synthetic set (native + scanned). Nothing may be silently wrong:
    every incorrect value must either be missing or flagged low-confidence for a reviewer."""
    ok, flagged, wrong, missing = evaluation["totals"]
    assert evaluation["classification_accuracy"] == 1.0
    assert wrong == 0, evaluation["failures"]
    assert missing == 0, evaluation["failures"]
    assert ok / (ok + flagged) >= 0.95


def test_poor_scan_is_flagged_not_trusted(evaluation):
    poor = {k: v for k, v in evaluation["fields"].items() if "scanned-poor" in k}
    assert sum(v[1] for v in poor.values()) >= 1  # at least one field routed to review
    assert sum(v[2] for v in poor.values()) == 0  # and none silently wrong
