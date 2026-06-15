# Related Work Notes

> Working notes for thesis Chapter 2. Verify exact venue/page metadata again before final submission.

## Nhóm A — NL2SPARQL Classic

### [2017] Trivedi et al. — LC-QuAD

- **Venue:** ISWC.
- **Problem:** Build a benchmark for complex natural-language questions over DBpedia that require SPARQL rather than keyword lookup.
- **Approach:** The dataset pairs natural language questions with SPARQL queries and targets complex patterns such as joins, constraints, and aggregations. It is useful as a template source, but it is open-domain and DBpedia-specific.
- **Dataset/KG:** DBpedia, about 5k questions.
- **Result:** Primarily a dataset contribution; downstream systems report accuracy/F1 against it.
- **Code/Data:** https://github.com/AskNowQA/LC-QuAD
- **Relevance to us:** It motivates template-driven NL-SPARQL benchmark construction. The gap is that blockchain entities, address clusters, and DeFi concepts are absent.

### [2019] Dubey et al. — LC-QuAD 2.0

- **Venue:** ISWC / Semantic Web dataset resource.
- **Problem:** Extend complex QA coverage to both Wikidata and DBpedia with larger query diversity.
- **Approach:** LC-QuAD 2.0 expands question patterns and supports Wikidata-style identifiers, making entity/relation linking harder than LC-QuAD 1.0. It shows why benchmark design must include multiple query structures rather than only simple fact lookup.
- **Dataset/KG:** Wikidata and DBpedia, roughly 30k questions.
- **Result:** Dataset benchmark, not a single model result.
- **Code/Data:** https://lc-quad.sda.tech/
- **Relevance to us:** Strong precedent for synthetic/template dataset generation. It does not address temporal blockchain analytics or multi-address-one-entity resolution.

### [2022] Perevalov et al. — QALD-9-plus

- **Venue:** arXiv / QALD benchmark extension.
- **Problem:** Multilingual KGQA lacks high-quality translated benchmarks with aligned SPARQL queries.
- **Approach:** The authors extend QALD-9 with native-speaker translations and port queries between DBpedia and Wikidata. The work emphasizes benchmark usability and answer consistency across KGs.
- **Dataset/KG:** DBpedia and Wikidata.
- **Result:** Dataset contribution with multilingual coverage.
- **Code/Data:** https://github.com/Perevalov/qald_9_plus
- **Relevance to us:** Shows how dataset quality and portability matter more than model novelty alone. Our thesis stays English-only but can borrow the careful benchmark-card style.

### [2018] Hartmann et al. — DBNQA

- **Venue:** LDOW.
- **Problem:** Neural SPARQL parsers need far more training pairs than manually curated KGQA datasets provide.
- **Approach:** The work generates a large DBpedia Neural Question Answering dataset from templates and semi-automatic annotation. It favors scale but inherits noise and template bias.
- **Dataset/KG:** DBpedia, hundreds of thousands of question-SPARQL pairs.
- **Result:** Dataset resource for neural KGQA.
- **Code/Data:** https://github.com/AKSW/DBNQA
- **Relevance to us:** Supports using synthetic data, but warns that large synthetic data must be validated by execution and manual review.

### [2017] Soru et al. — SPARQL as a Foreign Language

- **Venue:** SEMANTiCS.
- **Problem:** Treat SPARQL generation as neural translation from natural language to a formal language.
- **Approach:** The work trains sequence-to-sequence models on question-query pairs, framing SPARQL as the target language. This line of work is simple but vulnerable to invalid syntax and schema hallucination.
- **Dataset/KG:** DBpedia-derived question-SPARQL data.
- **Result:** Early neural baseline for NL2SPARQL.
- **Code/Data:** https://ceur-ws.org/Vol-2044/paper14/paper14.html
- **Relevance to us:** This is the ancestor of the B3 fine-tuning idea. Our planned validator and constrained decoding address its main failure modes.

## Nhóm B — KGQA + LLM

