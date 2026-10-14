# Stage A v2 large native transaction-to-class CQ audit — 2026-10-14

Status: local contract audit only. No template, catalogue, candidate, evidence,
benchmark or acceptance artifact changed; no provider call or benchmark/gold
inspection performed. Sources below are repository-owned definitions and code.
This note recommends a future correction; it does not implement one.
New provider coverage evidence is reported separately in the
[coverage audit](stage-a-v2-large-class-coverage-audit-2026-10-14.md); the
no-provider-call statement here describes this local CQ source inspection.

## Finding

`T_LARGE_TX_TO_CLASS` does not implement historical CQ21 or CQ25. CQ02 describes
its native-value threshold facet, but neither CQ02 alone nor CQ02 combined with
another existing CQ is an exact definition of the general parameterized question.
An explicit training CQ extension is the clearest full-scope correction.

The active question is: return up to `n` native transaction rows in a half-open
date window whose recipient's accepted label has `concept_class` equal to the
parameter and whose native `value_wei` is at least the parameter, ordered by
native wei descending. It projects transaction hash, timestamp, recipient
address, recipient owner, recipient class and native value. Class and threshold
are independent parameters. The current `DEXProtocol`/1 ETH example is one fill,
not the general definition. These facts come directly from
[templates.json:833](../../src/nl2sparql/dataset/templates/templates.json#L833),
[templates.json:837](../../src/nl2sparql/dataset/templates/templates.json#L837),
[templates.json:856](../../src/nl2sparql/dataset/templates/templates.json#L856),
[templates.json:858](../../src/nl2sparql/dataset/templates/templates.json#L858) and
[templates.json:878](../../src/nl2sparql/dataset/templates/templates.json#L878).

There is no source-class filter, role filter, receipt-success filter, token
transfer join, token-volume aggregation or existential output in this SQL.
The underlying labeled TVF only joins source and recipient labels by address;
it does not silently add those predicates
([label_layer.py:338](../../src/nl2sparql/sql/label_layer.py#L338)). Native facts
take `t.value` as `value_wei`, retain receipt status as a separate field, and
apply `timestamp >= start` and `timestamp < end`
([label_layer.py:163](../../src/nl2sparql/sql/label_layer.py#L163),
[label_layer.py:183](../../src/nl2sparql/sql/label_layer.py#L183)). Accordingly,
this question lists transaction values; it does not claim successful receipt of
funds. Accepted label class membership also does not itself promise an
operational protocol endpoint: the catalog distinguishes operational, treasury
and token roles, with token explicitly not assumed to be a protocol endpoint
([training catalogue:1271](../../src/nl2sparql/sql/catalog/ethereum_analytics_stage_a_v2.json#L1271)).

## Existing IDs: facet overlap versus full equivalence

| ID | Owned historical meaning | Relationship to this template |
|---|---|---|
| CQ21 | Existential mixer-to-DEX native flow; historical sketch fixes `MixerAccount`, `DEXProtocol` and a 1000 ETH inclusive threshold | Incorrect full mapping. Template permits arbitrary sender and recipient class, does not enforce mixer/DEX operational roles, returns rows, and parameterizes threshold. Even the DEX example lacks the mixer condition. |
| CQ25 | Token ranked by summed transfer amount into DEX protocols | Incorrect mapping. Template uses native transaction value, no token contract/symbol/transfer amount, and orders individual rows rather than aggregated tokens. Shared recipient-class vocabulary is insufficient. |
| CQ02 | List transactions above 1 ETH; sketch actually uses inclusive `>= 10^18` wei | Honest native-threshold facet. At the 1 ETH fill the threshold matches, but recipient-class restriction, arbitrary threshold, date window and ranked limit exceed the historical question. Do not redefine CQ02 as the complete class-level question. |
| CQ05 | Transactions received by a given account | Recipient-direction facet only. A selected class can cover many labeled accounts; the template does not take one given account as a parameter. CQ02 + CQ05 still omits the class-selection contract. |
| CQ01 | Count transactions in a time range | Time-window facet only. This template lists rows rather than counting them. |
| CQ13 | Exchange-to-DEX transactions | Partial DEX-recipient overlap for one fill, but misses the required exchange sender and general classes. |
| CQ27 | High native-value NFT marketplace interactions; sketch includes input data and strict `> 10 ETH` | Closest restricted class/value family, but only an NFTMarketplace special case. Template has arbitrary class, inclusive parameterized threshold and no input-data requirement. It is not general equivalence. |
| CQ18 / CQ19 / CQ22 / CQ26 / CQ28 / CQ29 | Contract-input interactions / transfers emitted by high-value transactions / exchange-to-lending owner ranking / bridge temporal outflow / MEV-to-DEX count ranking / tokens received then native sent to exchange | Each adds an absent contract/input, token, sender, aggregate or temporal constraint. None completes CQ02 into this template's exact question. |

Historical primary definitions and sketches:
[CQ01–CQ05, ontology:9](../../src/nl2sparql/kg/ontology/competency-questions.md#L9),
[CQ13, ontology:131](../../src/nl2sparql/kg/ontology/competency-questions.md#L131),
[CQ18–CQ19, ontology:181](../../src/nl2sparql/kg/ontology/competency-questions.md#L181),
[CQ21–CQ22, ontology:213](../../src/nl2sparql/kg/ontology/competency-questions.md#L213),
[CQ25–CQ29, ontology:253](../../src/nl2sparql/kg/ontology/competency-questions.md#L253).
The table's match judgments are this audit's comparison of those definitions
with the exact active SQL, not new meanings assigned to historical IDs.

The historical default SQL catalogue agrees with this separation: CQ02 has
`:Transaction`/`:hasValue`; CQ05 adds `:hasTo`; CQ21 has mixer/DEX semantics and
operational role requirements plus `coverage_gap`; CQ25 uses token transfer,
token dimension and token amount/symbol semantics
([default catalogue:432](../../src/nl2sparql/sql/catalog/ethereum_analytics.json#L432),
[default catalogue:435](../../src/nl2sparql/sql/catalog/ethereum_analytics.json#L435),
[default catalogue:451](../../src/nl2sparql/sql/catalog/ethereum_analytics.json#L451),
[default catalogue:455](../../src/nl2sparql/sql/catalog/ethereum_analytics.json#L455)).
The explicit training catalogue retains the same definitions
([training catalogue:1785](../../src/nl2sparql/sql/catalog/ethereum_analytics_stage_a_v2.json#L1785),
[training catalogue:1825](../../src/nl2sparql/sql/catalog/ethereum_analytics_stage_a_v2.json#L1825),
[training catalogue:2095](../../src/nl2sparql/sql/catalog/ethereum_analytics_stage_a_v2.json#L2095),
[training catalogue:2187](../../src/nl2sparql/sql/catalog/ethereum_analytics_stage_a_v2.json#L2187)).
CQ31–CQ34 cover native funding followed by token movement, owner net native
flow, owner recipient-count concentration, and treasury token diversity;
none is this general recipient-class threshold list
([training catalogue:2323](../../src/nl2sparql/sql/catalog/ethereum_analytics_stage_a_v2.json#L2323)).

## Why current static validation permits the mismatch

Template validation explicitly loads the training catalogue, then validates
that CQ IDs exist and disallows CQ24; it does not compare a template's SQL
predicates, result unit or aggregation with the CQ question. It also does not
reject all `coverage_gap` annotations. Thus current CQ21/CQ25 references can
pass the static reference check without being semantically correct
([validate.py:149](../../src/nl2sparql/dataset/templates/validate.py#L149),
[validate.py:307](../../src/nl2sparql/dataset/templates/validate.py#L307)).

Catalogue validation checks statuses, known relation/join/semantic references,
role values and exact CQ IDs, not equivalence between SQL and question text
([schema.py:524](../../src/nl2sparql/sql/schema.py#L524)). It pins 1.0.0 to
CQ01–CQ30 and 1.1.0 to CQ01–CQ34, rejects unknown versions and derives exact
IDs from the selected version
([schema.py:10](../../src/nl2sparql/sql/schema.py#L10),
[schema.py:586](../../src/nl2sparql/sql/schema.py#L586),
[schema.py:713](../../src/nl2sparql/sql/schema.py#L713),
[schema.py:760](../../src/nl2sparql/sql/schema.py#L760)).

## Recommendation for a separately authorized correction

Preserve the general native-to-class SQL and its `NUMERIC '{value_wei}'`
inclusive threshold. The field's owning schema is NUMERIC, sourced from native
transactions.value; changing it to token units, FLOAT or a fixed ETH threshold
would alter the question
([training catalogue:424](../../src/nl2sparql/sql/catalog/ethereum_analytics_stage_a_v2.json#L424),
[templates.json:856](../../src/nl2sparql/dataset/templates/templates.json#L856)).

For exact CQ coverage, introduce a new GoogleSQL training CQ, provisionally
CQ35 in a separately versioned catalogue revision, with this concrete wording:

> List up to {n} native transactions with recipient label concept_class equal
> to {concept_class} and native value at least {value_wei} wei, in the half-open
> interval [{start_date}, {end_date}), ordered by native wei descending. Return
> transaction hash, timestamp, recipient address, owner, class and native wei.

Document that this is labeled recipient-class membership, permits all sender
classes, and does not assert receipt success or a particular address role.
Use `transaction_facts` and `entity_labels_v1`, the `fact_address_to_entity`
join, native value/timestamp/recipient semantics and label-class lineage.
Do not invent a new ontology term solely to fill the semantic-ID list.
Set `supported` only as schema expressibility, without asserting non-empty
data; this is the existing extension convention
([training catalogue:2347](../../src/nl2sparql/sql/catalog/ethereum_analytics_stage_a_v2.json#L2347)).

Then map this template to the new ID and remove CQ21/CQ25. CQ02 may be retained
only if the annotation policy explicitly labels it as partial facet coverage;
CQ02-only remapping is not a full-question correction. Adding CQ05, CQ01 or
CQ27 to CQ02 does not make their composition an exact existing CQ. Prefer one
explicit complete question to ambiguous facet claims.

A future revision must preserve historical 1.0.0 and training 1.1.0 snapshots,
all prior CQ meanings, and exact version-to-ID guards; add the new version/count
explicitly and pin its bytes rather than appending CQ35 under 1.1.0 or disabling
the guard. The prior revision deliberately separated historical and training
catalogues and required explicit extensions when meanings differed
([revision implementation:9](stage-a-v2-supported-intents-implementation-2026-10-14.md#L9),
[prior audit:139](stage-a-v2-hard-intent-coverage-audit-2026-10-14.md#L139)).

This metadata finding does not resolve the empty witness. The earlier revision
reports one DEXProtocol/1 ETH/day fill returning zero rows and explicitly says
that this does not establish absence for every class/window/threshold
([revision implementation:83](stage-a-v2-supported-intents-implementation-2026-10-14.md#L83)).
The template's `expect_non_empty=false` example metadata is not permission to
accept an empty Stage A witness: the shared verifier explicitly rejects an
empty single result
([templates.json:885](../../src/nl2sparql/dataset/templates/templates.json#L885),
[verify.py:163](../../src/nl2sparql/dataset/stage_a/verify.py#L163)). Preserve the
1000 records, seed 42, 350/450/200 allocation and complete non-empty acceptance
requirements; coverage feasibility remains a separate audit using the unchanged
question
([stage_a_v2.py:30](../../src/nl2sparql/dataset/stage_a_v2.py#L30),
[stage_a_v2.py:221](../../src/nl2sparql/dataset/stage_a_v2.py#L221),
[revision implementation:118](stage-a-v2-supported-intents-implementation-2026-10-14.md#L118)).
