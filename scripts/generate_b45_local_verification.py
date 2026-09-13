#!/usr/bin/env python
"""Generate canonical local-verification evidence for the T5.3 workflow."""

from __future__ import annotations

import argparse
import json

from nl2sparql.models.b45.local_verification import (
    LOCAL_VERIFICATION_MANIFEST,
    LocalVerificationGenerationError,
    generate_local_verification_manifest,
)


def main(argv: list[str] | None = None) -> int:
    """Run local checks and publish their content-bound manifest."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete T5.3 local gate and write docs/evidence/t5-3-local-verification.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.parse_args(argv)
    try:
        evidence = generate_local_verification_manifest()
    except LocalVerificationGenerationError as error:
        print(
            json.dumps(
                {"status": "blocked", "error": str(error)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": "ready",
                "manifest": str(LOCAL_VERIFICATION_MANIFEST),
                "manifest_sha256": evidence.manifest_sha256,
                "source_sha256": evidence.source_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
