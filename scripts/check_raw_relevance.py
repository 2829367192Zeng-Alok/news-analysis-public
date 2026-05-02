#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from sqlalchemy import inspect

from models import engine


def main() -> None:
    insp = inspect(engine)
    cols = insp.get_columns("raw_news")
    relevance = [c for c in cols if c.get("name") == "relevance"]
    print(relevance)


if __name__ == "__main__":
    main()
