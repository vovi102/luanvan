# Vietnamese paired benchmark review

This draft is agent-authored from gold SQL, semantic annotations, catalog context,
and expected outputs. It is not a translation of the English surface questions.

The single human reviewer must review every pair for natural Vietnamese, SQL
faithfulness, terminology, and ambiguity. Record append-only decisions in
`review_events.jsonl`; do not auto-fill or fabricate acceptance events.

## Decision format

Add one compact JSON object per line with exactly these fields:

```json
{"pair_id":"pair-t35-001","review_round":1,"reviewer_role":"user","decision":"ACCEPT","naturalness":5,"sql_faithfulness":5,"terminology":5,"ambiguity":1,"revised_question":"","notes":""}
```

- `decision` is `ACCEPT`, `REVISE`, or `REJECT`.
- `naturalness`, `sql_faithfulness`, `terminology`, and `ambiguity` are integers
  from 1 to 5. Higher is better except for `ambiguity`, where lower is better.
- `REVISE` requires a non-empty `revised_question`, followed by another event
  for the same pair with the next consecutive `review_round`.
- `ACCEPT` requires naturalness, SQL faithfulness, and terminology of at least 4,
  and ambiguity of at most 2. It must be the final event for that pair.
- `reviewer_role` must remain `user`. Review all 100 candidates; do not copy an
  acceptance event across pairs without checking the candidate and its SQL.

Use `validate-draft` after edits to candidates and `finalize` only when the
append-only event log contains an explicit final `ACCEPT` for every pair.
