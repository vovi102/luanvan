# T3.5 candidate review guide

Codex authored the 120 candidate questions and GoogleSQL queries in this pack.
The user is the sole human reviewer and must record every decision explicitly;
no row is treated as reviewed merely because it appears in `candidates.jsonl`.

The candidates are agent-authored. Record one append-only event per review round
in `review_events.csv` using a stable pseudonymous reviewer ID. `ACCEPT` requires
both scores to be at least 4. `REVISE` requires changed NL or SQL and a later
explicit `ACCEPT`; it never implies acceptance. `REJECT` is terminal.

After all 120 candidates have terminal decisions, list exactly 100 accepted IDs
in `final_selection.csv` with 30 easy, 50 medium, and 20 hard cases. Do not edit
`candidates.jsonl`. BigQuery verification and final publication remain pending
until the review files pass offline validation.

Live BigQuery verification is pending and requires a separate explicit opt-in.
