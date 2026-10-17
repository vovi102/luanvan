#!/usr/bin/env python
"""CPU-only cache acquisition and byte verification; never load a model or run inference."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

import click

REPOSITORIES = {
    "model": "meta-llama/Meta-Llama-3-8B-Instruct",
    "encoder": "sentence-transformers/all-MiniLM-L6-v2",
}


class SetupError(ValueError):
    """A setup artifact or explicit operational gate is missing."""


def load_pins(path: Path) -> dict:
    document = json.loads(path.read_bytes())
    if document["schema_version"] != 1 or set(document["models"]) != set(REPOSITORIES):
        raise SetupError("model pin schema mismatch")
    for component, repo in REPOSITORIES.items():
        model = document["models"][component]
        if model["repo_id"] != repo or not re.fullmatch("[0-9a-f]{40}", model["revision"]):
            raise SetupError("research identity or revision mismatch")
        if not model["files"]:
            raise SetupError("pin file inventory is empty")
        for name, evidence in model["files"].items():
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or str(path) != name
                or any(p in {"..", "."} for p in name.split("/"))
            ):
                raise SetupError("unsafe cache relative path")
            length = {"sha256": 64, "git-blob-sha1": 40}.get(evidence["algorithm"])
            if length is None or not re.fullmatch(
                "[0-9a-f]{" + str(length) + "}", evidence["digest"]
            ):
                raise SetupError("invalid expected file digest")
            if type(evidence["bytes"]) is not int or evidence["bytes"] <= 0:
                raise SetupError("invalid expected file size")
    return document


def verify_cache(pins: dict, home: Path, component: str) -> dict:
    results = {}
    for kind in REPOSITORIES if component == "all" else (component,):
        model = pins["models"][kind]
        folder = (
            home
            / "hub"
            / ("models--" + model["repo_id"].replace("/", "--"))
            / "snapshots"
            / model["revision"]
        )
        for name, evidence in model["files"].items():
            path = folder / name
            if not path.resolve().is_relative_to(home.resolve()):
                raise SetupError("cache file escapes HF_HOME")
            if not path.is_file() or path.stat().st_size != evidence["bytes"]:
                raise SetupError(f"missing or wrong-size cache file: {kind}/{name}")
            digest = hashlib.sha256() if evidence["algorithm"] == "sha256" else hashlib.sha1()
            if evidence["algorithm"] == "git-blob-sha1":
                digest.update(f"blob {evidence['bytes']}\0".encode())
            with path.open("rb") as handle:
                while block := handle.read(2 * 1024 * 1024):
                    digest.update(block)
            if digest.hexdigest() != evidence["digest"]:
                raise SetupError(f"cache fingerprint mismatch: {kind}/{name}")
        results[kind] = {
            "repo_id": model["repo_id"],
            "revision": model["revision"],
            "files_verified": len(model["files"]),
            "snapshot": str(folder),
        }
    return {
        "status": "cache_bytes_verified",
        "models": results,
        "model_loaded": False,
        "scientific_ready": False,
    }


def fetch_cache(
    pins: dict, home: Path, component: str, *, allowed: bool, token_stdin: bool
) -> dict:
    if not allowed:
        raise SetupError("downloads require explicit --allow-downloads")
    kinds = tuple(REPOSITORIES) if component == "all" else (component,)
    token = False
    if "model" in kinds:
        if not home.resolve().is_relative_to(Path("/kaggle/working")):
            raise SetupError(
                "Llama acquisition is restricted to /kaggle/working; no local 8B download"
            )
        if not token_stdin:
            raise SetupError(
                "gated model requires --token-stdin from Kaggle Secrets; never argv/env"
            )
        token = sys.stdin.read().strip()
        if not token:
            raise SetupError("empty gated-model token")
    elif token_stdin:
        raise SetupError("public encoder must not receive a token")
    # Explicit cache and token=False for public files prevent ambient credential lookup.
    os.environ["HF_HOME"] = str(home.resolve())
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "0"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    import requests
    from huggingface_hub import configure_http_backend, hf_hub_download

    def session():
        result = requests.Session()
        result.trust_env = False  # No netrc, credential-bearing proxies or ambient auth.
        return result

    configure_http_backend(backend_factory=session)
    for kind in kinds:
        model = pins["models"][kind]
        try:
            for name in model["files"]:
                hf_hub_download(
                    repo_id=model["repo_id"],
                    revision=model["revision"],
                    filename=name,
                    cache_dir=home / "hub",
                    token=token if kind == "model" else False,
                )
        except Exception:
            raise SetupError(
                f"{kind} download failed; check access/network without printing tokens"
            ) from None
    return verify_cache(pins, home, component)


def emit(document: dict) -> None:
    click.echo(json.dumps(document, sort_keys=True))


@click.group()
def cli():
    """Inspect pins, explicitly acquire files, or verify a cache without loading it."""


@cli.command("inspect")
@click.option("--pins", type=click.Path(path_type=Path), required=True)
def inspect(pins: Path):
    value = load_pins(pins)
    emit(
        {
            "status": "pins_only_not_downloaded",
            "models": value["models"],
            "model_loaded": False,
            "scientific_ready": False,
        }
    )


@cli.command("verify-cache")
@click.option("--pins", type=click.Path(path_type=Path), required=True)
@click.option("--hf-home", type=click.Path(path_type=Path), required=True)
@click.option("--component", type=click.Choice(["all", "model", "encoder"]), default="all")
def verify(pins: Path, hf_home: Path, component: str):
    try:
        emit(verify_cache(load_pins(pins), hf_home, component))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        emit(
            {
                "status": "blocked",
                "error": str(exc),
                "model_loaded": False,
                "scientific_ready": False,
            }
        )
        raise click.exceptions.Exit(2) from None


@cli.command("fetch-cache")
@click.option("--pins", type=click.Path(path_type=Path), required=True)
@click.option("--hf-home", type=click.Path(path_type=Path), required=True)
@click.option("--component", type=click.Choice(["all", "model", "encoder"]), default="all")
@click.option("--allow-downloads", is_flag=True)
@click.option("--token-stdin", is_flag=True)
def fetch(pins: Path, hf_home: Path, component: str, allow_downloads: bool, token_stdin: bool):
    try:
        emit(
            fetch_cache(
                load_pins(pins),
                hf_home,
                component,
                allowed=allow_downloads,
                token_stdin=token_stdin,
            )
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        emit(
            {
                "status": "blocked",
                "error": str(exc),
                "model_loaded": False,
                "scientific_ready": False,
            }
        )
        raise click.exceptions.Exit(2) from None


if __name__ == "__main__":
    cli()