### [2024] Li et al. — UniOQA

- **Venue:** arXiv.
- **Problem:** LLM-based KGQA needs both executable query generation and answer robustness.
- **Approach:** UniOQA combines LLM semantic parsing to graph queries with a complementary RAG/direct-answer path. It also uses entity/relation replacement to improve executability.
- **Dataset/KG:** OwnThink / CQL-oriented KGQA benchmark.
- **Result:** Reports 21.2% logical accuracy and 54.9% execution accuracy on SpCQL.
- **Code/Data:** https://arxiv.org/abs/2406.02110
- **Relevance to us:** It supports a hybrid pipeline instead of raw LLM output. Our pipeline similarly separates linking, generation, validation, and execution.

### [2024] Schneider et al. — LLMs for Conversational KGQA Semantic Parsing

- **Venue:** arXiv.
- **Problem:** Evaluate whether general LLMs can generate structured graph queries for conversational KGQA.
- **Approach:** The paper compares prompting and fine-tuning settings and analyzes common failure cases. It finds that LLMs can help, but structured-query validity and context carryover remain difficult.
- **Dataset/KG:** Conversational KGQA benchmark.
- **Result:** Empirical comparison of zero-shot, few-shot, and fine-tuned settings.
- **Code/Data:** https://arxiv.org/abs/2401.01711
- **Relevance to us:** Justifies our baselines B1/B2/B3 and failure-mode analysis. The domain is conversational rather than blockchain analytics.

### [2024] Srivastava et al. — MST5

- **Venue:** arXiv.
- **Problem:** Multilingual users are under-served by KGQA systems that mostly target English.
- **Approach:** MST5 uses a multilingual T5-style model with linguistic context and entity information to generate SPARQL. It evaluates on QALD-9-plus and QALD-10 plus additional languages.
- **Dataset/KG:** QALD datasets.
- **Result:** Improves multilingual KGQA performance against prior baselines.
- **Code/Data:** https://arxiv.org/abs/2407.06041
- **Relevance to us:** Entity context injection is directly relevant to schema/entity linking. We keep language scope narrow but borrow the idea of explicit context in prompts.

### [2023] Xu et al. — WikiWebQuestions

- **Venue:** arXiv.
- **Problem:** LLMs hallucinate factual answers when not grounded in a KG.
- **Approach:** The authors port WebQuestions to Wikidata SPARQL and fine-tune LLaMA-style models for semantic parsing. They compare parser-only answers with GPT-assisted answering.
- **Dataset/KG:** Wikidata, WikiWebQuestions.
- **Result:** Reports 76% dev and 65% test answer accuracy for the semantic parser baseline.
- **Code/Data:** https://arxiv.org/abs/2305.14202
- **Relevance to us:** Strong support for fine-tuning smaller/open models on KG-grounded SPARQL. Their use of property names rather than IDs is relevant to ontology documentation.

### [2023] Perez-Beltrachini et al. — Conversational KGQA Semantic Parsing

- **Venue:** arXiv.
- **Problem:** Multi-turn KGQA requires semantic parsing across dialogue context, not isolated single questions.
- **Approach:** The paper studies semantic parsing representations for conversational KGQA and shows the need for context-aware structured queries. It broadens evaluation beyond one-shot question answering.
- **Dataset/KG:** Conversational KGQA data.
- **Result:** Benchmark/model analysis for conversational semantic parsing.
- **Code/Data:** https://arxiv.org/abs/2301.12217
- **Relevance to us:** Our v1 excludes multi-turn dialogue, which should be stated as a limitation. Pipeline trace in the demo can still borrow transparency ideas.

## Nhóm C — Text-to-SQL

### [2018] Yu et al. — Spider

