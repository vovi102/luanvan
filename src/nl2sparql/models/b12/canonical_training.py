"""Lossless train projection of the accepted T3.3 publication.

This adapter deliberately supports one validated publication. A new publication
requires new evidence and an explicit binding update, never an acceptance flag.
No benchmark text, credentials, model or encoder is read here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nl2sparql.models.b12.contracts import SmallLLMError

ROOT = Path(__file__).resolve().parents[4]
CORPUS = "data/dataset/processed/bilingual-training.jsonl"
EXPORT = "data/dataset/processed/b2-training.jsonl"
# File digests from the accepted publication and its immutable source evidence.
SOURCE_SHA256S = {
    CORPUS: "72285871518a14c0a30e09ee31e58bbb06bfb25089465555625ad9fd929f7f55",
    "data/dataset/processed/bilingual-training-manifest.json": (
        "a4db0c4afde877ac93ac1420c68434774ca73c2f3cc1b9b90697491c56547e28"
    ),
    "data/dataset/processed/bilingual-training-audit.jsonl": (
        "3d10f0d0e1f3db9e46367e7b924cc8e1232ef33f29361bf26d463dad2a76df62"
    ),
    "data/dataset/raw/synthetic-stage-a-v2.jsonl": (
        "15b7cd6144301f040ecef54028929131afab76c45ccf3282011fd68f9ce62203"
    ),
    "data/dataset/raw/generation-config-v2.json": (
        "0dd2234f0c9f16b77288b0deb0e65fc838b210d18f956d728ae39327aa5ad695"
    ),
    "src/nl2sparql/dataset/bilingual/templates.json": (
        "9a62ebb166b6e46da7d6970aeddf675ae05a58284242eea7f5625c8fcf88dbd7"
    ),
    "data/dataset/processed/bilingual-training-exclusion-index.json": (
        "83d76676a00588703d7136772f956770254a656ad1b4c1fab1dfbcc61e1b91b7"
    ),
}


def build_training_export(*, root: Path = ROOT) -> tuple[bytes, bytes]:
    """Authenticate published bytes, then select original train lines in order."""
    sources = {}
    for name, digest in SOURCE_SHA256S.items():
        try:
            payload = (root / name).read_bytes()
        except OSError as exc:
            raise SmallLLMError(f"canonical source unavailable: {name}") from exc
        if hashlib.sha256(payload).hexdigest() != digest:
            raise SmallLLMError(f"canonical source fingerprint mismatch: {name}")
        sources[name] = payload
    lines = sources[CORPUS].splitlines(keepends=True)
    selected = [line for line in lines if json.loads(line)["split"] == "train"]
    payload = b"".join(selected)
    manifest = {
        "schema_version": "b2-canonical-train-export-v1",
        "recipe": "select original split=train lines in original order; preserve bytes",
        "canonical_publication_commit": "2b652a3",
        "sources": SOURCE_SHA256S,
        "records": len(selected),
        "excluded_development_records": len(lines) - len(selected),
        "training_sha256": hashlib.sha256(payload).hexdigest(),
        "acceptance_note": "Derived from accepted T3.3; same-agent audit, not human review.",
    }
    return payload, (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()


def validate_training_projection(snapshot: bytes) -> None:
    """Reject altered rows, development, forged provenance, subsets and reorderings."""
    expected, _ = build_training_export()
    if snapshot != expected:
        raise SmallLLMError("canonical train projection does not match accepted source bytes")
