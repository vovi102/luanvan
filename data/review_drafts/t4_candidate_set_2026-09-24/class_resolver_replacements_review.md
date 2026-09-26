# T4.3 replacement review — 2026-09-26

**Status:** `DRAFT — agent-authored; requires human review`

These 15 rows replace the rejected semantic duplicates in
`class_resolver_candidates.jsonl`. Record `ACCEPT`, `REVISE`, or `REJECT` for
`resolver-candidate-36` through `resolver-candidate-50` in
`review_decisions.csv`.

| ID | Group | Question | Expected semantics | Plan status |
|---|---|---|---|---|
| resolver-candidate-36 | ambiguous / fail-closed | Show activity involving Bitmex in June 2026. | Bitmex → unresolved / unspecified / unresolved | unresolved |
| resolver-candidate-37 | ambiguous / fail-closed | Show activity involving Bitrue in June 2026. | Bitrue → unresolved / unspecified / unresolved | unresolved |
| resolver-candidate-38 | ambiguous / fail-closed | Show activity involving Bitstamp in June 2026. | Bitstamp → unresolved / unspecified / unresolved | unresolved |
| resolver-candidate-39 | missing direction | Show activity involving Binance in June 2026. | Binance → instance / unspecified / supported | partial |
| resolver-candidate-40 | conflicting direction | Show token transfers from and to Bitfinex in June 2026. | Bitfinex → instance / unspecified / supported | partial |
| resolver-candidate-41 | conflicting direction | List transactions received by and sent by Bitget in June 2026. | Bitget → instance / unspecified / supported | partial |
| resolver-candidate-42 | multi-mention | Show token transfers from Binance to Bitfinex in June 2026. | Binance → instance / from / supported; Bitfinex → instance / to / supported | resolved |
| resolver-candidate-43 | multi-mention conflict | Show token transfers from Binance and Bitfinex in June 2026. | Both owners → instance / from / supported | partial |
| resolver-candidate-44 | instance + concept | Show token transfers from Binance to exchange in June 2026. | Binance → instance / from / supported; exchange → concept / to / supported | resolved |
| resolver-candidate-45 | raw address | Show transfers from 0x1111111111111111111111111111111111111111 in June 2026. | address → instance / from / supported | resolved |
| resolver-candidate-46 | raw address | Show transfers to 0x2222222222222222222222222222222222222222 in June 2026. | address → instance / to / supported | resolved |
| resolver-candidate-47 | raw address | Find activity involving 0x3333333333333333333333333333333333333333 in June 2026. | address → instance / unspecified / supported | partial |
| resolver-candidate-48 | concept paraphrase | Show token transfers sent by bridges in June 2026. | bridge → concept / from / supported | resolved |
| resolver-candidate-49 | concept paraphrase | Show token transfers into decentralized exchanges in June 2026. | DEX → concept / to / supported | resolved |
| resolver-candidate-50 | concept paraphrase | List transactions sent out of lending protocols in June 2026. | lending → concept / from / supported | resolved |

The ambiguity rows deliberately carry competing owner/concept alternatives. No
class trigger resolves the alternatives, so the expected behavior is to fail
closed rather than silently choose the primary owner target.
