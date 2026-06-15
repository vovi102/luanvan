from importlib.metadata import version


def test_project_package_is_installable() -> None:
    assert version("nl2sparql-blockchain-kg")


def test_core_runtime_imports() -> None:
    import rdflib
    import yaml

    import nl2sparql

    assert nl2sparql.__name__ == "nl2sparql"
    assert rdflib.__name__ == "rdflib"
    assert yaml.__name__ == "yaml"
