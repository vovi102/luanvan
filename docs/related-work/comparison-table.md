# Related Work Comparison Table

| Paper | KG/Schema | Dataset size | Model / Method | Metric + value | Schema linking | Domain | Code available |
|---|---|---:|---|---|---|---|---|
| LC-QuAD 2.0 (2019) | DBpedia + Wikidata | ~30k questions | Dataset/templates | Dataset resource | Y, implicit via SPARQL relations | Open-domain KGQA | Data: https://lc-quad.sda.tech/ |
| QALD-9-plus (2022) | DBpedia + Wikidata | QALD-9 extension | Multilingual benchmark | Dataset resource | Y, gold SPARQL | Open-domain multilingual KGQA | Data: https://github.com/Perevalov/qald_9_plus |
| WikiWebQuestions (2023) | Wikidata | WebQuestions-derived | Fine-tuned LLaMA semantic parser | 76% dev / 65% test answer accuracy | Y, entity linker and property names | Open-domain KGQA | Paper: https://arxiv.org/abs/2305.14202 |
| UniOQA (2024) | OwnThink / CQL KG | Benchmark-specific | LLM parser + RAG/direct answer | 54.9% execution accuracy | Y, entity/relation replacement | Chinese open-domain KGQA | Paper: https://arxiv.org/abs/2406.02110 |
| MST5 (2024) | QALD KGs | QALD-9-plus/QALD-10 | Multilingual T5-style parser | Improves QALD multilingual scores | Y, entity context | Multilingual KGQA | Paper: https://arxiv.org/abs/2407.06041 |
| Spider (2018) | 200 SQL DB schemas | 10,181 questions | Cross-domain text-to-SQL dataset | Early best 12.4% exact match | Y, table/column linking | Cross-domain SQL | Data: https://yale-lily.github.io/spider |
| BIRD (2023) | 95 SQL DBs, 33.4GB | 12,751 pairs | Large DB-grounded benchmark | ChatGPT 40.08% exec acc; human 92.96% | Y, values + schema | Realistic SQL | Code/data: https://bird-bench.github.io/ |
| DIN-SQL (2023) | SQL schemas | Spider/BIRD | Decomposed prompting + self-correction | 85.3% Spider exec; 55.9% BIRD exec | Y, decomposition includes schema reasoning | SQL | Paper: https://arxiv.org/abs/2304.11015 |
| DAIL-SQL (2023) | SQL schemas | Spider + benchmarks | Prompt engineering + example selection | 86.6% Spider exec acc | Y, prompt representation | SQL | Paper: https://arxiv.org/abs/2308.15363 |
| PICARD (2021) | SQL grammar/schema | Spider/CoSQL | Incremental constrained decoding | Validity and exec-acc improvements | Partial, grammar focused | SQL | Code: https://github.com/ServiceNow/picard |
| BLONDiE (2020) | Blockchain ontology | Ontology resource | OWL/RDF ontology | Ontology contribution | N/A | Blockchain | Paper: https://arxiv.org/abs/2008.09518 |
| DLT Knowledge Graph (2023) | DLT ontology/KG | KG resource | Semantic web ontology/KG | KG contribution | N/A | Distributed ledgers | Paper: https://arxiv.org/abs/2303.16528 |
| EARL (2018) | DBpedia | 5k questions | Joint entity + relation linking | Outperforms prior linking baselines | Y, explicit relation linking | KGQA linking | Paper: https://arxiv.org/abs/1801.03825 |
| Falcon 2.0 (2019) | Wikidata | Linking benchmarks | Joint entity/relation linker | Beats Wikidata linking baselines | Y, explicit relation linking | Entity/relation linking | Code/API: https://labs.tib.eu/falcon/falcon2/ |
| BLINK (2019) | Wikipedia/Wikidata | EL benchmarks | Bi-encoder retrieval + cross-encoder rerank | SOTA gains on zero-shot EL | Entity linking only | Entity linking | Code: https://github.com/facebookresearch/BLINK |
| Overnight (2015) | 8 domain schemas | Domain-specific | Canonical utterance + crowdsourced paraphrase | Dataset/parser contribution | Y, logical forms generated from schema | Semantic parsing | Code: https://nlp.stanford.edu/software/sempre/ |
| RingSQL (2026) | SQL schemas | 6 benchmarks | Schema-independent templates + LLM paraphrase | Avg +2.3% accuracy | Y, SQL schema-aware generation | Synthetic text-to-SQL | Code: https://github.com/nu-c3lab/RingSQL |

## Direct Lessons for This Thesis

- Use **execution accuracy** and **syntax/schema validity** rather than text similarity alone.
- Treat **schema linking** as a measurable component, following Text-to-SQL practice.
- Keep synthetic data correctness by generating SPARQL from templates first, then paraphrasing natural language.
- Add domain-specific entity handling because open-domain KGQA linkers do not model exchange/protocol address clusters.
- Include cost/latency/reproducibility columns when comparing small fine-tuned LLMs and large API LLMs.