- **Venue:** EMNLP.
- **Problem:** Text-to-SQL models overfit to seen schemas and simple single-domain datasets.
- **Approach:** Spider introduces cross-domain train/test splits across 200 databases. It evaluates exact-match and execution-oriented generalization.
- **Dataset/KG:** SQL databases, 10,181 questions and 5,693 unique SQL queries.
- **Result:** Early best model achieved only 12.4% exact match under database split.
- **Code/Data:** https://yale-lily.github.io/spider
- **Relevance to us:** Spider informs Plan B and evaluation design. The schema generalization problem maps to ontology/property linking in SPARQL.

### [2023] Li et al. — BIRD

- **Venue:** arXiv.
- **Problem:** Existing text-to-SQL benchmarks are too small and clean compared with real large databases.
- **Approach:** BIRD includes large databases, domain knowledge, dirty values, and efficiency concerns. It evaluates whether LLMs can act as practical database interfaces.
- **Dataset/KG:** 12,751 pairs, 95 databases, 33.4GB, 37 domains.
- **Result:** ChatGPT achieved 40.08% execution accuracy while humans reached 92.96%.
- **Code/Data:** https://bird-bench.github.io/
- **Relevance to us:** Useful for Plan B and for cost/latency evaluation. It reinforces that real data values and entity grounding are essential.

### [2023] Pourreza and Rafiei — DIN-SQL

- **Venue:** arXiv.
- **Problem:** Direct few-shot prompting is brittle for complex text-to-SQL reasoning.
- **Approach:** DIN-SQL decomposes generation into subtasks and adds self-correction. The decomposition improves LLM reasoning and error isolation.
- **Dataset/KG:** Spider and BIRD.
- **Result:** Reports 85.3% Spider execution accuracy and 55.9% BIRD execution accuracy at publication time.
- **Code/Data:** https://arxiv.org/abs/2304.11015
- **Relevance to us:** Supports decomposed NL2SPARQL stages: linking, generation, validation, recovery. This is a direct design analogy.

### [2023] Gao et al. — DAIL-SQL

- **Venue:** arXiv.
- **Problem:** LLM text-to-SQL performance depends strongly on prompt representation and example selection.
- **Approach:** DAIL-SQL benchmarks prompt engineering choices and proposes an integrated prompt strategy with token efficiency concerns. It also studies open-source LLM fine-tuning.
- **Dataset/KG:** Spider and related text-to-SQL datasets.
- **Result:** Reports 86.6% Spider execution accuracy.
- **Code/Data:** https://arxiv.org/abs/2308.15363
- **Relevance to us:** Supports the planned few-shot baseline and prompt ablation. We should log prompt token length/cost as part of evaluation.

### [2021] Scholak et al. — PICARD

- **Venue:** arXiv / EMNLP-era constrained decoding work.
- **Problem:** Seq2seq models often generate syntactically invalid SQL.
- **Approach:** PICARD incrementally parses partial outputs during decoding and rejects invalid continuations. This constrains generation without retraining the base model.
- **Dataset/KG:** Spider and CoSQL.
- **Result:** Improves validity and execution accuracy for T5-based text-to-SQL systems.
- **Code/Data:** https://arxiv.org/abs/2109.05093
- **Relevance to us:** Direct precedent for SPARQL constrained decoding. Our grammar module should be evaluated on syntax-error reduction.

### [2020] Wang et al. — RAT-SQL

- **Venue:** ACL.
- **Problem:** Text-to-SQL parsers need explicit schema linking and relation-aware schema encoding.
- **Approach:** RAT-SQL models relations among question tokens, tables, and columns, using schema linking signals. It became a strong pre-LLM baseline.
- **Dataset/KG:** Spider.
- **Result:** Strong Spider exact-match results at the time.
- **Code/Data:** https://aclanthology.org/2020.acl-main.677/
- **Relevance to us:** Schema linking is a first-class model component, not an afterthought. This supports RQ2 on measuring linker contribution.

## Nhóm D — Blockchain KG / Analytics

### [2020] Ugarte-Rojas and Chullo-Llave — BLONDiE

