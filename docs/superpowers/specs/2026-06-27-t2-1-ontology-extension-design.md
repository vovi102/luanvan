# T2.1 Ontology Extension Design

## Goal

Define version `v0.1.0` of the local Ethereum KG ontology extension on top of
EthOn. The extension must cover the DeFi/account concepts needed by the thesis,
provide rich property documentation for the future schema linker, and document
the competency questions the ontology is expected to support.

## Scope

T2.1 is a schema-design task. It produces the ontology artifact, changelog,
competency-question catalogue, validation tests, and memory-document updates.
It does not extract new BigQuery data, build the entity dictionary, expand RML
mapping, or load the full KG into Fuseki; those are handled by later Phase 2
tasks.

The ontology extension keeps EthOn intact and adds local classes/properties in
the `https://thesis.example.org/eth-kg/` namespace. Local terms may subclass
EthOn classes but must not override EthOn predicates.

## Architecture

`eth-kg-extension-v0.1.0.ttl` is the authoritative ontology artifact for this
task. It imports no remote resource at runtime; instead it references EthOn
IRIs by namespace so validation remains reproducible offline.

The ontology is intentionally lightweight: OWL class/property declarations,
RDFS subclass relations, domain/range assertions, and annotation properties for
schema-linking metadata. It avoids complex OWL restrictions because the KG
pipeline and later schema linker need predictable terms more than heavy
reasoning.

Automated tests validate the structural acceptance criteria with `rdflib`.
Manual Protégé/HermiT or FaCT++ validation remains documented as an external
check because the CLI environment does not provide Protégé.

## Ontology Model

The class hierarchy extends three areas:

1. accounts and labeled entities, including externally owned accounts, contract
   accounts, exchange accounts, mixer accounts, DEX protocols, lending
   protocols, token contracts, bridges, NFT marketplaces, validators, and MEV
   actors;
2. transaction/event resources, including extended transactions and token
   transfers;
3. block/protocol support classes needed for later extraction and query
   templates.

The property set is capped near 30 terms to keep the future schema-linker index
focused. It covers:

- identity and labeling: labels, aliases, owners, categories, confidence;
- native ETH transaction semantics: sender, recipient, value, gas, nonce,
  receipt status, input data, block and timestamp;
- token semantics: transfer sender/recipient, token contract, amount, token
  metadata;
- block semantics: miner/validator, gas limit, gas used, transaction count;
- meta-transaction semantics: original initiator and executor/relayer.

All value amounts in the KG remain integer-valued wei represented as
`xsd:decimal`, consistent with the existing ontology reference decision.
User-facing ETH conversion remains a linker/UI responsibility.

## Property Documentation Contract

Every ontology property in the local namespace must have:

- `rdfs:label`;
- `rdfs:comment` with at least two sentences;
- `:synonyms` containing at least three comma-separated natural-language
  phrases;
- `:exampleUsage` with a SPARQL fragment;
- `rdfs:domain`;
- `rdfs:range`.

This contract is not just documentation. Phase 4 will embed labels, comments,
synonyms, and examples to rank schema terms against natural-language questions.
The tests therefore enforce the contract mechanically.

## Competency Questions

`competency-questions.md` is written before finalizing the ontology. It contains
at least 30 questions split into trivial, medium, and hard groups. Each question
lists the classes and properties needed to answer it and includes a concise
SPARQL sketch.

Coverage is measured by whether a question can be sketched using only the
defined class/property set. The target is at least 24 covered questions out of
30; the implementation should aim to cover all listed questions unless a
question is explicitly marked as future work.

## Data Flow to Later Phases

T2.1 produces schema artifacts consumed by later tasks:

- T2.2 entity dictionary uses account classes and identity properties;
- T2.4 RML full mapping uses the transaction, block, contract, and token
  transfer properties;
- Phase 3 query templates use competency questions as seed coverage;
- Phase 4 schema linker embeds the rich documentation fields;
- Phase 5+ validators use the ontology to check generated SPARQL predicates.

The ontology file is versioned so later breaking semantic changes can be
tracked independently from mapping and dataset changes.

## Error Handling and Validation

Automated validation must fail when:

- the TTL file cannot be parsed by `rdflib`;
- the ontology has fewer than 15 local classes;
- the ontology has fewer than 25 local properties;
- any local property misses label/comment/synonyms/example/domain/range;
- a property comment has fewer than two sentences;
- synonyms contain fewer than three terms;
- competency-question coverage falls below 80%.

Manual validation must be documented in the task file: open the TTL in Protégé,
run FaCT++ or HermiT, and record whether any inconsistency was found.

## Testing and Verification

Development follows test-driven development:

1. add failing tests for TTL existence, parseability, class/property counts, and
   property metadata completeness;
2. add failing tests for competency-question count and coverage markers;
3. add the minimal ontology/docs needed to make the tests pass;
4. run the focused unit tests, then the full suite before marking the task done.

Ruff should remain clean if any Python helper code is added. If no helper code
is needed, `rdflib`-based tests are sufficient.

## Deliverables

- `src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl`
- `src/nl2sparql/kg/ontology/changelog.md`
- `src/nl2sparql/kg/ontology/competency-questions.md`
- `tests/unit/test_ontology_extension.py`
- updated `docs/memory/03-ONTOLOGY_REFERENCE.md`
- updated `docs/memory/05-DECISION_LOG.md`
- updated `docs/tasks/phase-2-kg/01-ontology-extension.md`
