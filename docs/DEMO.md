# WASP — demo playbook

A 7-minute live demo of the full story, with preparation, a run sheet, fallbacks and Q&A prep.
Every step below is also executed and asserted by `python -m app.demo rehearse`.
Measured numbers for the pitch are in [METRICS.md](METRICS.md).

---

## 1. The day before (with internet)

```bash
git pull && docker compose up -d --build          # images, migrations, seed
docker compose exec backend python -m app.demo prefetch    # demo PDFs + embedding model
docker compose exec backend python -m app.demo preflight   # everything green?
docker compose exec backend python -m app.demo rehearse --times 5
```

- If you have the official APH 2024-27 PDF: load it (README → *Loading the AICTE handbook*) and
  verify the three draft rules on the **Rules** page. Citations then show real clauses and the
  "provisional" badges disappear. If not, keep the badges and say so (it's a strength, see Q&A).
- Prove it works offline, exactly as it will at the venue:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d --force-recreate
  docker compose exec backend python -m app.demo rehearse --times 3
  ```
- Record a backup screen capture of the whole run sheet (section 3) in case the laptop fails.
- Laptop: disable sleep/updates/notifications, plug in, close Docker-heavy apps.

## 2. At the venue (10 minutes before)

```bash
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d
docker compose exec backend python -m app.demo preflight
docker compose exec backend python -m app.demo load --stage draft     # resets, then preloads
```

`load --stage draft` creates ABC Institute's application with all 41 documents uploaded and
extracted, **except** the building certificate. Uploading 41 files by hand on stage wastes a
minute; showing them already there doesn't.

Open three browser windows (each origin keeps its own login):

| Window | URL | Log in as |
|---|---|---|
| Institution | http://localhost:5173 | institution@wasp.dev |
| Reviewer | http://127.0.0.1:5173 | reviewer@wasp.dev |
| Admin | private/incognito window, http://localhost:5173 | admin@wasp.dev |

Password for all: `wasp1234`. Have `data/synthetic/abc_institute/` open in the file picker.

## 3. Run sheet (~7 min)

| # | Time | Window | Do | Say |
|---|---|---|---|---|
| 1 | 0:00 | Institution | Open the application. Point at the checklist, field counts, "3 to verify" on `certificate_09.pdf`. | "An institution has uploaded 41 documents. WASP has already read every one: native text, and OCR for scans." |
| 2 | 0:40 | Institution | Click `certificate_09.pdf`. Click the amber *Holder name*. | "This is a bad photocopy. Every value is linked to where it was read on the page, with a confidence. Below 80% it's never trusted: it goes to a human." |
| 3 | 1:20 | Institution | Back → **Submit for review** → accept the missing-document warning. | "They submit with a document missing. We don't block; we record it." |
| 4 | 1:40 | Reviewer | Review queue → the application. Walk the findings top-down. Click one evidence chip. | "Seven rules ran in under a second. Missing building certificate. 3 of 20 faculty have no certificate. 'S. Priya' versus 'S. Priyaa'. 20 faculty for 480 students against 1:20. Fire NOC expiring in 30 days. Each finding shows its evidence, and the clause it enforces." |
| 5 | 2:50 | Reviewer | Point at a **provisional** badge and its *where this norm comes from*. | "Rules encoding AICTE norms stay provisional until an officer verifies them against the handbook clause. The system never pretends a number is official." |
| 6 | 3:10 | Reviewer | **Request clarification…** → type a short message → send. | "The case is now paused, waiting for the institution, and the clock starts on their response." |
| 7 | 3:30 | Institution | Refresh. Banner + alert badge. **Replace** `certificate_02.pdf` with `certificate_02_corrected.pdf`; **Upload** `building_certificate.pdf` → **Resubmit**. | "They fix exactly what was asked." |
| 8 | 4:15 | Reviewer | Refresh. Point at **"Round 2: re-checked 3 of 7 rules"**. | "Only the rules those two documents can affect re-ran. The other four results are carried over, untouched. That's what makes continuous checking cheap at scale." |
| 9 | 4:45 | Reviewer | Override the remaining findings with one-line reasons → **Approve…** → reason → confirm. | "Approval is impossible until every open finding has a human decision with a reason. AI extracts and checks; people decide." |
| 10 | 5:25 | Institution | **Alerts** badge → "Fire safety NOC expires in 30 days". | "Approval isn't the end. WASP keeps watching." |
| 11 | 5:45 | Admin | **Alerts** → scan *as of* a date 40 days ahead → **Run scan**. | "Fast-forward 40 days: the NOC has expired, the alert is critical and escalated." |
| 12 | 6:10 | Institution | Alert → **Upload renewal** → `fire_noc_renewed.pdf`. Show it moved to *Resolved*. | "A renewed certificate closes the alert by itself. Nobody ticks a box; the data proves it." |
| 13 | 6:35 | Reviewer | Scroll to the **Audit trail**. | "Every upload, extraction, rule run, review, decision and alert, with who and when." |

## 4. If something goes wrong

| Problem | Recovery (in the backend container) |
|---|---|
| A step misbehaves | `python -m app.demo load --stage <next stage>` and continue from there. Stages: `draft`, `submitted`, `clarification`, `resubmitted`, `approved`, `renewed`. |
| Not sure what's down | `python -m app.demo preflight` |
| Documents stuck "extracting…" | `docker compose restart worker` (tasks are redelivered safely) |
| Browser shows stale state | Refresh; the API is the source of truth |
| Laptop or Docker dies | Play the backup recording; screenshots are in the deck |

`load` prints the application URL; open it in the reviewer and institution windows.

## 5. Q&A prep (answer honestly)

**Is the AI approving applications?** No. Extraction and retrieval are automated; checks are
deterministic code; anything uncertain is routed to a reviewer; approval requires a human decision
with a written reason for every open finding.

**What if OCR misreads something?** Values below 80% confidence are flagged, never trusted. But
confidence isn't a guarantee: in our tests some degradation levels produced a confident misread
name. That's why cross-document checks exist: the faculty list and the certificate must agree, so
a misread name surfaces as a mismatch for review.

**Why are some rules "provisional"?** Their numbers (1:20, 1:2:6, fire NOC validity) are widely
cited, but we haven't yet verified them against the 2024-27 handbook text. The system shows that
openly; an officer verifies each rule against the exact clause, then it cites it.

**Does it work on real documents?** It's built and measured on a synthetic set that mirrors real
ones. The pattern-based extractors handle the layouts we wrote them for. Real documents vary, so
the next step is a pilot set and an LLM fallback for fields the patterns miss. All numbers in
METRICS.md are measured, not projected.

**Why LangGraph?** A case can wait days for a reviewer or institution. The graph is checkpointed
in Postgres, so it survives restarts, resumes in any worker, and knows exactly where it's waiting.

**How does it scale?** Heavy work runs in background workers by queue, so more documents means
more workers, not a slower portal. Incremental re-validation re-checks only what changed. We
haven't load-tested at national scale; the architecture separates the parts that need to scale.

**Where does data go?** Nowhere: everything runs on-premises, including OCR and the embedding
model. This demo runs with the internet blocked.

**What did you not build?** Email/SMS delivery of alerts, a separate approver role, integration
with the AICTE portal, and evaluation on real documents.