- **Venue:** arXiv.
- **Problem:** Blockchain platforms lack a unified semantic model for blocks, transactions, and related concepts.
- **Approach:** BLONDiE defines an extensible ontology for Bitcoin, Ethereum, and Hyperledger Fabric. It targets common semantic representation and SPARQL queries across chains.
- **Dataset/KG:** Blockchain ontology, not a single extracted Ethereum month.
- **Result:** Ontology contribution.
- **Code/Data:** https://arxiv.org/abs/2008.09518
- **Relevance to us:** Useful ontology reference, but broader than our Ethereum analytics scope. We need DeFi/entity-label extensions beyond chain-native structures.

### [2023] Konig and Neumaier — Distributed Ledger Technology KG

- **Venue:** arXiv.
- **Problem:** DLT knowledge is fragmented across technologies, standards, vulnerabilities, and application domains.
- **Approach:** The authors build an ontology and knowledge graph for distributed ledger technologies with semantic web best practices. It focuses more on technology classification than transaction-level analytics.
- **Dataset/KG:** DLT ontology/KG.
- **Result:** Published KG and ontology resource.
- **Code/Data:** https://arxiv.org/abs/2303.16528
- **Relevance to us:** Shows how to document ontology methodology. It does not solve NL2SPARQL or Ethereum transaction querying.

### [2020] Sharma and Bhatia — Bitcoin Graph Analytics

- **Venue:** arXiv.
- **Problem:** Blockchain transaction data can be analyzed as graphs to infer patterns and behaviors.
- **Approach:** The paper reviews graph-theoretic perspectives for Bitcoin analytics and proposes analytics workflows. It is not RDF/SPARQL-specific.
- **Dataset/KG:** Bitcoin transaction graph.
- **Result:** Framework and use-case analysis.
- **Code/Data:** https://arxiv.org/abs/2002.06403
- **Relevance to us:** Motivates graph analytics use cases. Our contribution differs by exposing analytics through NL2SPARQL over RDF.

### [2013] Meiklejohn et al. — A Fistful of Bitcoins

- **Venue:** IMC.
- **Problem:** Bitcoin pseudonymity can be weakened by transaction graph analysis and service attribution.
- **Approach:** The paper clusters addresses and links them to real-world services using graph heuristics and manual interaction. It is an early foundation for blockchain entity attribution.
- **Dataset/KG:** Bitcoin blockchain and tagged services.
- **Result:** Demonstrates practical deanonymization and service clustering.
- **Code/Data:** https://doi.org/10.1145/2504730.2504747
- **Relevance to us:** Strong support for entity dictionary and multi-address-one-entity modeling. Ethereum and DeFi introduce different address and contract patterns.

### [2015] ConsenSys — EthOn

- **Venue:** Ontology/resource.
- **Problem:** Ethereum concepts need RDF/OWL-style representation for semantic web tooling.
- **Approach:** EthOn provides an Ethereum ontology baseline for accounts, blocks, transactions, and related structures. It is a starting point rather than a complete analytics KG.
- **Dataset/KG:** Ethereum ontology.
- **Result:** Reusable ontology resource.
- **Code/Data:** https://github.com/ConsenSys/EthOn
- **Relevance to us:** This is the planned base ontology. We need to extend it with labels, aliases, DeFi classes, and SHACL constraints.

## Nhóm E — Entity Linking + Schema Linking

### [2018] Dubey et al. — EARL

- **Venue:** arXiv / KGQA linking.
- **Problem:** Entity and relation linking errors are a major bottleneck in KGQA.
- **Approach:** EARL jointly solves entity and relation linking instead of treating them as independent sequential tasks. It uses graph connectivity and ranking features.
- **Dataset/KG:** DBpedia QA datasets with 5,000 questions.
- **Result:** Outperforms prior entity/relation linking baselines.
- **Code/Data:** https://arxiv.org/abs/1801.03825
- **Relevance to us:** Direct support for combined schema/entity linking. Our version must adapt to Ethereum aliases and address clusters.

### [2019] Sakor et al. — Falcon 2.0

