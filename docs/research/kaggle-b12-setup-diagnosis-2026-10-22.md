# Setup timeout diagnosis — 2026-10-22

The user chose “Dừng để xử lý lỗi setup trước”. Final B2 VI r03 remains
unstarted; the previously prepared disabled continuation proposal was not
approved. This investigation uses retained local evidence only. No new remote
session, inference, retry, runtime change or model download was performed.

## Findings

Compared all ten completed native sessions and the failed B2 EN r03 setup.
The operational driver/cache/model/encoder pins and full dependency lock are
unchanged across these submissions. Earlier successful package preparation
ranged from 56.01s to 3m49s. Failed-session preparation took 7m46s for the same
218 packages; installation then completed in 14.08s. This establishes increased
package preparation elapsed time, not its underlying network/CPU/I/O cause.

The next stage was original mounted-cache byte verification. Its allowed timeout
was 615.233s, calculated from the shared 1,200s setup budget, which was already
584.767s consumed. It timed out at cumulative 1,200.003s. Direct cause:
setup watchdog exhaustion while cache verification was running. The verifier
hashes pinned model/encoder files and emits a result only when all finish;
its failed-session log is empty. Cache corruption, a particular stuck file,
OOM or a particular I/O bottleneck is not established.

The full driver-minus-native elapsed for successful sessions ranged from
235.961s to 787.413s. This includes setup, worker preflight and driver evidence
overhead; it must not be presented as exact cache verification timing. There is
insufficient per-stage telemetry to compare cache read durations precisely.

All six failed-session native-manifest entries/seven saved files pass integrity
verification. Native runner never started; no predictions/native report/ledger
or completeness receipt was published. Scratch cleanup succeeded. Retain this
as a setup failure, not 0/100 accuracy or a completed replicate. Campaign stays
ten complete native processes, one failed setup slot, one unstarted VI slot.

## Bounded repair candidate, not implemented

Increase only setup allowance from 1,200s to 1,620s (20m to 27m), and persist
stage start/end/elapsed, remaining allowance and exit/timeout outcome, including
failed stages. Use elapsed monotonic timing and avoid environment/credential
dumps. Preserve exact cache byte verification and fail-stop behavior; do not
skip hashing, change accepted input/cache/lock or research semantics.

Budget arithmetic: 1,620s setup + 5,460s maximum worker watchdog + 120s cleanup
= 7,200s. Native process cap stays 5,400s, including model/encoder setup and
generation. Worker watchdog includes preflight overhead; this remains an upper
bound policy, not a guarantee of a full 90m of inference. Extra seven setup
minutes uses existing session headroom and does not raise the 120m session cap.
It is not proof the mounted-cache check will finish within the new allowance.

The bounded change would touch the operational driver, its embedded disabled
notebook, focused operational tests and cap documentation. The accepted bundle
and scripts 25/17/26, model/encoder, prompts, retrieval, seed/greedy/quantization,
scientific thresholds and all original failed/native artifacts would stay
unchanged. The driver/source hash would explicitly change for future sessions;
preserve old source/hash and distinguish protocol revisions in future audits.

Meaningful offline verification: simulate slow stages to verify timeout
telemetry/remaining budget; check the full budget sum and worker bounds; retain
existing descendant-kill, default-disabled notebook and embedded-source integrity
checks. No remote setup-only validation or new benchmark run is authorized by
this design. A real remote validation would be needed before claiming the
operational issue fixed. Any EN replacement still needs a new approved identity
and must remain separate from the original failed setup.

This is a bounded change to existing flow. The short in-chat design requires
approval before runtime implementation under the brainstorming skill. Current
output is a diagnosis and concrete repair recommendation, not a fix claim.

[Machine comparison](../evidence/kaggle-b12-setup-diagnosis-2026-10-22.json)
contains all eleven session observations and hashes of supporting summary/log
sources. [Original failure audit](kaggle-b12-benchmark-b2-en-r03-2026-10-21.md)
and native artifacts remain unchanged.
