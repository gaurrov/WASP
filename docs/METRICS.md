# WASP — measured metrics

Measured 2026-10-27 15:11 UTC (M6 branch, based on main c98957c), with outbound internet blocked (docker-compose.offline.yml), on the synthetic ABC Institute set, local Docker stack. Synthetic documents are cleaner than real ones: re-measure on real samples before quoting these as production figures.

## Document intelligence

| Metric | Value |
|---|---|
| Documents (incl. 3 scans) | 43 |
| Document type classification | 100% |
| Fields extracted correctly | 99.4% (168/169) |
| Wrong but flagged for human review | 0.6% |
| **Silently wrong** | **0.0%** |
| Missing | 0.0% |

## Planted issues caught

| Issue | Caught |
|---|---|
| Poor scan flagged for verification | yes |
| Missing building certificate | yes |
| 3 faculty without certificates | yes |
| Name mismatch (S. Priya / S. Priyaa) | yes |
| Faculty shortfall vs 1:20 (provisional rule) | yes |
| Fire NOC expiring in 30 days | yes |

## End-to-end timings (mean of 3 runs, real worker)

| Step | Time |
|---|---|
| Upload 41 documents + extraction (incl. OCR) | 4.0 s (max 4.4) |
| Submission → findings ready for review | 0.7 s (max 0.7) |
| Clarification request | 0.6 s (max 0.6) |
| Fix 2 documents + resubmit → re-evaluated | 1.3 s (max 1.4) |
| Overrides + approval | 0.7 s (max 0.8) |
| Time-travel scan + renewal → alert auto-resolved | 0.6 s (max 0.6) |

Re-validation after resubmission re-checked **3 of 7** rules; the other 4 findings were carried over unchanged.

Not measured: time saved versus manual scrutiny (needs a pilot with real reviewers).