- **Venue:** arXiv / ISWC-style resource.
- **Problem:** Wikidata text requires joint entity and relation linking for short natural-language inputs.
- **Approach:** Falcon 2.0 uses linguistic preprocessing, candidate generation, and optimization to link entities and relations to Wikidata IRIs. It exposes an API and reusable resources.
- **Dataset/KG:** Wikidata.
- **Result:** Reported gains over existing Wikidata linking baselines.
- **Code/Data:** https://labs.tib.eu/falcon/falcon2/
- **Relevance to us:** Useful architecture reference for returning ranked candidates with URIs. Blockchain dictionaries will be far smaller but more domain-specific.

### [2019] Wu et al. — BLINK

- **Venue:** arXiv / Facebook AI.
- **Problem:** Entity linking needs both scalability to millions of candidates and zero-shot ability.
- **Approach:** BLINK uses a bi-encoder for dense retrieval and a cross-encoder for reranking. It shows the accuracy/latency trade-off clearly.
- **Dataset/KG:** Wikipedia/Wikidata-style entity linking benchmarks.
- **Result:** State-of-the-art gains on zero-shot and standard linking benchmarks; reports fast retrieval over millions of candidates.
- **Code/Data:** https://github.com/facebookresearch/BLINK
- **Relevance to us:** Supports embedding retrieval plus reranking, but our 5k-entity dictionary may use simpler fuzzy + embedding stages.

### [2011] Mendes et al. — DBpedia Spotlight

- **Venue:** SEMANTiCS.
- **Problem:** Web documents need automatic annotation with DBpedia resources.
- **Approach:** Spotlight combines mention detection, candidate generation, and disambiguation for DBpedia entities. It became a common semantic annotation baseline.
- **Dataset/KG:** DBpedia.
- **Result:** Tool/resource contribution.
- **Code/Data:** https://www.dbpedia-spotlight.org/
- **Relevance to us:** Provides the classic pipeline structure for entity linking. It is open-domain and not enough for Ethereum addresses/protocol aliases.

### [2011] Yosef et al. — AIDA

- **Venue:** PVLDB.
- **Problem:** Named entities in text and tables need accurate disambiguation to a knowledge base.
- **Approach:** AIDA uses graph coherence among candidate entities plus context similarity. Collective disambiguation is central.
- **Dataset/KG:** YAGO/Wikipedia-style KB.
- **Result:** Tool contribution with strong disambiguation performance at the time.
- **Code/Data:** https://www.vldb.org/pvldb/vol4/p1450-yosef.pdf
- **Relevance to us:** Coherence is relevant when a question contains multiple entities such as exchange, mixer, and token. We may defer collective inference unless simple linking is insufficient.

## Nhóm F — Synthetic Data Generation for Semantic Parsing

### [2015] Wang et al. — Overnight

- **Venue:** ACL-IJCNLP.
- **Problem:** Semantic parsers are expensive to build for each new domain.
- **Approach:** Overnight generates canonical utterances from logical forms and uses crowdsourcing to paraphrase them into natural language. This reduces annotation cost while retaining executable semantics.
- **Dataset/KG:** Eight domains with lambda-DCS logical forms.
- **Result:** Demonstrates rapid domain adaptation for semantic parsers.
- **Code/Data:** https://nlp.stanford.edu/software/sempre/
- **Relevance to us:** Closest conceptual match to template → paraphrase → validate dataset generation. Our use of execution filtering follows the same spirit.

### [2016] Jia and Liang — Data Recombination

- **Venue:** arXiv / ACL-era semantic parsing.
- **Problem:** Neural parsers need more compositional examples than small supervised datasets provide.
- **Approach:** The method recombines existing logical forms and utterances to generate new training pairs. It targets compositional generalization rather than only surface paraphrase variety.
- **Dataset/KG:** Semantic parsing benchmarks.
- **Result:** Improves parser robustness through synthetic recombination.
- **Code/Data:** https://arxiv.org/abs/1606.03622
- **Relevance to us:** Suggests balancing template distribution and compositional variety. We should avoid letting a few entities/templates dominate.

