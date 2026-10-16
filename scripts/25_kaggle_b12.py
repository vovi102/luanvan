#!/usr/bin/env python
"""Offline preparation and guarded Kaggle orchestration; real execution is opt-in."""

import sys

sys.dont_write_bytecode = True
from nl2sparql.kaggle.workflow import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
