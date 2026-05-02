#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from news_filter import filter_news
from scripts.export_recent_news_csv import main as export_main


def main() -> None:
    print("STEP 1: quick filter (limit=8)")
    selected = filter_news(limit=8)
    print(f"new selected_news: {len(selected)}")

    print("STEP 2: export csv (recent 30m)")
    export_main()
    print("DONE")


if __name__ == "__main__":
    main()