### [2016] Narayan et al. — Paraphrase Generation for Semantic Parsing

- **Venue:** arXiv.
- **Problem:** Semantic parsers fail when user wording differs from KB predicate wording.
- **Approach:** The paper generates paraphrases with latent-variable PCFGs and evaluates them extrinsically through semantic parsing. It treats paraphrasing as a bridge over lexical mismatch.
- **Dataset/KG:** Freebase/WebQuestions.
- **Result:** Paraphrases improve semantic parser performance over strong baselines.
- **Code/Data:** https://arxiv.org/abs/1601.06068
- **Relevance to us:** Supports paraphrasing synthetic questions. Our domain-specific terms like "mixer", "bridge", and "whale tx" need explicit paraphrase coverage.

### [2020] Tran and Tan — Synthetic Data for Task-Oriented Semantic Parsing

- **Venue:** arXiv.
- **Problem:** Hierarchical task-oriented semantic parsing lacks labeled data in new domains.
- **Approach:** The authors use BART to generate synthetic utterances from masked templates, then filter them with an auxiliary parser. Filtering is key to quality.
- **Dataset/KG:** Facebook TOP-style semantic parsing.
- **Result:** Shows synthetic data can help when filtered for semantic consistency.
- **Code/Data:** https://arxiv.org/abs/2011.02050
- **Relevance to us:** Reinforces the need for validation after paraphrasing/noise injection. Our validator should reject non-executable SPARQL.

### [2021] Wu et al. — Synchronous Semantic Decoding

- **Venue:** arXiv.
- **Problem:** Unsupervised semantic parsing must bridge both structural and lexical gaps.
- **Approach:** SSD jointly generates canonical utterances and meaning representations under constraints. It frames parsing as constrained paraphrasing.
- **Dataset/KG:** Multiple semantic parsing datasets.
- **Result:** Competitive unsupervised parsing results.
- **Code/Data:** https://arxiv.org/abs/2106.06228
- **Relevance to us:** Supports constrained decoding and canonical utterance design. Full unsupervised parsing is out of scope.

### [2026] Sterbentz et al. — RingSQL

- **Venue:** arXiv.
- **Problem:** Text-to-SQL training data remains scarce, and existing synthetic approaches trade correctness for scale.
- **Approach:** RingSQL combines schema-independent SQL templates with LLM paraphrasing. It keeps SQL correctness while adding linguistic diversity.
- **Dataset/KG:** Six text-to-SQL benchmarks.
- **Result:** Reports an average +2.3% accuracy gain across benchmarks.
- **Code/Data:** https://arxiv.org/abs/2601.05451
- **Relevance to us:** Very close to our template + paraphrase approach, but for SQL and later than many baselines. It strengthens the argument for correctness-preserving synthetic generation.

## Gaps Identified

1. **No blockchain-specific NL2SPARQL benchmark:** Existing NL2SPARQL datasets focus on DBpedia/Wikidata, not Ethereum transactions, contracts, exchanges, mixers, or DeFi protocols.
2. **Weak treatment of multi-address real-world entities:** Classic KGQA linking maps mentions to one KG entity, while blockchain analytics often maps one organization to many addresses and aliases.
3. **Limited schema-linking analysis for domain ontologies:** Text-to-SQL literature measures schema linking heavily, but KGQA papers often hide ontology/property linking inside end-to-end scores.
4. **Few reproducible small-LLM vs large-LLM trade-off studies for KGQA:** Recent work uses LLMs, but not often with cost, latency, privacy, and reproducibility side by side on a domain KG.
5. **Little execution-validated synthetic SPARQL data for specialized KGs:** Synthetic semantic parsing exists, but blockchain KG questions need execution filtering against real graph data and domain-specific entity sampling.
6. **Demo transparency gap:** Many KGQA systems report answer accuracy but expose little trace of entity linking, schema linking, generated SPARQL, validation, and execution provenance to non-technical users.
