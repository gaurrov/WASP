import re
from datetime import date

MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))

# Regex fragment matching any supported date, for use inside field patterns.
DATE_PATTERN = (
    r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTH_RE})[a-z]*\.?,?\s+\d{{4}}"
    rf"|(?:{MONTH_RE})[a-z]*\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"
    r"|\d{4}-\d{2}-\d{2}"
)


def parse_date(raw: str) -> date | None:
    """Parse the date formats seen on Indian certificates. Numeric dates are day-first."""
    s = raw.strip().lower().replace(",", " ")
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s):
            return date(int(m[3]), int(m[2]), int(m[1]))
        if m := re.fullmatch(
            rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_RE})[a-z]*\.?\s+(\d{{4}})", s
        ):
            return date(int(m[3]), MONTHS[m[2]], int(m[1]))
        if m := re.fullmatch(
            rf"({MONTH_RE})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+(\d{{4}})", s
        ):
            return date(int(m[3]), MONTHS[m[1]], int(m[2]))
    except ValueError:  # e.g. 31/02/2026
        return None
    return None
