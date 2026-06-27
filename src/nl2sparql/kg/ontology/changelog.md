# Ethereum KG Ontology Changelog

## v0.1.0 — 2026-06-27

- Added local namespace `https://thesis.example.org/eth-kg/`.
- Added EthOn-based account, DeFi protocol, transaction, block, and token transfer classes.
- Added 17 local classes covering account labels, centralized exchanges, mixers, DEX protocols, lending protocols, bridge protocols, NFT marketplaces, token contracts, transactions, blocks, token transfers, and protocol interactions.
- Added 30 local properties with schema-linker-ready metadata: `rdfs:label`, two-sentence `rdfs:comment`, `:synonyms`, `:exampleUsage`, `rdfs:domain`, and `rdfs:range`.
- Added 30 competency questions with class/property coverage and SPARQL sketches.
- Automated validation: `rdflib` parse and metadata tests in `tests/unit/test_ontology_extension.py`.
- Manual Protégé validation: pending external GUI check with FaCT++ or HermiT.
