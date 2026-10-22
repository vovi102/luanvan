# Offline setup repair — 2026-10-22

The user approved the bounded setup/timing design after choosing to address
setup before continuing the campaign. This change is offline only. No Kaggle
upload/session, model inference, EN replacement, final VI continuation or new
BigQuery job was performed or authorized by this implementation.

## Change

Setup allowance is now 1,620s (27m), derived from the unchanged 7,200s session
cap minus 5,460s maximum worker watchdog and 120s cleanup reserve. Native
process cap remains 5,400s (90m); worker preflight uses watchdog time. These
are upper bounds, not a guarantee of 90 full generation minutes. The added
seven setup minutes uses existing session headroom without increasing the
native/session caps. Exact mounted-cache hash verification remains mandatory.

The driver creates an exclusive `stage-timings.jsonl` per fresh session and
records each subprocess start/finish: stage, setup/session budget, driver/stage
elapsed seconds, allocated timeout, remaining budget and completed/failed/
timed-out outcome. Error records contain the exception type, not command text
or environment variables. Finish records persist through ordinary exceptions
and watchdog timeouts. Existing process-group termination, failure propagation,
owned-scratch cleanup and exclusive log/artifact writes remain unchanged.
Timing files are included in the session output manifest, and summaries now
state setup/worker/cleanup caps explicitly. A failure before the first subprocess
can leave an empty timing file; the summary still carries the failing stage.
Hard platform termination or disk failure can prevent final records, as before.

`scripts/27_kaggle_b12_benchmark.py` is embedded exactly in disabled notebook 16;
campaign configuration/documentation uses the new cap. All three notebook
opt-ins remain false. No dependency or accepted setup script is modified.

Old operational driver SHA:
`39a39ad40a5fd0b2a3c575cc437e473ac5bdea24f88871cac23d1ae531f3bfe7`.
New operational driver SHA:
`7f80915acfb47ce4e2741eb1f60f20487b121390d9cdd2ef43ffe8b1f4e7c5de`.
Retain each submitted notebook/source hash and cap revision with its session;
the old failed session remains immutable and is not relabeled complete.

## Verification scope

Three new simulated-time tests failed against the original code: cache setup
exhausted the old allowance, and timeout/error timing files did not exist.
After implementation all three passed. These tests execute real driver budget,
logging, failure and cleanup logic with TEST-ONLY external-process timings;
they never install packages or create genuine inference evidence.

The slow-setup test spends 27m on setup, allocates at most 91m to the worker,
finishes at 118m and leaves the 2m reserve. Timeout/error tests retain stage
timing/output and stop before later work; a secret-like test environment value
and PATH marker do not appear in timing records. Existing real subprocess-group
termination, input integrity, default-disabled notebook and embedded-source
tests remain in the focused operational suite.

Focused suite: 19 passed. Lint/format, notebook nbformat/compilation, embedded
source/hash and disabled defaults pass. AST comparison confirms planner,
selection, completeness, worker, raw subprocess handling and cleanup functions
unchanged; all model/encoder/input/cache pins and four setup-kit fingerprints
match. Notebook 14 is unchanged. Full project suite: **1,593 passed, 342 warnings, 788.72s**. The warning count
matches the historical preparation-suite count; no claim is made that every
warning instance is identical. Results/log are retained in linked machine
evidence. Two additional TEST-ONLY clock probes verify unused session headroom
does not raise the 91m worker cap, and expired budget blocks process creation
while retaining a timeout event. No real mounted-cache completion is claimed
from these offline checks.

## Handoff

The original problem was cumulative setup watchdog exhaustion while mounted
verification was running. Underlying verification slowness was not established.
More bounded headroom and retained stage timing improve the operational policy
and evidence; they do not prove the original Kaggle cache check would now finish.
A separately authorized private setup-only validation is the next external
check, with inference disabled and original exact-byte checks preserved.
That validation must not be presented as a benchmark replicate.

Campaign remains ten complete native processes, one failed setup slot, final
VI unstarted. No attempt ID may be reused, no failed evidence hidden or partial
outputs spliced. An EN replacement still requires a distinct approved identity
and protocol decision; final-VI continuation after the failed EN setup has not
been approved. Scientific blockers/readiness and T5.4/BigQuery gates stay intact.
The accepted input archive is unchanged; rebuilding from the checkout containing
updated runbook prose does not reproduce that archive and is not a substitute.

[Diagnosis](kaggle-b12-setup-diagnosis-2026-10-22.md) and
[repair verification evidence](../evidence/kaggle-b12-setup-repair-2026-10-22.json).
