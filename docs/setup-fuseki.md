# Fuseki Local Setup

This project uses Apache Jena Fuseki as the local SPARQL endpoint for Plan A.
The Phase 0 smoke dataset is in-memory and named `test`.

## Start

```bash
src/nl2sparql/kg/scripts/start_fuseki.sh
```

The script uses Docker Compose, so Java only needs to exist inside the container.
The compose file uses `stain/jena-fuseki:latest`, which currently runs Apache
Jena Fuseki 5.x. This satisfies the project requirement of Fuseki 4.10+ and
avoids installing Java on the host. It starts:

```bash
./fuseki-server --update --mem /test
```

Open the admin UI at `http://localhost:3030/`.

## Upload Smoke Data

In another terminal:

```bash
curl -X POST -H "Content-Type: text/turtle" \
  -u admin:admin \
  --data-binary @src/nl2sparql/kg/validation/sample.ttl \
  http://localhost:3030/test/data
```

## Query

SPARQL endpoint:

```text
http://localhost:3030/test/sparql
```

Smoke queries are stored in:

```text
src/nl2sparql/kg/validation/smoke_queries.sparql
```

Minimal Python check:

```python
from SPARQLWrapper import JSON, SPARQLWrapper

sw = SPARQLWrapper("http://localhost:3030/test/sparql")
sw.setReturnFormat(JSON)
sw.setQuery("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")
print(sw.query().convert())
```

## Stop

Press `Ctrl+C` in the terminal running Fuseki, or run:

```bash
docker compose -f infrastructure/docker/docker-compose.fuseki.yml down
```

The `/test` dataset is in-memory, so uploaded data is lost after shutdown.
Phase 2 will switch to persistent TDB2 storage.
