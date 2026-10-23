# B1/B2 EN/VI native generation matrix — 2026-10-23

All12 planned generation roles now have complete genuine native evidence:
B1 EN3/VI3 and B2 EN3/VI3, each full100cases per run/language. Two failed
setups remain retained, giving14attempted IDs. B2 EN r03 is fulfilled by the
separately authorized replacement02 run, not by relabeling either failed attempt.
No remaining B1/B2 native generation process needs launching. No new session
was created during this result review.

This is generation/artifact completeness, not scientific campaign acceptance
or SQL execution accuracy. Every original report remains scientific_ready=false
with latency_gate_failed, live_evidence_missing and reviewed_test_set_missing.
Source case authorities had been verified; original native aggregate review/live
flags stay conservative. No report/flag/threshold/SQL repair or test tuning is
performed. No additional runs are selected to obtain better outputs or latency.

## Independent verification

All12 native run/report file hashes, report canonical self-digests, native output
hashes,100ordered unique per-run case IDs, genuine completion markers/run/language
identity, accepted bundle-content hash and EN/VI input snapshot digests pass.
Configuration matches within each language after excluding execution campaign
identity and mounted HF_HOME path; model/encoder revisions,4bit/BF16,seed42,
greedy,batch1,512tokens and5400s native caps remain fixed. All actual native
hardware is T4 with Python3.11.15. Final14-ID native ledger exactly equals the
12successful IDs and2retained failed IDs. No fake native ledger is created for
setup failures. Earlier source/paired-lineage/retrieval reviews remain valid by
unchanged artifact hashes. Final replacement02 independently revalidates its
7208×384train-only cache and all500selected examples.

Each row below keeps N=100. Replicates reuse the same100questions; they are not
300distinct cases. EN and VI are not pooled. “Extraction OK” means native SQL
extraction accepted the text; it does not mean predicted SQL executed correctly.
No aggregate execution accuracy or statistical comparison is inferred here.

| Baseline | Language | Role | N | Extraction OK | P50 generation (s) | P95 generation (s) |
|---|---|---|---:|---:|---:|---:|
| B1 | EN | r01 | 100 | 0 | 25.457 | 49.107 |
| B1 | EN | r02 | 100 | 0 | 25.522 | 48.809 |
| B1 | EN | r03 | 100 | 0 | 23.260 | 45.922 |
| B1 | VI | r01 | 100 | 0 | 20.461 | 30.376 |
| B1 | VI | r02 | 100 | 0 | 19.814 | 29.532 |
| B1 | VI | r03 | 100 | 0 | 20.664 | 31.101 |
| B2 | EN | r01 | 100 | 31 | 33.696 | 52.987 |
| B2 | EN | r02 | 100 | 31 | 32.443 | 51.300 |
| B2 | EN | r03 (replacement02) | 100 | 31 | 31.959 | 50.256 |
| B2 | VI | r01 | 100 | 12 | 30.977 | 73.590 |
| B2 | VI | r02 | 100 | 12 | 30.515 | 72.962 |
| B2 | VI | r03 | 100 | 12 | 28.525 | 68.346 |

## Final B2 EN replacement02

Private v1 kernel140401001 COMPLETE.100genuine EN generations verified;
31extraction OK,60prose,8unsafe,1invalid. P5031.959s/P9550.256s.
Native inference3,474.011s (57.90m), driver3,727.032s (62.12m), native exit0,
scratch cleanup complete. T4×2/Python3.11.15/torch2.5.1+cu124/CUDA12.4,
accepted archive/cache-v5 and data/runtime gates pass. Full26saved files
(11,397,279bytes),25native manifest entries, no omissions/model payload downloads.

T4 setup finished219.001s (3.65m), including137.393s mounted-cache verification
and75.168s pinned package installation. This session passed original checks
comfortably within27m. It does not isolate the cause of earlier T4 slowness or
prove that it cannot recur; no hash gate was weakened or bypassed using CPU
receipts. Source/defaults/caps and native scientific blockers remain unchanged.

Submitted20:53:22 Asia/Saigon; native inference finished21:55:37 on2026-10-23.
Platform COMPLETE observed22:55:57 that day; exact platform completion clock
was not observed. GPU quota16.956826111h at check, zero reserved. Account change
from prelaunch is1.039825000h, not invoice cost or a general billing rule.

## Next work

No further B1/B2 generation session is required. T5.4 remains: canonical
adaptation, privacy/cost review, separately authorized/budgeted predicted and
gold BigQuery execution, reports and comparisons. The campaign plan explicitly
reserves BigQuery project/location, query/aggregate byte/USD caps and pricing
policy for a later independent authorization. This review does not start those
jobs or infer authorization from “next process if needed.” Offline preparation
can use these retained artifacts without spending another GPU session.

Existing B0 genuine0/100 is English-only; it is not a VI control. No VI B0,
B3, training, constrained decoding, demo or Phase6–7 session is implied. Preserve
both setup failures and all invalid/unsafe/prose outputs. No extra replicate,
retry, partial-run merge or replacement03 is scheduled.

[Independent registry](../evidence/kaggle-b12-generation-matrix-2026-10-23.json),
[per-run CSV](../evidence/kaggle-b12-generation-matrix-2026-10-23/native-runs.csv),
[audit source](../evidence/kaggle-b12-generation-matrix-2026-10-23/audit_campaign.py),
[final replacement evidence](../evidence/kaggle-b12-benchmark-b2-en-r03-replacement02-2026-10-23.json).
