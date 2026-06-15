from pathlib import Path

from rdflib import Graph

ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = ROOT / "src" / "nl2sparql" / "kg" / "validation"


def test_sample_ttl_parses_and_contains_transactions() -> None:
    graph = Graph()
    graph.parse(VALIDATION_DIR / "sample.ttl", format="turtle")

    rows = list(
        graph.query(
            """
            PREFIX : <https://thesis.example.org/eth-kg/>
            SELECT ?tx WHERE { ?tx a :Transaction }
            """
        )
    )

    assert len(rows) == 2


def test_smoke_queries_file_contains_three_queries() -> None:
    query_file = VALIDATION_DIR / "smoke_queries.sparql"
    text = query_file.read_text(encoding="utf-8")

    assert text.count("# Query ") == 3
    assert "COUNT(?tx)" in text
    assert "FILTER(?v >= 1000000000000000000)" in text


def test_start_fuseki_script_documents_dev_dataset() -> None:
    script = ROOT / "src" / "nl2sparql" / "kg" / "scripts" / "start_fuseki.sh"
    text = script.read_text(encoding="utf-8")

    assert script.stat().st_mode & 0o111
    assert "docker compose" in text
    assert "docker-compose.fuseki.yml" in text


def test_docker_compose_builds_fuseki_container() -> None:
    compose = ROOT / "infrastructure" / "docker" / "docker-compose.fuseki.yml"

    compose_text = compose.read_text(encoding="utf-8")

    assert "stain/jena-fuseki:latest" in compose_text
    assert "3030:3030" in compose_text
    assert "/jena-fuseki/fuseki-server" in compose_text
    assert "ADMIN_PASSWORD: admin" in compose_text
